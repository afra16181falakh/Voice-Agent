import logging
import sys
import structlog
from app.config import settings

def setup_logging():
    # Windows consoles default to cp1252, which can't encode non-Latin
    # scripts (Hindi/Gujarati/etc. transcripts) — logging one previously
    # raised UnicodeEncodeError, which the stdlib logging module handles by
    # printing a full traceback, adding yet more synchronous overhead.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Configure stdlib logging to run through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO if not settings.server.debug else logging.DEBUG,
    )

    # DEBUG at the root logger cascades to every third-party logger too.
    # The `websockets` library's own wire-level logger dumps full frame
    # contents (including base64 audio payloads) on every message — that's
    # not app debug output, it's noise that measurably slows down the
    # audio-relay hot path. Cap it independently of app debug mode.
    logging.getLogger("websockets").setLevel(logging.WARNING)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.server.debug:
        # Beautiful console logging for dev
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        # Structured JSON for production
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
