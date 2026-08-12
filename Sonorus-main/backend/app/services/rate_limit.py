"""
In-memory sliding-window rate limiter for login attempts (mobile user auth
and the web admin login) -- stdlib-only, same philosophy as auth.py's own
PBKDF2/HMAC choices. No Redis in this deployment, so state is per-process;
acceptable here since there's a single backend instance and the goal is
slowing down brute-force guessing, not perfect distributed enforcement.
"""
import time
from collections import defaultdict

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 15 * 60

_failures: dict[str, list[float]] = defaultdict(list)


def _prune(key: str) -> list[float]:
    cutoff = time.time() - _WINDOW_SECONDS
    attempts = [t for t in _failures[key] if t > cutoff]
    _failures[key] = attempts
    return attempts


def is_locked_out(key: str) -> bool:
    return len(_prune(key)) >= _MAX_ATTEMPTS


def record_failure(key: str) -> None:
    _prune(key)
    _failures[key].append(time.time())


def clear(key: str) -> None:
    _failures.pop(key, None)


def seconds_until_retry(key: str) -> int:
    attempts = _prune(key)
    if not attempts:
        return 0
    oldest = min(attempts)
    return max(0, int(oldest + _WINDOW_SECONDS - time.time()))
