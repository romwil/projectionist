"""Owner-facing application log reader (tail + filters + SSE helpers)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from projectionist.logging_config import resolve_log_file_path, sanitize_log_message

_LEVEL_RANK = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_VALID_LEVELS = frozenset(_LEVEL_RANK)

# Text formatter: "2024-01-01 12:00:00 INFO logger.name: message"
_TEXT_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<logger>[^\s:]+)\s*:\s*"
    r"(?P<message>.*)$"
)

SENSITIVE_WARNING = (
    "Application logs may contain sensitive data (paths, usernames, request details). "
    "Common API keys and tokens are redacted best-effort; treat this view as owner-private."
)

DEFAULT_TAIL_LIMIT = 300
MAX_TAIL_LIMIT = 2000
MAX_LOGGER_SAMPLES = 40


@dataclass(frozen=True)
class LogLine:
    id: int
    timestamp: str
    level: str
    logger: str
    message: str
    raw: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_log_line(raw: str, *, line_id: int = 0) -> LogLine:
    """Parse a single text or JSON log line into a structured record."""
    text = str(raw or "").rstrip("\n\r")
    cleaned = sanitize_log_message(text)

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            level = str(payload.get("level") or "INFO").upper()
            if level not in _VALID_LEVELS:
                level = "INFO"
            message = sanitize_log_message(str(payload.get("message") or ""))
            logger_name = str(payload.get("logger") or payload.get("name") or "")
            timestamp = str(payload.get("timestamp") or payload.get("time") or "")
            if payload.get("exception"):
                message = f"{message}\n{sanitize_log_message(str(payload['exception']))}".strip()
            return LogLine(
                id=line_id,
                timestamp=timestamp,
                level=level,
                logger=logger_name,
                message=message,
                raw=cleaned,
            )

    match = _TEXT_LINE_RE.match(cleaned)
    if match:
        return LogLine(
            id=line_id,
            timestamp=match.group("timestamp"),
            level=match.group("level").upper(),
            logger=match.group("logger"),
            message=sanitize_log_message(match.group("message")),
            raw=cleaned,
        )

    # Unstructured / continuation lines — keep visible with a soft level.
    return LogLine(
        id=line_id,
        timestamp="",
        level="INFO",
        logger="",
        message=cleaned,
        raw=cleaned,
    )


def normalize_min_level(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip().upper()
    if not value or value == "ALL":
        return None
    if value not in _VALID_LEVELS:
        raise ValueError(f"level must be one of {', '.join(sorted(_VALID_LEVELS))} (or ALL)")
    return value


def line_matches_filters(
    line: LogLine,
    *,
    min_level: Optional[str] = None,
    logger_prefix: Optional[str] = None,
    q: Optional[str] = None,
) -> bool:
    if min_level:
        if _LEVEL_RANK.get(line.level, 0) < _LEVEL_RANK.get(min_level, 0):
            return False
    prefix = str(logger_prefix or "").strip()
    if prefix:
        name = line.logger or ""
        if not (name == prefix or name.startswith(f"{prefix}.")):
            # Also allow substring match on logger for convenience (e.g. "uvicorn").
            if prefix.lower() not in name.lower():
                return False
    needle = str(q or "").strip().lower()
    if needle:
        haystack = f"{line.logger} {line.message} {line.raw}".lower()
        if needle not in haystack:
            return False
    return True


def _read_tail_bytes(path: Path, max_bytes: int) -> tuple[bytes, int]:
    """Return (chunk, start_offset) for the last ``max_bytes`` of ``path``."""
    size = path.stat().st_size
    start = max(0, size - max_bytes)
    with path.open("rb") as handle:
        handle.seek(start)
        data = handle.read()
    return data, start


def read_log_tail(
    path: Optional[Path] = None,
    *,
    limit: int = DEFAULT_TAIL_LIMIT,
    min_level: Optional[str] = None,
    logger_prefix: Optional[str] = None,
    q: Optional[str] = None,
) -> Dict[str, Any]:
    """Return recent filtered lines from the durable app log."""
    log_path = Path(path) if path is not None else resolve_log_file_path()
    limit = max(1, min(int(limit or DEFAULT_TAIL_LIMIT), MAX_TAIL_LIMIT))
    min_level = normalize_min_level(min_level)

    if not log_path.is_file():
        return {
            "path": str(log_path),
            "exists": False,
            "file_size": 0,
            "next_offset": 0,
            "lines": [],
            "loggers": [],
            "sensitive_warning": SENSITIVE_WARNING,
        }

    # Over-read so filters still have enough candidates near the end.
    approx_bytes = max(64_000, limit * 400)
    chunk, start_offset = _read_tail_bytes(log_path, approx_bytes)
    text = chunk.decode("utf-8", errors="replace")
    if start_offset > 0:
        # Drop the first (possibly partial) line when we mid-seeked.
        nl = text.find("\n")
        if nl != -1:
            discarded = text[: nl + 1].encode("utf-8", errors="replace")
            start_offset += len(discarded)
            text = text[nl + 1 :]

    raw_lines = text.splitlines()
    # Absolute line ids: byte offset of each line start within the file.
    offset = start_offset
    parsed: List[LogLine] = []
    for raw in raw_lines:
        line_id = offset
        encoded = (raw + "\n").encode("utf-8")
        offset += len(encoded)
        if not raw.strip():
            continue
        parsed.append(parse_log_line(raw, line_id=line_id))

    matched = [
        line
        for line in parsed
        if line_matches_filters(line, min_level=min_level, logger_prefix=logger_prefix, q=q)
    ]
    selected = matched[-limit:]

    loggers = _collect_loggers(parsed)
    file_size = log_path.stat().st_size
    return {
        "path": str(log_path),
        "exists": True,
        "file_size": file_size,
        "next_offset": file_size,
        "lines": [line.to_dict() for line in selected],
        "loggers": loggers,
        "sensitive_warning": SENSITIVE_WARNING,
    }


def _collect_loggers(lines: Sequence[LogLine]) -> List[str]:
    seen: Dict[str, None] = {}
    for line in lines:
        name = (line.logger or "").strip()
        if not name:
            continue
        seen.setdefault(name, None)
        if len(seen) >= MAX_LOGGER_SAMPLES:
            break
    # Prefer projectionist.* first, then alpha.
    names = list(seen.keys())
    names.sort(key=lambda n: (0 if n.startswith("projectionist") else 1, n.lower()))
    return names


def read_new_lines(
    path: Path,
    *,
    after_offset: int,
    min_level: Optional[str] = None,
    logger_prefix: Optional[str] = None,
    q: Optional[str] = None,
    max_lines: int = 200,
) -> tuple[List[LogLine], int]:
    """Read lines appended after ``after_offset``. Returns (lines, new_offset)."""
    if not path.is_file():
        return [], max(0, after_offset)

    size = path.stat().st_size
    if after_offset > size:
        # Rotation / truncate — restart from beginning of current file.
        after_offset = 0
    if after_offset == size:
        return [], after_offset

    min_level = normalize_min_level(min_level)
    with path.open("rb") as handle:
        handle.seek(after_offset)
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    # Hold a trailing partial line until a newline arrives.
    if text and not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return [], after_offset
        complete = text[: last_nl + 1]
        consumed = len(complete.encode("utf-8"))
    else:
        complete = text
        consumed = len(data)

    offset = after_offset
    out: List[LogLine] = []
    for raw in complete.splitlines():
        line_id = offset
        offset += len((raw + "\n").encode("utf-8"))
        if not raw.strip():
            continue
        line = parse_log_line(raw, line_id=line_id)
        if line_matches_filters(line, min_level=min_level, logger_prefix=logger_prefix, q=q):
            out.append(line)
            if len(out) >= max_lines:
                break
    return out, after_offset + consumed


def iter_log_chunks(
    lines: Iterable[LogLine],
) -> Iterator[Dict[str, str]]:
    """Yield SSE event dicts for ``EventSourceResponse``."""
    for line in lines:
        yield {"event": "log", "data": json.dumps(line.to_dict(), ensure_ascii=False)}
