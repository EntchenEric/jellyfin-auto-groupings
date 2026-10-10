"""Logging utilities for Jellyfin Groupings."""

import logging
import os


def setup_logger(name: str, level: str = "INFO", log_file: str = None) -> logging.Logger:
    """Set up a logger with the given name, level, and optional file output.

    Args:
        name: The logger name.
        level: The logging level (e.g. "DEBUG", "INFO", "WARNING").
        log_file: Optional file path to write log output to.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid adding handlers if already configured
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler if log_file is provided
        if log_file:
            log_dir = os.path.dirname(log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: The logger name.

    Returns:
        A logging.Logger instance.
    """
    return logging.getLogger(name)