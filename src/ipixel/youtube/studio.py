"""YouTube Studio session + exact subscriber extraction."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from ipixel.constants import (
    COOKIE_HELP,
    STUDIO_ANALYTICS_API,
    STUDIO_CHANNELS_API,
    STUDIO_ORIGIN,
    STUDIO_SESSION_TTL_S,
    STUDIO_SUBSCRIBER_KEYS,
    USER_AGENT,
    WEB_CREATOR_CLIENT_NAME,
)
from ipixel.debug import debug
from ipixel.youtube.cookies import CookieStore, cookie_store, studio_headers
from ipixel.youtube.http import (
    _http_error_is_login,
    http_error_detail,
    http_get_text,
    http_post_json,
    studio_html_opener,
)


def _ytcfg_field(html: str, key: str) -> str | None:
    match = re.search(rf'"{re.escape(key)}":"([^"]+)"', html)
    return match.group(1) if match else None


def looks_publicly_rounded(count: int) -> bool:
    """YouTube Data API rounds counts ≥ 1000 to three significant figures."""
    if count < 1000:
        return False
    return len(str(count).rstrip("0")) <= 3


def _as_positive_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        if digits:
            number = int(digits)
            return number if number > 0 else None
    return None


def _json_at_marker(html: str, marker: str) -> object | None:
    idx = html.find(marker)
    if idx < 0:
        return None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(html[idx + len(marker) :].lstrip())
    except json.JSONDecodeError:
        return None
    return parsed


def studio_session_ok(html: str, final_url: str) -> bool:
    if "accounts.google.com" in final_url:
        return False
    if _ytcfg_field(html, "CHANNEL_ID"):
        return True
    return bool(re.search(r'"LOGGED_IN"\s*:\s*true', html))


def extract_lifetime_subscribers(payload: object) -> int | None:
    stack: list[object] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            lifetime = node.get("lifetimeSubsData")
            if isinstance(lifetime, dict):
                for column in lifetime.get("metricColumns") or []:
                    if not isinstance(column, dict):
                        continue
                    counts = column.get("counts")
                    values = counts.get("values") if isinstance(counts, dict) else None
                    if isinstance(values, list) and values:
                        count = _as_positive_int(values[0])
                        if count is not None:
                            return count
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


def extract_studio_subscriber_count(payload: object, channel_id: str | None = None) -> int | None:
    if isinstance(payload, dict):
        channels = payload.get("channels")
        if isinstance(channels, list):
            for channel in channels:
                if not isinstance(channel, dict):
                    continue
                if channel_id and channel.get("channelId") not in {None, channel_id}:
                    continue
                metric = channel.get("metric")
                if isinstance(metric, dict):
                    count = _as_positive_int(metric.get("subscriberCount"))
                    if count is not None:
                        return count

    found: list[int] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in STUDIO_SUBSCRIBER_KEYS:
                    count = _as_positive_int(value)
                    if count is not None:
                        found.append(count)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    if not found:
        return None
    exact = [count for count in found if not looks_publicly_rounded(count)]
    return exact[0] if exact else found[0]


def _studio_context(html: str, channel_id: str) -> tuple[dict[str, object], str, str | None]:
    parsed = _json_at_marker(html, '"INNERTUBE_CONTEXT":')
    if isinstance(parsed, dict):
        context: dict[str, object] = parsed
    else:
        client_version = _ytcfg_field(html, "INNERTUBE_CLIENT_VERSION") or "1.20240820.01.00"
        visitor = _ytcfg_field(html, "VISITOR_DATA")
        client: dict[str, object] = {
            "hl": "fr",
            "gl": "FR",
            "clientName": "WEB_CREATOR",
            "clientVersion": client_version,
            "userAgent": USER_AGENT,
        }
        if visitor:
            client["visitorData"] = visitor
        context = {
            "client": client,
            "user": {"lockedSafetyMode": False},
        }

    user_obj = context.get("user")
    user: dict[str, object] = dict(user_obj) if isinstance(user_obj, dict) else {}
    delegated = _ytcfg_field(html, "DELEGATED_SESSION_ID")
    if delegated:
        user["onBehalfOfUser"] = delegated
    context["user"] = user
    studio_channel = _ytcfg_field(html, "CHANNEL_ID") or channel_id
    return context, studio_channel, _ytcfg_field(html, "INNERTUBE_API_KEY")


def _studio_payload(context: dict[str, object], channel_id: str) -> dict[str, object]:
    return {
        "context": context,
        "channelIds": [channel_id],
        "criticalRead": True,
        "delegationContext": {
            "externalChannelId": channel_id,
            "roleType": {"channelRoleType": "CREATOR_CHANNEL_ROLE_TYPE_OWNER"},
        },
        "mask": {
            "channelId": True,
            "title": True,
            "channelHandle": True,
            "metric": {"all": True},
        },
    }


def _default_studio_context() -> dict[str, object]:
    return {
        "client": {
            "hl": "fr",
            "gl": "FR",
            "clientName": "WEB_CREATOR",
            "clientVersion": "1.20240820.01.00",
            "userAgent": USER_AGENT,
        },
        "user": {"lockedSafetyMode": False},
    }


def _studio_api_url(endpoint: str, api_key: str | None) -> str:
    if not api_key:
        return endpoint
    return f"{endpoint}&key={urllib.parse.quote(api_key)}"


@dataclass
class StudioSession:
    store: CookieStore
    auth_user: str
    context: dict[str, object]
    query_id: str
    api_key: str | None
    html: str
    loaded_at: float

    def api_headers(self) -> dict[str, str]:
        headers = studio_headers(self.store.as_dict(), auth_user=self.auth_user)
        client = self.context.get("client")
        if isinstance(client, dict):
            version = client.get("clientVersion")
            if isinstance(version, str) and version:
                headers["X-YouTube-Client-Version"] = version
            if client.get("clientName") == "WEB_CREATOR":
                headers["X-YouTube-Client-Name"] = WEB_CREATOR_CLIENT_NAME
        return headers


_studio_sessions: dict[str, StudioSession] = {}


def _probe_studio_session(session: StudioSession) -> bool:
    try:
        data = http_post_json(
            _studio_api_url(STUDIO_ANALYTICS_API, session.api_key),
            {
                "context": session.context,
                "screenConfig": {
                    "entity": {"channelId": session.query_id},
                    "screenId": "channel_analytics_overview",
                },
            },
            headers=session.api_headers(),
            cookie_store=session.store,
        )
    except urllib.error.HTTPError as exc:
        debug(f"studio probe auth_user={session.auth_user} HTTP {exc.code}")
        try:
            exc.read()
        except OSError:
            pass
        return False
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError) as exc:
        debug(f"studio probe auth_user={session.auth_user}: {exc}")
        return False
    if isinstance(data.get("error"), dict):
        return False
    return extract_lifetime_subscribers(data) is not None or "responseContext" in data


def _api_only_studio_session(
    channel_id: str,
    store: CookieStore,
) -> StudioSession | None:
    context = _default_studio_context()
    for auth_user in ("0", "1", "2", "3", "4", "5", "6"):
        session = StudioSession(
            store=store,
            auth_user=auth_user,
            context=context,
            query_id=channel_id,
            api_key=None,
            html="",
            loaded_at=time.time(),
        )
        if _probe_studio_session(session):
            debug(f"studio API-only session auth_user={auth_user}")
            return session
    return None


def load_studio_session(
    channel_id: str,
    cookies_path: str,
    *,
    force: bool = False,
) -> StudioSession:
    path = Path(cookies_path)
    if not path.is_file():
        raise RuntimeError(f"Fichier cookies introuvable: {cookies_path}\n\n{COOKIE_HELP}")

    store = cookie_store(cookies_path)
    cached = _studio_sessions.get(cookies_path)
    if cached is not None and not force and (time.time() - cached.loaded_at) < STUDIO_SESSION_TTL_S:
        debug(f"studio session cache age={int(time.time() - cached.loaded_at)}s")
        return cached

    html = ""
    final_url = STUDIO_ORIGIN + "/"
    try:
        html, final_url = http_get_text(
            STUDIO_ORIGIN + "/",
            headers=studio_headers(store.as_dict()),
            opener=studio_html_opener(),
            cookie_store=store,
        )
    except urllib.error.HTTPError as exc:
        login = _http_error_is_login(exc)
        detail = http_error_detail(exc)
        debug(f"studio HTML {detail} login={login}")
        if cached is not None:
            debug("studio HTML failed, reuse session cache")
            return cached
        html = ""

    logged_in = bool(html) and studio_session_ok(html, final_url)
    debug(
        f"studio session url={final_url} html={len(html)} bytes "
        f"logged_in={logged_in} channel={_ytcfg_field(html, 'CHANNEL_ID') if html else None} "
        f"service_login_in_html={'ServiceLogin' in html}"
    )
    if logged_in:
        auth_user = _ytcfg_field(html, "SESSION_INDEX") or "0"
        context, query_id, api_key = _studio_context(html, channel_id)
        client = context.get("client")
        client_version = client.get("clientVersion") if isinstance(client, dict) else None
        debug(
            f"studio ytcfg query_id={query_id} session_index={auth_user} "
            f"api_key={'oui' if api_key else 'non'} client={client_version} "
            f"delegated={'oui' if _ytcfg_field(html, 'DELEGATED_SESSION_ID') else 'non'}"
        )
        session = StudioSession(
            store=store,
            auth_user=auth_user,
            context=context,
            query_id=query_id,
            api_key=api_key,
            html=html,
            loaded_at=time.time(),
        )
        _studio_sessions[cookies_path] = session
        return session

    api_session = _api_only_studio_session(channel_id, store)
    if api_session is not None:
        _studio_sessions[cookies_path] = api_session
        return api_session
    if cached is not None:
        return cached
    raise RuntimeError("Session YouTube Studio expirée ou cookies invalides.\n\n" + COOKIE_HELP)


def _studio_count_from_apis(session: StudioSession, errors: list[str]) -> int | None:
    context = session.context
    query_id = session.query_id
    api_key = session.api_key

    analytics_payload: dict[str, object] = {
        "context": context,
        "screenConfig": {
            "entity": {"channelId": query_id},
            "screenId": "channel_analytics_overview",
        },
    }
    try:
        data = http_post_json(
            _studio_api_url(STUDIO_ANALYTICS_API, api_key),
            analytics_payload,
            headers=session.api_headers(),
            cookie_store=session.store,
        )
        count = extract_lifetime_subscribers(data)
        debug(
            f"analytics lifetime_subs={count} "
            f"looks_rounded={looks_publicly_rounded(count) if count is not None else None}"
        )
        # lifetimeSubsData is the Studio owner metric. 1100 can be the real count.
        if count is not None:
            debug(f"count source=analytics value={count}")
            return count
        errors.append("analytics: Abonnés actuels absent")
    except urllib.error.HTTPError as exc:
        detail = http_error_detail(exc)
        debug(f"analytics HTTP {detail}")
        errors.append(f"analytics HTTP {detail}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError) as exc:
        debug(f"analytics: {exc}")
        errors.append(f"analytics: {exc}")

    for endpoint, payload in (
        (
            STUDIO_CHANNELS_API,
            _studio_payload(context, query_id),
        ),
    ):
        name = endpoint.split("/")[-1]
        try:
            data = http_post_json(
                _studio_api_url(endpoint, api_key),
                payload,
                headers=session.api_headers(),
                cookie_store=session.store,
            )
        except urllib.error.HTTPError as exc:
            detail = http_error_detail(exc)
            debug(f"{name} HTTP {detail}")
            errors.append(f"{name} HTTP {detail}")
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError) as exc:
            debug(f"{name}: {exc}")
            errors.append(f"{name}: {exc}")
            continue
        count = extract_studio_subscriber_count(data, query_id)
        debug(
            f"{name} subscriberCount={count} "
            f"looks_rounded={looks_publicly_rounded(count) if count is not None else None}"
        )
        if count is not None:
            debug(f"count source={name} value={count}")
            return count
        errors.append(f"{name}: subscriberCount absent")
    return None


def fetch_studio_count(channel_id: str, cookies_path: str) -> int:
    session = load_studio_session(channel_id, cookies_path)
    errors: list[str] = []
    count = _studio_count_from_apis(session, errors)
    if count is not None:
        return count

    http_fail = any("HTTP 401" in err or "HTTP 403" in err for err in errors)
    if http_fail:
        debug("studio APIs HTTP error, refresh session")
        session = load_studio_session(channel_id, cookies_path, force=True)
        errors = []
        count = _studio_count_from_apis(session, errors)
        if count is not None:
            return count

    embedded = extract_studio_subscriber_count(
        _extract_embedded_json(session.html),
        session.query_id,
    )
    debug(
        f"html embedded subscriberCount={embedded} "
        f"rounded={looks_publicly_rounded(embedded) if embedded is not None else None}"
    )
    if embedded is not None and not looks_publicly_rounded(embedded):
        debug(f"count source=html value={embedded}")
        return embedded

    debug(f"studio échec: {' | '.join(errors)}")
    raise RuntimeError("Impossible de lire le nombre exact depuis YouTube Studio. " + " | ".join(errors))


def _extract_embedded_json(html: str) -> dict[str, object]:
    blob: dict[str, object] = {}
    for pattern in (
        r"ytcfg\.set\(({.*?})\);",
        r"ytInitialData\s*=\s*({.*?});",
    ):
        match = re.search(pattern, html, flags=re.DOTALL)
        if not match:
            continue
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blob.update(parsed)
    return blob
