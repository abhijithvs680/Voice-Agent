"""Centralised logging setup.

We use loguru (which Pipecat also uses) so that our application events and the
framework's internal logs share a single, consistent stream. The helpers below
label the main call lifecycle events: started, ended, and errors.
"""

import sys

from loguru import logger

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure a single, readable loguru sink. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan> - <level>{message}</level>"
        ),
    )
    _CONFIGURED = True


def log_call_started(call_sid: str, stream_sid: str, to_number: str = "") -> None:
    logger.info(
        f"CALL STARTED | call_sid={call_sid} stream_sid={stream_sid} to={to_number}"
    )


def log_call_ended(call_sid: str, reason: str = "client disconnected") -> None:
    logger.info(f"CALL ENDED | call_sid={call_sid} reason={reason}")


def log_error(context: str, error: Exception) -> None:
    logger.error(f"ERROR | {context}: {error.__class__.__name__}: {error}")


__all__ = ["logger", "setup_logging", "log_call_started", "log_call_ended", "log_error"]
