"""Configure package logging from the bundled YAML configuration."""

import logging.config
from importlib import resources

import yaml


def configure_logging() -> None:
    """Load ``config/log_config.yaml`` and apply it with ``dictConfig``."""
    text = resources.files("fundrock").joinpath("config/log_config.yaml").read_text(
        encoding="utf-8"
    )
    logging.config.dictConfig(yaml.safe_load(text))
