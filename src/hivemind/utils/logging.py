"""Logging setup — structured-ish console + rotating file under var/logs/."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from hivemind.config import Settings

_FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(settings: Settings) -> None:
    """Configure root logging to console + var/logs/bridge.log."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FMT))
    root.addHandler(console)

    log_dir = settings.var_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_h = RotatingFileHandler(
        log_dir / "bridge.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_h.setFormatter(logging.Formatter(_FMT))
    root.addHandler(file_h)
