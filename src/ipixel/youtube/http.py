"""HTTP helpers for YouTube / Studio requests."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from http.client import HTTPMessage, HTTPResponse
from typing import IO

from ipixel.constants import USER_AGENT
from ipixel.debug import debug
from ipixel.youtube.cookies import CookieStore

_STUDIO_HTML_OPENER: urllib.request.OpenerDirector | None = None


def _merge_headers(extra: dict[str, str] | None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if extra:
        headers.update(extra)
    return headers


def _redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "...") if key.lower() in {"key", "access_token", "token"} else (key, value) for key, value in query
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(redacted), parsed.fragment)
    )


def http_error_detail(exc: urllib.error.HTTPError) -> str:
    url = _redact_url(exc.url) if exc.url else ""
    try:
        body = exc.read().decode(errors="replace")[:300].strip()
    except OSError:
        body = ""
    reason = str(exc.reason or "").strip()
    bits = [str(exc.code)]
    if reason:
        bits.append(reason)
    if url:
        bits.append(url)
    detail = " ".join(bits)
    return f"{detail}: {body}" if body else detail


def _is_google_login_url(url: str | None) -> bool:
    if not url:
        return False
    host = urllib.parse.urlsplit(url).netloc.lower()
    return host == "accounts.google.com" or host.endswith(".accounts.google.com")


def _http_error_is_login(exc: urllib.error.HTTPError) -> bool:
    if _is_google_login_url(exc.url):
        return True
    location = exc.headers.get("Location") if exc.headers is not None else None
    return _is_google_login_url(location)


class _SkipGoogleLoginRedirects(urllib.request.HTTPRedirectHandler):
    """Do not follow Studio → accounts.google.com; urllib would 400 the login page."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if _is_google_login_url(newurl):
            debug(f"studio stop redirect {_redact_url(newurl)}")
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old_host = urllib.parse.urlsplit(req.full_url).netloc
        new_host = urllib.parse.urlsplit(newurl).netloc
        if old_host != new_host:
            redirected.remove_header("Authorization")
        return redirected


def studio_html_opener() -> urllib.request.OpenerDirector:
    global _STUDIO_HTML_OPENER
    if _STUDIO_HTML_OPENER is None:
        _STUDIO_HTML_OPENER = urllib.request.build_opener(_SkipGoogleLoginRedirects)
    return _STUDIO_HTML_OPENER


def _http_open(
    request: urllib.request.Request,
    timeout: int,
    opener: urllib.request.OpenerDirector | None = None,
    cookie_store: CookieStore | None = None,
) -> HTTPResponse:
    debug(f"{request.get_method()} {_redact_url(request.full_url)}")
    try:
        if opener is None:
            response = urllib.request.urlopen(request, timeout=timeout)
        else:
            response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        debug(f"HTTP {exc.code} {_redact_url(exc.url or request.full_url)}")
        if cookie_store is not None:
            cookie_store.absorb(request, exc)
        raise
    if cookie_store is not None:
        cookie_store.absorb(request, response)
    return response


def http_get_text(
    url: str,
    timeout: int = 20,
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    cookie_store: CookieStore | None = None,
) -> tuple[str, str]:
    request = urllib.request.Request(url, headers=_merge_headers(headers))
    with _http_open(request, timeout, opener, cookie_store) as response:
        body = response.read().decode("utf-8", errors="replace")
        final_url = response.url
        debug(f"GET <- {response.status} {final_url} ({len(body)} bytes)")
        return body, final_url


def http_get_json(
    url: str,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
    cookie_store: CookieStore | None = None,
) -> dict:
    request = urllib.request.Request(url, headers=_merge_headers(headers))
    with _http_open(request, timeout, cookie_store=cookie_store) as response:
        raw = response.read().decode()
        debug(f"GET <- {response.status} {_redact_url(response.url)} ({len(raw)} bytes)")
        return json.loads(raw)


def http_post_json(
    url: str,
    payload: Mapping[str, object],
    timeout: int = 20,
    headers: dict[str, str] | None = None,
    cookie_store: CookieStore | None = None,
) -> dict:
    request_headers = _merge_headers(headers)
    request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=request_headers,
    )
    with _http_open(request, timeout, cookie_store=cookie_store) as response:
        raw = response.read().decode()
        parsed = json.loads(raw)
        keys = list(parsed)[:8] if isinstance(parsed, dict) else type(parsed).__name__
        debug(f"POST <- {response.status} {_redact_url(response.url)} ({len(raw)} bytes, keys={keys})")
        if not isinstance(parsed, dict):
            raise TypeError(f"Réponse JSON inattendue: {type(parsed).__name__}")
        return parsed
