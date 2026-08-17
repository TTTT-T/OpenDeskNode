"""stdout plus bounded daily application log rotation."""

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import sys


def configure_logging(log_path: str) -> None:
    root = logging.getLogger()
    if getattr(root, "_stock_gateway_configured", False):
        return
    if log_path != ":memory:":
        Path(log_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    root.addHandler(stream)
    if log_path != ":memory:":
        file_handler = TimedRotatingFileHandler(
            log_path,
            when="midnight",
            interval=1,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    root.setLevel(logging.INFO)
    setattr(root, "_stock_gateway_configured", True)
