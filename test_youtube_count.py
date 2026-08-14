"""Unit tests for Studio subscriber parsing."""

from pathlib import Path

from youtube_subs import (
    _redact_url,
    extract_lifetime_subscribers,
    extract_studio_subscriber_count,
    load_netscape_cookies,
    looks_publicly_rounded,
    sapisid_from_cookies,
    sapisid_hash,
    studio_session_ok,
)


def test_redact_url() -> None:
    url = _redact_url("https://studio.youtube.com/youtubei/v1/yta_web/get_screen?alt=json&key=SECRET")
    assert "SECRET" not in url
    assert "key=..." in url


def test_looks_publicly_rounded() -> None:
    assert looks_publicly_rounded(1100)
    assert looks_publicly_rounded(1090)
    assert looks_publicly_rounded(1000)
    assert not looks_publicly_rounded(1093)
    assert not looks_publicly_rounded(999)


def test_extract_prefers_owner_metric() -> None:
    payload = {
        "channels": [
            {
                "channelId": "UCxxxxxxxxxxxxxxxxxxxxxx",
                "metric": {"subscriberCount": "1093", "videoCount": "12"},
            }
        ]
    }
    assert extract_studio_subscriber_count(payload, "UCxxxxxxxxxxxxxxxxxxxxxx") == 1093


def test_extract_lifetime_subscribers() -> None:
    payload = {
        "cards": [
            {
                "latestActivityCardData": {
                    "lifetimeSubsData": {
                        "metricColumns": [
                            {"counts": {"values": [1096]}},
                        ]
                    }
                }
            }
        ]
    }
    assert extract_lifetime_subscribers(payload) == 1096


def test_studio_session_ok() -> None:
    html = '"CHANNEL_ID":"UCxxxxxxxxxxxxxxxxxxxxxx","LOGGED_IN":true,ServiceLogin'
    assert studio_session_ok(html, "https://studio.youtube.com/")
    assert not studio_session_ok(html, "https://accounts.google.com/ServiceLogin")
    assert not studio_session_ok("<html>ServiceLogin</html>", "https://studio.youtube.com/")


def test_extract_skips_rounded_when_exact_exists() -> None:
    payload = {
        "stats": {
            "subscriberCount": "1100",
            "currentSubscriberCount": 1093,
        }
    }
    assert extract_studio_subscriber_count(payload) == 1093


def test_netscape_cookies(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com	TRUE	/	TRUE	0	SAPISID	secret123\n"
        "#HttpOnly_.google.com	TRUE	/	TRUE	0	SID	sidvalue\n",
        encoding="utf-8",
    )
    cookies = load_netscape_cookies(str(cookie_file))
    assert cookies["SAPISID"] == "secret123"
    assert cookies["SID"] == "sidvalue"
    assert sapisid_from_cookies(cookies) == "secret123"
    token = sapisid_hash("secret123")
    assert "_" in token
    timestamp, digest = token.split("_", 1)
    assert timestamp.isdigit()
    assert len(digest) == 40


if __name__ == "__main__":
    test_looks_publicly_rounded()
    test_redact_url()
    test_extract_prefers_owner_metric()
    test_extract_skips_rounded_when_exact_exists()
    test_extract_lifetime_subscribers()
    test_studio_session_ok()
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        test_netscape_cookies(Path(folder))
    print("OK youtube count")
