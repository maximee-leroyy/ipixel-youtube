"""Optional stderr tracing for HTTP / Studio session work."""

from __future__ import annotations

import sys

DEBUG = False


def set_debug(enabled: bool) -> None:
    global DEBUG
    DEBUG = enabled


def debug(message: str) -> None:
    if DEBUG:
        print(f"debug: {message}", file=sys.stderr)
