"""Unified logging: the one place that defines the log line format.

Every line looks like:

    2026-11-11T20:04:30.488+01:00 INFO    [@myChannel] Connected to panel AA:BB:CC:DD:EE:FF (32x32)

- timestamp: ISO-8601, milliseconds, local offset (set TZ in the container)
- level: padded to 7 characters so messages line up
- tag: the channel (or the BLE address), so two containers can be told apart
  in a merged `nerdctl compose logs`

Multi-line messages (tracebacks, help text) are indented under their line.

The container entrypoint logs through this module too:

    python -m ipixel.log INFO "message"
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(tag)s] %(message)s"

log = logging.getLogger("ipixel")
_tag = "ipixel"


def tag_for(channel: str | None, address: str | None) -> str:
    """The instance tag: the channel, else the BLE address, else "ipixel"."""
    return channel or address or "ipixel"


def set_tag(tag: str) -> None:
    global _tag
    _tag = tag


class _Formatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return datetime.fromtimestamp(record.created).astimezone().isoformat(timespec="milliseconds")

    def format(self, record: logging.LogRecord) -> str:
        record.tag = _tag
        return super().format(record).replace("\n", "\n    ")


def setup_logging(debug: bool) -> None:
    """Send every logger (ours, pypixelcolor, bleak) to stderr in LOG_FORMAT.

    Without --debug, pypixelcolor and bleak only show warnings: pypixelcolor
    logs every BLE command at INFO, which would flood the output.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for library in ("pypixelcolor", "bleak"):
        logging.getLogger(library).setLevel(logging.DEBUG if debug else logging.WARNING)


def main(argv: list[str]) -> int:
    """`python -m ipixel.log LEVEL message...`: one log line, tag taken from the env."""
    level, *words = argv
    setup_logging(debug=False)
    set_tag(tag_for(os.environ.get("YOUTUBE_CHANNEL"), os.environ.get("IPIXEL_ADDRESS")))
    log.log(logging.getLevelNamesMapping()[level], " ".join(words))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
