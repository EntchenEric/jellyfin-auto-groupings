import logging
import tempfile
from pathlib import Path

from utils.logging import get_logger, setup_logger


def test_setup_logger_console_only():
    logger = setup_logger("test_console_logger", level="DEBUG")
    assert logger.name == "test_console_logger"
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) >= 1


def test_setup_logger_with_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "subdir" / "test.log"
        logger = setup_logger("test_file_logger", log_file=log_file, level="INFO")
        assert logger.name == "test_file_logger"
        logger.info("Testing file logging message")

        # Flush handlers
        for h in logger.handlers:
            h.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Testing file logging message" in content


def test_get_logger():
    logger = get_logger("my_custom_module")
    assert logger.name == "my_custom_module"
