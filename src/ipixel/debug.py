"""Debug tracing for HTTP / Studio session work, routed through the unified logger."""

from __future__ import annotations

from ipixel.log import log, setup_logging


def set_debug(enabled: bool) -> None:
    setup_logging(enabled)


def debug(message: str) -> None:
    log.debug(message)
