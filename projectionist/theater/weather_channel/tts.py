"""Local neural speech for Weather Channel scripts.

Kokoro is the default engine; Piper is the lighter fallback. Both run inside the
container. The voice model is downloaded once, when the owner turns on Weather
narration, into ``DATA_DIR/weather/tts`` — it is not part of the image. Each
script variant is rendered once to ``DATA_DIR/weather/audio/{hash}.opus`` and
shared by every viewer. When TTS is off or fails, the channel shows captions and
does not fall back to a browser voice.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import threading
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

KOKORO_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
PIPER_VOICES = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
MODEL_HOSTS = ("github.com", "huggingface.co")

ENGINES: Dict[str, Dict[str, Any]] = {
    "kokoro": {
        "label": "Kokoro (default, most natural)",
        "files": [
            {"name": "kokoro-v1.0.int8.onnx", "url": f"{KOKORO_RELEASE}/kokoro-v1.0.int8.onnx", "approx_bytes": 92_000_000},
            {"name": "voices-v1.0.bin", "url": f"{KOKORO_RELEASE}/voices-v1.0.bin", "approx_bytes": 28_000_000},
        ],
        "voices": [
            {"id": "af_heart", "label": "Heart — warm, American"},
            {"id": "am_michael", "label": "Michael — calm, American"},
            {"id": "af_bella", "label": "Bella — bright, American"},
            {"id": "bm_george", "label": "George — British"},
        ],
    },
    "piper": {
        "label": "Piper (lighter, faster on small CPUs)",
        "voices": [
            {"id": "en_US-lessac-medium", "label": "Lessac — American", "path": "en/en_US/lessac/medium", "approx_bytes": 63_000_000},
            {"id": "en_US-ryan-medium", "label": "Ryan — American", "path": "en/en_US/ryan/medium", "approx_bytes": 63_000_000},
            {"id": "en_GB-alan-medium", "label": "Alan — British", "path": "en/en_GB/alan/medium", "approx_bytes": 63_000_000},
        ],
    },
}
DEFAULT_ENGINE = "kokoro"
RATE_MIN, RATE_MAX = 0.8, 1.2


def normalize_choice(engine: str, voice: str, rate: Any) -> tuple[str, str, float]:
    eng = engine if engine in ENGINES else DEFAULT_ENGINE
    voices = [v["id"] for v in ENGINES[eng]["voices"]]
    picked = voice if voice in voices else voices[0]
    try:
        speed = float(rate)
    except (TypeError, ValueError):
        speed = 1.0
    return eng, picked, round(min(max(speed, RATE_MIN), RATE_MAX), 2)


def model_files(engine: str, voice: str) -> List[Dict[str, Any]]:
    if engine == "piper":
        meta = next(v for v in ENGINES["piper"]["voices"] if v["id"] == voice)
        base = f"{PIPER_VOICES}/{meta['path']}/{voice}"
        return [
            {"name": f"{voice}.onnx", "url": f"{base}.onnx", "approx_bytes": meta["approx_bytes"]},
            {"name": f"{voice}.onnx.json", "url": f"{base}.onnx.json", "approx_bytes": 5_000},
        ]
    return list(ENGINES["kokoro"]["files"])


def script_hash(text: str, engine: str, voice: str, rate: float) -> str:
    key = f"{engine}|{voice}|{rate:.2f}|{' '.join(str(text).split())}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class Engine(Protocol):
    def synthesize(self, text: str, wav_path: Path) -> None: ...


def engine_available(engine: str) -> bool:
    import importlib.util

    module = "kokoro_onnx" if engine == "kokoro" else "piper"
    return importlib.util.find_spec(module) is not None


class KokoroEngine:
    def __init__(self, model_dir: Path, voice: str, rate: float) -> None:
        from kokoro_onnx import Kokoro  # type: ignore[import-not-found]

        self._tts = Kokoro(str(model_dir / "kokoro-v1.0.int8.onnx"), str(model_dir / "voices-v1.0.bin"))
        self.voice = voice
        self.rate = rate

    def synthesize(self, text: str, wav_path: Path) -> None:
        import numpy as np

        lang = "en-gb" if self.voice.startswith("b") else "en-us"
        samples, sample_rate = self._tts.create(text, voice=self.voice, speed=self.rate, lang=lang)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        with wave.open(str(wav_path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(int(sample_rate))
            out.writeframes(pcm)


class PiperEngine:
    def __init__(self, model_dir: Path, voice: str, rate: float) -> None:
        from piper import PiperVoice  # type: ignore[import-not-found]

        self._voice = PiperVoice.load(str(model_dir / f"{voice}.onnx"))
        self.rate = rate

    def synthesize(self, text: str, wav_path: Path) -> None:
        try:
            from piper import SynthesisConfig  # type: ignore[import-not-found]

            config = SynthesisConfig(length_scale=1.0 / self.rate)
        except ImportError:
            config = None
        with wave.open(str(wav_path), "wb") as out:
            if config is not None:
                self._voice.synthesize_wav(text, out, syn_config=config)
            else:
                self._voice.synthesize_wav(text, out)


def _ffmpeg() -> Optional[str]:
    import os

    return os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")


def wav_to_opus(wav_path: Path, opus_path: Path) -> None:
    binary = _ffmpeg()
    if not binary:
        raise RuntimeError("ffmpeg is not available to encode opus")
    subprocess.run(
        [binary, "-nostdin", "-loglevel", "error", "-y", "-i", str(wav_path), "-c:a", "libopus", "-b:a", "40k", "-f", "ogg", str(opus_path)],
        check=True,
        timeout=60,
    )


@dataclass
class DownloadState:
    running: bool = False
    done_bytes: int = 0
    total_bytes: int = 0
    error: str = ""
    engine: str = ""
    voice: str = ""


@dataclass
class TtsRenderer:
    data_dir: Path
    engine_factory: Optional[Callable[[str, Path, str, float], Engine]] = None
    encoder: Callable[[Path, Path], None] = wav_to_opus
    downloader: Optional[Callable[[str, Path, Callable[[int], None]], None]] = None
    _engines: Dict[tuple, Engine] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    download: DownloadState = field(default_factory=DownloadState)
    failures: int = 0
    last_error: str = ""

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "weather" / "audio"

    def model_dir(self, engine: str) -> Path:
        return self.data_dir / "weather" / "tts" / engine

    def installed(self, engine: str, voice: str) -> bool:
        base = self.model_dir(engine)
        return all((base / f["name"]).is_file() and (base / f["name"]).stat().st_size > 0 for f in model_files(engine, voice))

    def audio_path(self, digest: str) -> Optional[Path]:
        if not digest or len(digest) != 32 or any(ch not in "0123456789abcdef" for ch in digest):
            return None
        path = self.audio_dir / f"{digest}.opus"
        return path if path.is_file() else None

    def status(self, engine: str, voice: str, rate: float, enabled: bool) -> Dict[str, Any]:
        files = model_files(engine, voice)
        return {
            "enabled": bool(enabled),
            "engine": engine,
            "voice": voice,
            "rate": rate,
            "engine_available": self.engine_factory is not None or engine_available(engine),
            "installed": self.installed(engine, voice),
            "download_bytes": sum(int(f["approx_bytes"]) for f in files),
            "downloading": self.download.running,
            "download_done_bytes": self.download.done_bytes,
            "download_total_bytes": self.download.total_bytes,
            "download_error": self.download.error,
            "last_error": self.last_error,
            "engines": [
                {"id": key, "label": meta["label"], "voices": [{"id": v["id"], "label": v["label"]} for v in meta["voices"]]}
                for key, meta in ENGINES.items()
            ],
        }

    # -- download ---------------------------------------------------------

    def _default_download(self, url: str, dest: Path, progress: Callable[[int], None]) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": "ProjectionistWeather/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — fixed model hosts
            with dest.open("wb") as out:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
                    progress(len(chunk))

    def start_download(self, engine: str, voice: str, *, background: bool = True) -> bool:
        with self._lock:
            if self.download.running:
                return False
            files = model_files(engine, voice)
            self.download = DownloadState(
                running=True, total_bytes=sum(int(f["approx_bytes"]) for f in files), engine=engine, voice=voice
            )

        def run() -> None:
            base = self.model_dir(engine)
            base.mkdir(parents=True, exist_ok=True)
            fetch = self.downloader or self._default_download
            try:
                for item in files:
                    dest = base / item["name"]
                    if dest.is_file() and dest.stat().st_size > 0:
                        self.download.done_bytes += int(item["approx_bytes"])
                        continue
                    tmp = dest.with_suffix(dest.suffix + ".part")

                    def bump(n: int) -> None:
                        self.download.done_bytes += n

                    fetch(item["url"], tmp, bump)
                    tmp.replace(dest)
            except Exception as exc:  # noqa: BLE001 — surfaced in Admin
                logger.warning("weather voice download failed: %s", exc)
                self.download.error = f"Voice download failed: {type(exc).__name__}"
            finally:
                self.download.running = False

        if background:
            threading.Thread(target=run, name="weather-voice-download", daemon=True).start()
        else:
            run()
        return True

    # -- render -----------------------------------------------------------

    def _engine(self, engine: str, voice: str, rate: float) -> Engine:
        key = (engine, voice, rate)
        if key not in self._engines:
            base = self.model_dir(engine)
            if self.engine_factory is not None:
                self._engines[key] = self.engine_factory(engine, base, voice, rate)
            elif engine == "piper":
                self._engines[key] = PiperEngine(base, voice, rate)
            else:
                self._engines[key] = KokoroEngine(base, voice, rate)
        return self._engines[key]

    def render(self, text: str, *, engine: str, voice: str, rate: float) -> Optional[str]:
        """Render once; return the hash, or None (captions only) on any failure."""
        digest = script_hash(text, engine, voice, rate)
        if self.audio_path(digest):
            return digest
        if not self.installed(engine, voice) and self.engine_factory is None:
            return None
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        wav = self.audio_dir / f"{digest}.wav"
        out = self.audio_dir / f"{digest}.opus"
        tmp = self.audio_dir / f"{digest}.opus.part"
        try:
            self._engine(engine, voice, rate).synthesize(text, wav)
            self.encoder(wav, tmp)
            tmp.replace(out)
            return digest
        except Exception as exc:  # noqa: BLE001 — the channel falls back to captions
            self.failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            logger.info("weather TTS render failed: %s", exc)
            return None
        finally:
            for leftover in (wav, tmp):
                try:
                    leftover.unlink()
                except FileNotFoundError:
                    pass
