"""Структурные логи. Значения с секретами не попадают в вывод."""
from __future__ import annotations

import logging
import sys

import structlog

_SECRET_KEYS = {"apifootball_key", "password", "token", "api_key", "authorization"}


def _redact(_logger, _name, event_dict):
    for k in list(event_dict):
        if k.lower() in _SECRET_KEYS:
            event_dict[k] = "<redacted>"
    return event_dict


def configure(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout,
                        level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
