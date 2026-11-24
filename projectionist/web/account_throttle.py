"""Per-account sign-in lock (SEC-018).

Ten failures lock the username or invite. The next ten lock for twice as
long, up to 24 hours. A success clears the count. State stays in process
memory. The raw invite token and the password are never stored.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

FAILURES_PER_LOCK = 10
BASE_LOCK_SECONDS = 15 * 60
MAX_LOCK_SECONDS = 24 * 60 * 60

GENERIC_LOGIN_DETAIL = "Invalid username or password"
GENERIC_INVITE_DETAIL = "This invite can't be used."


def lock_seconds_for_round(round_number: int) -> int:
    """``round_number`` 1 is 15 minutes. Each later round doubles, capped at a day."""
    if round_number < 1:
        return 0
    # 2**6 * 15 min is 16 hours; 2**7 is 32 hours, so the cap applies there.
    shift = min(round_number - 1, 16)
    return min(BASE_LOCK_SECONDS * (2**shift), MAX_LOCK_SECONDS)


def login_key(username: str) -> str:
    name = " ".join(str(username or "").split()).casefold()
    return f"login:{name}"


def invite_key(token: str) -> str:
    """Key a redeem attempt by invite id, or by a hash when the token is not valid."""
    from projectionist.invites import parse_invite_token

    try:
        invite_id, _raw = parse_invite_token(token)
    except ValueError:
        digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
        return f"invite-unparsed:{digest}"
    return f"invite:{invite_id}"


@dataclass
class _Bucket:
    failures: int = 0
    locked_until: float = 0.0
    rounds: int = 0


class AccountThrottle:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}
        self._now = time.monotonic

    def locked(self, key: str, *, now: float | None = None) -> bool:
        moment = self._now() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return False
            return bucket.locked_until > moment

    def record_failure(self, key: str, *, now: float | None = None) -> int | None:
        """Count one failure. Return the new lock length in seconds when a lock starts."""
        moment = self._now() if now is None else now
        with self._lock:
            bucket = self._buckets.setdefault(key, _Bucket())
            if bucket.locked_until > moment:
                return None
            bucket.failures += 1
            if bucket.failures % FAILURES_PER_LOCK != 0:
                return None
            bucket.rounds += 1
            seconds = lock_seconds_for_round(bucket.rounds)
            bucket.locked_until = moment + seconds
            return seconds

    def record_success(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


account_throttle = AccountThrottle()


def clear_account_throttle() -> None:
    """Test helper."""
    account_throttle.clear()
