"""Unified log format: ISO timestamp, padded level, instance tag."""

import logging
import re
import subprocess
import sys

import pytest

from ipixel.log import log, set_tag, setup_logging, tag_for

LINE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d (\w+) +\[(.+?)\] (.*)$")


def test_tag_for_prefers_channel_then_address() -> None:
    assert tag_for("@chan", "AA:BB") == "@chan"
    assert tag_for(None, "AA:BB") == "AA:BB"
    assert tag_for(None, None) == "ipixel"


def test_line_format(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(debug=False)
    set_tag("@chan")
    log.info("hello")
    match = LINE.match(capsys.readouterr().err.rstrip("\n"))
    assert match is not None
    assert match.groups() == ("INFO", "@chan", "hello")


def test_multiline_is_indented(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging(debug=False)
    log.error("first\nsecond")
    first, second = capsys.readouterr().err.rstrip("\n").split("\n")
    assert LINE.match(first)
    assert second == "    second"


def test_libraries_quiet_without_debug() -> None:
    setup_logging(debug=False)
    assert logging.getLogger("pypixelcolor").level == logging.WARNING
    setup_logging(debug=True)
    assert logging.getLogger("pypixelcolor").level == logging.DEBUG


def test_module_cli_matches_format() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "ipixel.log", "WARNING", "from", "shell"],
        capture_output=True,
        text=True,
        check=True,
        env={"YOUTUBE_CHANNEL": "@chan", "PATH": ""},
    )
    match = LINE.match(out.stderr.rstrip("\n"))
    assert match is not None
    assert match.groups() == ("WARNING", "@chan", "from shell")
