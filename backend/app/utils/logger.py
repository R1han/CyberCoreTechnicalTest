"""
Ask-Docs — Structured JSON Logger
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Generator

from app.config import settings


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge extra fields
        for key in ("request_id", "path", "docs_dir", "count", "chunks",
                     "size_mb", "total", "max", "elapsed_ms", "span",
                     "file_path", "question", "top_k", "status_code"):
            val = getattr(record, key, None)
            if val is not None:
                log_obj[key] = val
        if record.exc_info and record.exc_info[0] is not None:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with JSON output."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    return logger


def make_request_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def timing_span(logger: logging.Logger, span_name: str, **extra: Any) -> Generator[None, None, None]:
    """Context manager that logs elapsed time for a named span."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            f"span completed: {span_name}",
            extra={"span": span_name, "elapsed_ms": elapsed_ms, **extra},
        )
