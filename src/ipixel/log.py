"""Unified logging: one line format, ISO-8601 timestamps, per-instance tag.

    2026-11-11T14:03:22.123+01:00 INFO    [@myChannel] Connecté au panneau 32x32

The tag tells two containers apart in a merged `docker compose logs`.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

LOGGER_NAME = "ipixel"
_TAG = os.environ.get("IPIXEL_LOG_TAG", "ipixel")


class _Formatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")

    def format(self, record: logging.LogRecord) -> str:
        record.tag = _TAG
        line = super().format(record)
        # Une entrée = un bloc : les lignes de traceback sont indentées sous la même date.
        return line.replace("\n", "\n    ")


def set_tag(tag: str) -> None:
    """Set the per-instance tag, unless IPIXEL_LOG_TAG pins it."""
    global _TAG
    if "IPIXEL_LOG_TAG" not in os.environ and tag:
        _TAG = tag


def setup_logging(debug: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatter("%(asctime)s %(levelname)-7s [%(tag)s] %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # pypixelcolor log chaque commande en INFO, bleak est bavard : seulement en --debug.
    for noisy in ("pypixelcolor", "bleak"):
        logging.getLogger(noisy).setLevel(logging.DEBUG if debug else logging.WARNING)


log = logging.getLogger(LOGGER_NAME)
