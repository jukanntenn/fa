from __future__ import annotations

import logging
import sys
from pathlib import Path

from fa.core.config import FA_LOG_FILE_NAME


def configure_logging(logs_dir: Path) -> logging.Logger:
    logger = logging.getLogger("fa")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(logs_dir / FA_LOG_FILE_NAME, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger
