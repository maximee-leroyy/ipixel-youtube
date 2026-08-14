"""Unit tests for Studio subscriber parsing."""

from pathlib import Path

from ipixel.youtube.cookies import (
    CookieStore,
    load_netscape_cookies,
    sapisid_from_cookies,
    sapisid_hash,
    studio_headers,
    studio_page_headers,
)
from ipixel.youtube.http import (
    _is_google_login_url,
    _redact_url,
    _SkipGoogleLoginRedirects,
    http_error_detail,
)
from ipixel.youtube.studio import (
    extract_lifetime_subscribers,
    extract_studio_subscriber_count,
    looks_publicly_rounded,
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


def test_extract_lifetime_subscribers_accepts_round_looking_count() -> None:
    payload = {
        "cards": [
            {
                "latestActivityCardData": {
                    "lifetimeSubsData": {
                        "metricColumns": [
                            {"counts": {"values": [1100]}},
                        ]
                    }
                }
            }
        ]
    }
    assert extract_lifetime_subscribers(payload) == 1100


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


def test_google_login_url() -> None:
    assert _is_google_login_url("https://accounts.google.com/ServiceLogin?service=youtube&hl=fr")
    assert not _is_google_login_url("https://studio.youtube.com/")


def test_skip_google_login_redirect() -> None:
    from http.client import HTTPMessage
    from io import BytesIO
    from urllib.request import Request

    handler = _SkipGoogleLoginRedirects()
    request = Request(
        "https://studio.youtube.com/",
        headers={"Authorization": "SAPISIDHASH x"},
    )
    headers = HTTPMessage()
    headers["Location"] = "https://accounts.google.com/ServiceLogin"
    redirected = handler.redirect_request(
        request,
        BytesIO(),
        302,
        "Found",
        headers,
        "https://accounts.google.com/ServiceLogin?service=youtube",
    )
    assert redirected is None


def test_studio_page_headers_omit_authorization() -> None:
    cookies = {"SAPISID": "secret123", "SID": "sidvalue"}
    page = studio_page_headers(cookies)
    api = studio_headers(cookies)
    assert "Authorization" not in page
    assert "SAPISID=secret123" in page["Cookie"]
    assert api["Authorization"].startswith("SAPISIDHASH ")


def test_http_error_detail_empty_body() -> None:
    from email.message import Message
    from io import BytesIO
    from urllib.error import HTTPError

    exc = HTTPError("https://studio.youtube.com/", 400, "Bad Request", Message(), BytesIO(b""))
    detail = http_error_detail(exc)
    assert "400" in detail
    assert "studio.youtube.com" in detail
    assert not detail.endswith(":")


def test_cookie_store_writes_set_cookie(tmp_path: Path) -> None:
    from http.client import HTTPMessage
    from urllib.request import Request

    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com	TRUE	/	TRUE	0	SAPISID	secret123\n",
        encoding="utf-8",
    )
    store = CookieStore(str(cookie_file))
    assert store.as_dict()["SAPISID"] == "secret123"

    headers = HTTPMessage()
    headers.add_header(
        "Set-Cookie",
        "__Secure-3PSIDTS=rotated-token; Domain=.google.com; Path=/; Secure; HttpOnly; Max-Age=3600",
    )

    class Response:
        def info(self) -> HTTPMessage:
            return headers

    store.absorb(Request("https://studio.youtube.com/"), Response())
    text = cookie_file.read_text(encoding="utf-8")
    assert "secret123" in text
    assert "rotated-token" in text
    reloaded = CookieStore(str(cookie_file)).as_dict()
    assert reloaded["SAPISID"] == "secret123"
    assert reloaded["__Secure-3PSIDTS"] == "rotated-token"


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
    test_extract_lifetime_subscribers_accepts_round_looking_count()
    test_studio_session_ok()
    test_google_login_url()
    test_skip_google_login_redirect()
    test_studio_page_headers_omit_authorization()
    test_http_error_detail_empty_body()
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        root = Path(folder)
        netscape_dir = root / "netscape"
        absorb_dir = root / "absorb"
        netscape_dir.mkdir()
        absorb_dir.mkdir()
        test_netscape_cookies(netscape_dir)
        test_cookie_store_writes_set_cookie(absorb_dir)
    print("OK youtube count")
