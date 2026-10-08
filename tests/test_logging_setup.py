import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fundrock.logging_setup import configure_logging


class ConfigureLoggingTest(unittest.TestCase):
    def test_configure_logging_writes_to_log_file(self):
        logger = logging.getLogger("fundrock")
        old = (logger.handlers[:], logger.level, logger.propagate)
        with tempfile.TemporaryDirectory() as directory:
            with patch("fundrock.dblogging.get_log_path", side_effect=lambda n: str(Path(directory) / n)):
                configure_logging()
                try:
                    logging.getLogger("fundrock.test").error("hello log")
                    for handler in logger.handlers:
                        handler.flush()
                    text = (Path(directory) / "fundrock.log").read_text()
                    self.assertIn("hello log", text)
                finally:
                    for handler in logger.handlers:
                        handler.close()
                    logger.handlers[:] = old[0]
                    logger.setLevel(old[1])
                    logger.propagate = old[2]
