"""Netscape cookies.txt store for YouTube Studio sessions."""

from __future__ import annotations

import errno
import hashlib
import http.cookiejar
import time
import urllib.request
from http.client import HTTPResponse
from pathlib import Path
from typing import cast

from ipixel.constants import COOKIE_HELP, STUDIO_COOKIE_NAMES, STUDIO_ORIGIN
from ipixel.debug import debug

_cookie_stores: dict[str, CookieStore] = {}


def _cookie_host_ok(domain: str) -> bool:
    host = domain.lstrip(".").lower()
    return host.endswith(("youtube.com", "google.com"))


class _StudioCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Allow Google/YouTube Set-Cookie even when the request host is studio.youtube.com."""

    def set_ok_domain(self, cookie: http.cookiejar.Cookie, request: object) -> bool:
        del request
        return _cookie_host_ok(cookie.domain)


def _netscape_cookie(
    domain: str,
    path: str,
    secure: str,
    exp: str,
    name: str,
    value: str,
    httponly: bool,
) -> http.cookiejar.Cookie:
    initial_dot = domain.startswith(".")
    try:
        expires = int(exp) if exp else None
    except ValueError:
        expires = None
    discard = expires is None or expires == 0
    if expires == 0:
        expires = None
    return http.cookiejar.Cookie(
        0,
        name,
        value,
        None,
        False,
        domain,
        initial_dot,
        initial_dot,
        path or "/",
        True,
        secure.upper() == "TRUE",
        expires,
        discard,
        None,
        None,
        {"HttpOnly": ""} if httponly else {},
        False,
    )


def _iter_netscape_cookies(path: str) -> list[http.cookiejar.Cookie]:
    cookies: list[http.cookiejar.Cookie] = []
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        httponly = line.startswith("#HttpOnly_")
        if line.startswith("#") and not httponly:
            continue
        if httponly:
            line = line[len("#HttpOnly_") :]
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, cookie_path, secure, exp, name, value = parts[:7]
        if not _cookie_host_ok(domain):
            continue
        cookies.append(_netscape_cookie(domain, cookie_path, secure, exp, name, value, httponly))
    return cookies


class CookieStore:
    """Netscape cookies.txt that absorbs Set-Cookie and writes itself back."""

    def __init__(self, path: str) -> None:
        self.path = str(Path(path))
        self.jar = http.cookiejar.MozillaCookieJar(
            filename=self.path,
            policy=_StudioCookiePolicy(),
        )
        self._saved_mtime = 0.0
        self._load()

    def _load(self) -> None:
        path = Path(self.path)
        if not path.is_file():
            raise RuntimeError(f"Fichier cookies introuvable: {self.path}\n\n{COOKIE_HELP}")
        loaded = False
        try:
            self.jar.load(ignore_discard=True, ignore_expires=True)
            loaded = True
        except (OSError, http.cookiejar.LoadError, UnicodeError, ValueError):
            debug("cookies mozilla load failed, fallback parser")
        if not loaded or sum(1 for _ in self.jar) == 0:
            self.jar.clear()
            for cookie in _iter_netscape_cookies(self.path):
                self.jar.set_cookie(cookie)
        if sum(1 for _ in self.jar) == 0:
            raise RuntimeError(f"Aucun cookie YouTube/Google dans {self.path}.")
        present = [
            cookie.name for cookie in self.jar if cookie.name in {"SAPISID", "__Secure-3PAPISID", "LOGIN_INFO", "SID"}
        ]
        debug(f"cookies {self.path}: {sum(1 for _ in self.jar)} noms, auth={present or 'aucun'}")
        self._saved_mtime = path.stat().st_mtime

    def reload_if_externally_changed(self) -> None:
        path = Path(self.path)
        if not path.is_file():
            return
        mtime = path.stat().st_mtime
        if mtime <= self._saved_mtime:
            return
        debug(f"cookies reload from disk {self.path}")
        self.jar.clear()
        self._load()

    def as_dict(self) -> dict[str, str]:
        ranked: dict[str, tuple[int, str]] = {}
        now = time.time()
        for cookie in self.jar:
            if not _cookie_host_ok(cookie.domain):
                continue
            if cookie.expires is not None and cookie.expires > 0 and cookie.expires < now:
                continue
            value = cookie.value
            if value is None:
                continue
            rank = 2 if cookie.domain.lstrip(".").endswith("youtube.com") else 1
            previous = ranked.get(cookie.name)
            if previous is None or rank >= previous[0]:
                ranked[cookie.name] = (rank, value)
        return {name: value for name, (_rank, value) in ranked.items()}

    def _fingerprint(self) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            sorted(
                (cookie.domain, cookie.path, cookie.name, cookie.value)
                for cookie in self.jar
                if cookie.value is not None
            )
        )

    def absorb(self, request: urllib.request.Request, response: object) -> None:
        before = self._fingerprint()
        before_names = {(cookie.domain, cookie.path, cookie.name): cookie.value for cookie in self.jar}
        try:
            self.jar.extract_cookies(cast(HTTPResponse, response), request)
        except (AttributeError, OSError, ValueError):
            debug("cookies extract skipped")
            return
        if self._fingerprint() == before:
            return
        changed = [
            cookie.name
            for cookie in self.jar
            if before_names.get((cookie.domain, cookie.path, cookie.name)) != cookie.value
        ]
        debug(f"cookies refresh {', '.join(changed) or 'unknown'} -> {self.path}")
        self.save()

    def save(self) -> None:
        path = Path(self.path)
        tmp = path.with_name(path.name + ".tmp")
        self.jar.save(filename=str(tmp), ignore_discard=True, ignore_expires=True)
        try:
            tmp.replace(path)
        except OSError as exc:
            # Bind-mount d'un fichier (Docker/nerdctl) : rename vers le mountpoint = EBUSY.
            if exc.errno not in (errno.EBUSY, errno.EXDEV):
                tmp.unlink(missing_ok=True)
                raise
            path.write_bytes(tmp.read_bytes())
            tmp.unlink(missing_ok=True)
        self._saved_mtime = path.stat().st_mtime


def cookie_store(path: str) -> CookieStore:
    resolved = str(Path(path).resolve())
    store = _cookie_stores.get(resolved)
    if store is None:
        store = CookieStore(path)
        _cookie_stores[resolved] = store
    else:
        store.reload_if_externally_changed()
    return store


def load_netscape_cookies(path: str) -> dict[str, str]:
    return CookieStore(path).as_dict()


def sapisid_from_cookies(cookies: dict[str, str]) -> str:
    for name in STUDIO_COOKIE_NAMES:
        value = cookies.get(name)
        if value:
            return value
    raise RuntimeError(
        "Cookie SAPISID absent. Réexporte les cookies depuis studio.youtube.com pendant que tu es connecté."
    )


def sapisid_hash(sapisid: str, origin: str = STUDIO_ORIGIN) -> str:
    timestamp = str(int(time.time()))
    digest = hashlib.sha1(f"{timestamp} {sapisid} {origin}".encode()).hexdigest()
    return f"{timestamp}_{digest}"


def _cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def studio_page_headers(cookies: dict[str, str]) -> dict[str, str]:
    """Cookies only for the HTML page. SAPISIDHASH belongs on youtubei POSTs."""
    return {
        "Cookie": _cookie_header(cookies),
        "Referer": f"{STUDIO_ORIGIN}/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }


def studio_headers(
    cookies: dict[str, str],
    origin: str = STUDIO_ORIGIN,
    auth_user: str = "0",
) -> dict[str, str]:
    token = sapisid_hash(sapisid_from_cookies(cookies), origin)
    debug(f"studio headers origin={origin} auth_user={auth_user} sapisidhash_ts={token.split('_', 1)[0]}")
    return {
        "Authorization": f"SAPISIDHASH {token} SAPISID1PHASH {token} SAPISID3PHASH {token}",
        "Cookie": _cookie_header(cookies),
        "Origin": origin,
        "X-Origin": origin,
        "Referer": f"{origin}/",
        "X-Goog-AuthUser": auth_user,
    }
