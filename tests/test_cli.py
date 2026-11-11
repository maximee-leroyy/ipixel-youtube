"""CLI: exit codes, SIGTERM, no silent fallbacks."""

import signal

import pytest
from click.testing import CliRunner

from ipixel import cli


def invoke(*args: str) -> int:
    return CliRunner().invoke(cli.main, list(args), env={"YOUTUBE_SOURCE": "", "IPIXEL_BRIGHTNESS": ""}).exit_code


def test_sigterm_handler_exits_cleanly() -> None:
    with pytest.raises(SystemExit) as exc:
        cli._exit_on_sigterm(signal.SIGTERM, None)
    assert exc.value.code == 0


def test_save_slot_requires_static() -> None:
    assert invoke("--channel", "UCxxxxxxxxxxxxxxxxxxxxxx", "--save-slot", "2", "--print-count") == 2


def test_studio_without_cookies_is_an_error(tmp_path) -> None:
    missing = str(tmp_path / "none.txt")
    assert invoke("--channel", "UCxxxxxxxxxxxxxxxxxxxxxx", "--cookies", missing, "--preview") == 2


def test_missing_channel_name_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "fetch_channel_name", lambda channel_id: None)
    assert invoke("--channel", "UCxxxxxxxxxxxxxxxxxxxxxx", "--source", "live", "--print-count") == 1


def test_print_count_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "fetch_channel_name", lambda channel_id: "Chan")
    monkeypatch.setattr(cli, "fetch_count", lambda *args, **kwargs: 1234)
    result = CliRunner().invoke(
        cli.main, ["--channel", "UCxxxxxxxxxxxxxxxxxxxxxx", "--source", "live", "--print-count"]
    )
    assert result.exit_code == 0
    assert "Chan 1.234" in result.stdout
