"""Structured logging setup using structlog with file and console output."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import structlog

from claudedev.config import LOG_DIR

if TYPE_CHECKING:
    from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    json_file: bool = True,
) -> None:
    """Configure structured logging for the application.

    Sets up both console (human-readable) and file (JSON) logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        log_dir: Directory for log files. Defaults to ~/.claudedev/logs/.
        json_file: Whether to also write JSON logs to a file.
    """
    log_dir = log_dir or LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    if json_file:
        json_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler = logging.FileHandler(log_dir / "claudedev.log")
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)

    for noisy_logger in ("uvicorn", "uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
