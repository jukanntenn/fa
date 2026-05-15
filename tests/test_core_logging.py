from __future__ import annotations

import logging
from pathlib import Path

from fa.core.logging import configure_logging


def test_configure_logging_returns_logger_with_expected_name(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    assert logger.name == "fa"


def test_configure_logging_adds_console_and_file_handlers(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    handlers = logger.handlers
    assert len(handlers) == 2
    handler_types = {type(h).__name__ for h in handlers}
    assert "StreamHandler" in handler_types
    assert "FileHandler" in handler_types


def test_configure_logging_sets_correct_log_levels(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    console_handler = next(
        h for h in logger.handlers if not isinstance(h, logging.FileHandler)
    )
    file_handler = next(
        h for h in logger.handlers if isinstance(h, logging.FileHandler)
    )
    assert console_handler.level == logging.INFO
    assert file_handler.level == logging.DEBUG
