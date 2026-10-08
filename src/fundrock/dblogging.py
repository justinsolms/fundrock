"""Logging handlers for the fundrock package."""

import logging.handlers

from fundrock.path_utils import get_log_path


class FileHandler(logging.handlers.TimedRotatingFileHandler):
    """Timed rotating file handler whose log file lives in the project log path.

    The log file path must not be given in the log configuration file; it is
    set here. All other keyword arguments are those of
    ``logging.handlers.TimedRotatingFileHandler`` and come from the YAML config.
    """

    _log_file = "fundrock.log"

    def __init__(self, **kwargs):
        super().__init__(get_log_path(self._log_file), **kwargs)
