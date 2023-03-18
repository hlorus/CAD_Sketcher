import os
import logging
from tempfile import gettempdir
from pathlib import Path

from .register import get_name


def setup_logger(logger):
    """Configures a logger, this is intended to be run on the root logger"""

    # Clear handlers
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(name)s:{%(levelname)s}: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    filepath = Path(gettempdir()) / (get_name() + f"-{os.getlogin()}" + ".log")

    logger.info("Logging into: " + str(filepath))

    # Add file handler
    try:
        file_handler = logging.FileHandler(filepath, mode="w")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except:
        logger.warning(f"Cannot use logger file at: {filepath}")


def update_logger(logger):
    from .preferences import get_prefs

    prefs = get_prefs()
    logger.setLevel(prefs.logging_level)
