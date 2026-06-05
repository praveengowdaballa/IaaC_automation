"""
scripts/logger.py
Module-level logging configuration for tf_differ.
"""

import logging
import sys
from typing import Optional

logger = logging.getLogger("tf_differ")
_logging_configured = False


def setup_logger(
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    force_reconfigure: bool = False
) -> None:
    """
    Configure module-level logging with console and optional file handlers.

    Args:
        level: Logging level (INFO, DEBUG, ERROR, WARNING)
        log_file: Optional path to write logs to file
        force_reconfigure: Force reconfiguration even if already configured
    """
    global _logging_configured

    if _logging_configured and not force_reconfigure:
        return

    logger.handlers = []

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info(f"Logging to file: {log_file}")
        except IOError as e:
            logger.warning(f"Could not create log file {log_file}: {e}")

    logger.setLevel(level)
    _logging_configured = True
