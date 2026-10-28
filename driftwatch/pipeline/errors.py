"""
Error classification.

Concept: TRANSIENT vs PERMANENT failures.
  * Transient = might succeed if we just try again: network blip, timeout,
    deadlock, server restarting. -> RETRY with backoff.
  * Permanent = will fail every time until a human/AI fixes something:
    missing table, missing column, bad credentials, type mismatch. -> DON'T
    retry (retrying wastes time and hides the real problem). FAIL + ALERT.

Getting this distinction right is the first step of "failure triage". In
Phase 11 the AI agent takes over the hard cases this simple classifier can't
explain.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for errors we raise ourselves."""


class TransientError(PipelineError):
    """Worth retrying."""


class PermanentError(PipelineError):
    """Not worth retrying — needs a fix."""


# SQLSTATE codes (first 2 chars = class) that usually mean "try again".
_TRANSIENT_SQLSTATES = {
    "08001",  # unable to connect
    "08S01",  # communication link failure (server dropped / network)
    "08004",  # server rejected connection
    "HYT00",  # timeout expired
    "HYT01",  # connection timeout
    "40001",  # deadlock victim
}


def _sqlstate(exc: BaseException) -> str | None:
    """pyodbc puts the SQLSTATE code as the first argument of its exceptions."""
    args = getattr(exc, "args", ())
    if args and isinstance(args[0], str) and len(args[0]) == 5:
        return args[0]
    return None


def is_transient(exc: BaseException) -> bool:
    if isinstance(exc, TransientError):
        return True
    if isinstance(exc, PermanentError):
        return False
    # SQLAlchemy wraps the driver error; look inside it.
    inner = getattr(exc, "orig", None) or exc
    state = _sqlstate(inner)
    if state is not None:
        return state in _TRANSIENT_SQLSTATES or state.startswith("08")
    return isinstance(exc, (ConnectionError, TimeoutError))


def error_type(exc: BaseException) -> str:
    """Short label stored in run metadata, e.g. 'transient:08S01' or 'permanent:42S02'."""
    inner = getattr(exc, "orig", None) or exc
    state = _sqlstate(inner)
    kind = "transient" if is_transient(exc) else "permanent"
    return f"{kind}:{state or type(inner).__name__}"