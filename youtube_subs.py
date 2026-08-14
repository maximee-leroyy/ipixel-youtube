#!/usr/bin/env python3
"""Display a live YouTube subscriber count on an iPixel Color LED matrix.

The exact Studio figure (Abonnés actuels) is owner-only. Public live
counters interpolate between YouTube's rounded API value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from http.client import HTTPResponse
from io import BytesIO
from pathlib import Path

import pypixelcolor
from bleak.exc import BleakError
from PIL import Image, ImageDraw

BLE_ERRORS = (BleakError, OSError, RuntimeError, TimeoutError, ConnectionError)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3/channels"
INNERTUBE_RESOLVE = "https://www.youtube.com/youtubei/v1/navigation/resolve_url?prettyPrint=false"
INNERTUBE_BROWSE = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"
MIXERNO_API = "https://mixerno.space/api/youtube-channel-counter/user/{channel_id}"
SOCIALCOUNTS_API = "https://api.socialcounts.org/youtube-live-subscriber-count/{channel_id}"
STUDIO_ORIGIN = "https://studio.youtube.com"
STUDIO_CHANNELS_API = (
    "https://studio.youtube.com/youtubei/v1/creator/get_creator_channels?alt=json"
)
STUDIO_DASHBOARD_API = (
    "https://studio.youtube.com/youtubei/v1/creator/get_channel_dashboard?alt=json"
)
STUDIO_ANALYTICS_API = (
    "https://studio.youtube.com/youtubei/v1/yta_web/get_screen?alt=json"
)
INNERTUBE_CONTEXT = {
    "client": {
        "hl": "en",
        "gl": "US",
        "clientName": "WEB",
        "clientVersion": "2.20240815.00.00",
    }
}
STUDIO_COOKIE_NAMES = ("SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID")
STUDIO_SUBSCRIBER_KEYS = {
    "subscriberCount",
    "totalSubscriberCount",
    "currentSubscriberCount",
    "subscribers",
}
COOKIE_HELP = """\
Le chiffre exact (YouTube Studio → Abonnés actuels) n'est pas public.
Il faut la session du propriétaire de la chaîne.

1. Connecte-toi à https://studio.youtube.com avec le compte RYXACORE
2. Exporte les cookies (extension Chrome « Get cookies.txt LOCALLY »)
3. Enregistre le fichier cookies.txt à la racine du projet
4. Relance : python youtube_subs.py --cookies cookies.txt

Sans cookies, tu peux encore afficher l'estimation publique :
  python youtube_subs.py --source live
"""
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CHANNEL_ID_RE = re.compile(r"UC[\w-]{22}")

# Palette RYXACORE, poussée à fond pour rester lisible sur LED.
BRAND_BG = (0, 0, 0)
BRAND_WHITE = (255, 255, 255)
BRAND_CYAN = (0, 245, 255)
PixelColor = tuple[int, int, int]
DEBUG = False


def set_debug(enabled: bool) -> None:
    global DEBUG
    DEBUG = enabled


def debug(message: str) -> None:
    if DEBUG:
        print(f"debug: {message}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Affiche le nombre d'abonnés YouTube en live sur un iPixel Color."
    )
    parser.add_argument(
        "--address",
        default=os.environ.get("IPIXEL_ADDRESS", "00000000-0000-0000-0000-000000000000"),
        help="Adresse Bluetooth du panneau. "
        "Ou variable d'environnement IPIXEL_ADDRESS. "
        "Trouve-la avec: python -m pypixelcolor --scan",
    )
    parser.add_argument(
        "--channel",
        default=os.environ.get(
            "YOUTUBE_CHANNEL",
            os.environ.get("YOUTUBE_CHANNEL_ID", "@example"),
        ),
        help="ID de chaîne (UCxxxx) ou handle (@maChaine). "
        "Ou variable YOUTUBE_CHANNEL.",
    )
    parser.add_argument(
        "--source",
        choices=("studio", "live", "official"),
        default="studio",
        help="studio = chiffre exact YouTube Studio (cookies du propriétaire). "
        "live = estimation Mixerno/SocialCounts. "
        "official = YouTube Data API arrondie (--api-key).",
    )
    parser.add_argument(
        "--cookies",
        default=os.environ.get("YOUTUBE_COOKIES", "cookies.txt"),
        help="Fichier cookies Netscape (session YouTube Studio). "
        "Ou variable YOUTUBE_COOKIES.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("YOUTUBE_API_KEY"),
        help="Clé API YouTube Data v3, seulement pour --source official.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Secondes entre deux requêtes (défaut: 15).",
    )
    parser.add_argument(
        "--color",
        default=None,
        help="Override couleur accent hex. Défaut: palette RYXACORE (bleu/violet/cyan).",
    )
    parser.add_argument(
        "--font",
        default="CUSONG",
        help="Police: CUSONG, SIMSUN ou VCR_OSD_MONO (défaut: CUSONG, plus lisible en 32x32).",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("YOUTUBE_CHANNEL_NAME"),
        help="Nom affiché en haut du panneau. Par défaut: le vrai nom YouTube (RYXACORE).",
    )
    parser.add_argument(
        "--save-slot",
        type=int,
        default=1,
        help="Slot 1-10 pour garder l'affichage après déconnexion (défaut: 1). 0 = ne pas sauver.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Génère une simu 32x32 (preview_32x32.png + preview_led.png) sans Bluetooth.",
    )
    parser.add_argument(
        "--preview-count",
        default="1093",
        help="Nombre affiché en mode --preview (défaut: 1093).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Affiche une seule fois puis quitte (le texte reste si --save-slot >= 1).",
    )
    parser.add_argument(
        "--print-count",
        action="store_true",
        help="Affiche le nombre d'abonnés dans le terminal, sans Bluetooth.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("YOUTUBE_DEBUG", "").lower() in {"1", "true", "yes"},
        help="Logs détaillés sur stderr (HTTP, session Studio, extraction). "
        "Ou variable YOUTUBE_DEBUG=1.",
    )
    return parser.parse_args()


def _merge_headers(extra: dict[str, str] | None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if extra:
        headers.update(extra)
    return headers


def _redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "...") if key.lower() in {"key", "access_token", "token"} else (key, value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(redacted), parsed.fragment)
    )


def _http_open(request: urllib.request.Request, timeout: int) -> HTTPResponse:
    debug(f"{request.get_method()} {_redact_url(request.full_url)}")
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        debug(f"HTTP {exc.code} {_redact_url(exc.url or request.full_url)}")
        raise


def http_get_text(
    url: str,
    timeout: int = 20,
    headers: dict[str, str] | None = None,
) -> tuple[str, str]:
    request = urllib.request.Request(url, headers=_merge_headers(headers))
    with _http_open(request, timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        final_url = response.url
        debug(f"GET <- {response.status} {final_url} ({len(body)} bytes)")
        return body, final_url


def http_get_json(
    url: str,
    timeout: int = 15,
    headers: dict[str, str] | None = None,
) -> dict:
    request = urllib.request.Request(url, headers=_merge_headers(headers))
    with _http_open(request, timeout) as response:
        raw = response.read().decode()
        debug(f"GET <- {response.status} {_redact_url(response.url)} ({len(raw)} bytes)")
        return json.loads(raw)


def http_post_json(
    url: str,
    payload: Mapping[str, object],
    timeout: int = 20,
    headers: dict[str, str] | None = None,
) -> dict:
    request_headers = _merge_headers(headers)
    request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=request_headers,
    )
    with _http_open(request, timeout) as response:
        raw = response.read().decode()
        parsed = json.loads(raw)
        keys = list(parsed)[:8] if isinstance(parsed, dict) else type(parsed).__name__
        debug(
            f"POST <- {response.status} {_redact_url(response.url)} "
            f"({len(raw)} bytes, keys={keys})"
        )
        if not isinstance(parsed, dict):
            raise TypeError(f"Réponse JSON inattendue: {type(parsed).__name__}")
        return parsed


def is_channel_id(channel: str) -> bool:
    return bool(CHANNEL_ID_RE.fullmatch(channel))


def _id_from_innertube(handle: str) -> str | None:
    payload = {
        "context": INNERTUBE_CONTEXT,
        "url": f"https://www.youtube.com/{handle}",
    }
    data = http_post_json(INNERTUBE_RESOLVE, payload)
    browse_id = (
        data.get("endpoint", {})
        .get("browseEndpoint", {})
        .get("browseId")
    )
    if isinstance(browse_id, str) and is_channel_id(browse_id):
        debug(f"resolve innertube {handle} -> {browse_id}")
        return browse_id
    debug(f"resolve innertube {handle}: browseId absent")
    return None


def _id_from_channel_page(handle: str) -> str | None:
    html, _final_url = http_get_text(f"https://www.youtube.com/{handle}")

    for pattern in (
        r'"externalId":"(UC[\w-]{22})"',
        r'"browseId":"(UC[\w-]{22})"',
        r'"channelId":"(UC[\w-]{22})"',
        r"/channel/(UC[\w-]{22})",
    ):
        match = re.search(pattern, html)
        if match:
            debug(f"resolve page {handle} via {pattern} -> {match.group(1)}")
            return match.group(1)
    debug(f"resolve page {handle}: ID absent")
    return None


def resolve_channel_id(channel: str) -> str:
    if is_channel_id(channel):
        debug(f"resolve {channel}: déjà un ID")
        return channel

    handle = channel if channel.startswith("@") else f"@{channel.lstrip('/')}"
    errors: list[str] = []

    try:
        channel_id = _id_from_innertube(handle)
        if channel_id:
            return channel_id
        errors.append("Innertube: browseId absent")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError) as exc:
        errors.append(f"Innertube: {exc}")

    try:
        channel_id = _id_from_channel_page(handle)
        if channel_id:
            return channel_id
        errors.append("page YouTube: ID absent")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        errors.append(f"page YouTube: {exc}")

    raise RuntimeError(
        f"Impossible de résoudre {channel!r} en ID de chaîne (UCxxxx). "
        + " | ".join(errors)
    )


def fetch_channel_name(channel_id: str) -> str | None:
    payload = {"context": INNERTUBE_CONTEXT, "browseId": channel_id}
    data = http_post_json(INNERTUBE_BROWSE, payload)
    title = data.get("metadata", {}).get("channelMetadataRenderer", {}).get("title")
    if isinstance(title, str) and title.strip():
        debug(f"channel name metadata: {title.strip()}")
        return title.strip()
    page_title = data.get("header", {}).get("pageHeaderRenderer", {}).get("pageTitle")
    if isinstance(page_title, str) and page_title.strip():
        debug(f"channel name header: {page_title.strip()}")
        return page_title.strip()
    debug(f"channel name absent for {channel_id}")
    return None


def fetch_live_count(channel_id: str) -> int:
    """Same approach as public live counters: Mixerno, then SocialCounts."""
    errors: list[str] = []

    try:
        payload = http_get_json(SOCIALCOUNTS_API.format(channel_id=channel_id))
        counters = payload.get("counters") or {}
        estimation = counters.get("estimation") or {}
        if "subscriberCount" in estimation:
            count = int(estimation["subscriberCount"])
            debug(f"SocialCounts estimation={count}")
            return count
        if "est_sub" in payload:
            count = int(payload["est_sub"])
            debug(f"SocialCounts est_sub={count}")
            return count
        errors.append("SocialCounts: champ subscriberCount absent")
        debug("SocialCounts: champ subscriberCount absent")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"SocialCounts: {exc}")

    try:
        payload = http_get_json(MIXERNO_API.format(channel_id=channel_id))
        for item in payload.get("counts") or []:
            if item.get("value") == "subscribers":
                count = int(item["count"])
                debug(f"Mixerno subscribers={count}")
                return count
        errors.append("Mixerno: champ subscribers absent")
        debug("Mixerno: champ subscribers absent")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Mixerno: {exc}")

    raise RuntimeError("Compteurs live injoignables: " + " | ".join(errors))


def fetch_official_count(api_key: str, channel: str) -> int:
    params: dict[str, str] = {
        "part": "statistics",
        "key": api_key,
    }
    if is_channel_id(channel):
        params["id"] = channel
    else:
        handle = channel if channel.startswith("@") else f"@{channel}"
        params["forHandle"] = handle

    payload = http_get_json(f"{YOUTUBE_API}?{urllib.parse.urlencode(params)}")
    items = payload.get("items") or []
    if not items:
        raise RuntimeError(
            f"Chaîne introuvable: {channel!r}. Vérifie l'ID (UCxxxx) ou le handle (@nom)."
        )

    stats = items[0].get("statistics") or {}
    if stats.get("hiddenSubscriberCount"):
        raise RuntimeError("Le nombre d'abonnés de cette chaîne est masqué.")

    count = stats.get("subscriberCount")
    if count is None:
        raise RuntimeError("L'API n'a pas renvoyé de subscriberCount.")
    official = int(count)
    debug(f"official subscriberCount={official} hidden={stats.get('hiddenSubscriberCount')}")
    return official


def load_netscape_cookies(path: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    text = Path(path).read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        http_only = line.startswith("#HttpOnly_")
        if line.startswith("#") and not http_only:
            continue
        if http_only:
            line = line[len("#HttpOnly_") :]
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, _exp, name, value = parts[:7]
        host = domain.lstrip(".")
        if host.endswith(("youtube.com", "google.com")):
            cookies[name] = value
    if not cookies:
        raise RuntimeError(f"Aucun cookie YouTube/Google dans {path}.")
    present = [name for name in ("SAPISID", "__Secure-3PAPISID", "LOGIN_INFO", "SID") if name in cookies]
    debug(
        f"cookies {path}: {len(cookies)} noms, auth={present or 'aucun'}"
    )
    return cookies


def sapisid_from_cookies(cookies: dict[str, str]) -> str:
    for name in STUDIO_COOKIE_NAMES:
        value = cookies.get(name)
        if value:
            return value
    raise RuntimeError(
        "Cookie SAPISID absent. Réexporte les cookies depuis studio.youtube.com "
        "pendant que tu es connecté."
    )


def sapisid_hash(sapisid: str, origin: str = STUDIO_ORIGIN) -> str:
    timestamp = str(int(time.time()))
    digest = hashlib.sha1(f"{timestamp} {sapisid} {origin}".encode()).hexdigest()
    return f"{timestamp}_{digest}"


def studio_headers(
    cookies: dict[str, str],
    origin: str = STUDIO_ORIGIN,
    auth_user: str = "0",
) -> dict[str, str]:
    token = sapisid_hash(sapisid_from_cookies(cookies), origin)
    debug(f"studio headers origin={origin} auth_user={auth_user} sapisidhash_ts={token.split('_', 1)[0]}")
    return {
        "Authorization": f"SAPISIDHASH {token} SAPISID1PHASH {token} SAPISID3PHASH {token}",
        "Cookie": "; ".join(f"{name}={value}" for name, value in cookies.items()),
        "Origin": origin,
        "X-Origin": origin,
        "Referer": f"{origin}/",
        "X-Goog-AuthUser": auth_user,
    }


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


def _studio_api_url(endpoint: str, api_key: str | None) -> str:
    if not api_key:
        return endpoint
    return f"{endpoint}&key={urllib.parse.quote(api_key)}"


def fetch_studio_count(channel_id: str, cookies_path: str) -> int:
    if not Path(cookies_path).is_file():
        raise RuntimeError(f"Fichier cookies introuvable: {cookies_path}\n\n{COOKIE_HELP}")

    cookies = load_netscape_cookies(cookies_path)
    headers = studio_headers(cookies)
    html, final_url = http_get_text(STUDIO_ORIGIN + "/", headers=headers)
    logged_in = studio_session_ok(html, final_url)
    debug(
        f"studio session url={final_url} html={len(html)} bytes "
        f"logged_in={logged_in} channel={_ytcfg_field(html, 'CHANNEL_ID')} "
        f"service_login_in_html={'ServiceLogin' in html}"
    )
    if not logged_in:
        raise RuntimeError(
            "Session YouTube Studio expirée ou cookies invalides.\n\n" + COOKIE_HELP
        )

    auth_user = _ytcfg_field(html, "SESSION_INDEX") or "0"
    headers = studio_headers(cookies, auth_user=auth_user)
    context, query_id, api_key = _studio_context(html, channel_id)
    client = context.get("client")
    client_version = None
    if isinstance(client, dict):
        client_version = client.get("clientVersion")
    debug(
        f"studio ytcfg query_id={query_id} session_index={auth_user} "
        f"api_key={'oui' if api_key else 'non'} client={client_version} "
        f"delegated={'oui' if _ytcfg_field(html, 'DELEGATED_SESSION_ID') else 'non'}"
    )
    errors: list[str] = []

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
            headers=headers,
        )
        count = extract_lifetime_subscribers(data)
        debug(
            f"analytics lifetime_subs={count} "
            f"rounded={looks_publicly_rounded(count) if count is not None else None}"
        )
        if count is not None and not looks_publicly_rounded(count):
            debug(f"count source=analytics value={count}")
            return count
        if count is not None:
            errors.append(f"analytics: encore arrondi ({count})")
        else:
            errors.append("analytics: Abonnés actuels absent")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:300]
        debug(f"analytics HTTP {exc.code}: {body}")
        errors.append(f"analytics HTTP {exc.code}: {body}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError) as exc:
        debug(f"analytics: {exc}")
        errors.append(f"analytics: {exc}")

    for endpoint, payload in (
        (
            STUDIO_CHANNELS_API,
            _studio_payload(context, query_id),
        ),
        (
            STUDIO_DASHBOARD_API,
            {"context": context, "channelId": query_id},
        ),
    ):
        try:
            data = http_post_json(
                _studio_api_url(endpoint, api_key),
                payload,
                headers=headers,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            debug(f"{endpoint.split('/')[-1]} HTTP {exc.code}: {body}")
            errors.append(f"{endpoint.split('/')[-1]} HTTP {exc.code}: {body}")
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, TypeError) as exc:
            debug(f"{endpoint.split('/')[-1]}: {exc}")
            errors.append(f"{endpoint.split('/')[-1]}: {exc}")
            continue
        count = extract_studio_subscriber_count(data, query_id)
        debug(
            f"{endpoint.split('/')[-1]} subscriberCount={count} "
            f"rounded={looks_publicly_rounded(count) if count is not None else None}"
        )
        if count is not None and not looks_publicly_rounded(count):
            debug(f"count source={endpoint.split('/')[-1]} value={count}")
            return count
        if count is not None:
            errors.append(
                f"{endpoint.split('/')[-1]}: encore arrondi ({count}), pas le chiffre Studio"
            )
        else:
            errors.append(f"{endpoint.split('/')[-1]}: subscriberCount absent")

    embedded = extract_studio_subscriber_count(_extract_embedded_json(html), query_id)
    debug(
        f"html embedded subscriberCount={embedded} "
        f"rounded={looks_publicly_rounded(embedded) if embedded is not None else None}"
    )
    if embedded is not None and not looks_publicly_rounded(embedded):
        debug(f"count source=html value={embedded}")
        return embedded

    debug(f"studio échec: {' | '.join(errors)}")

    raise RuntimeError(
        "Impossible de lire le nombre exact depuis YouTube Studio. "
        + " | ".join(errors)
        + "\n\n"
        + COOKIE_HELP
    )


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


def fetch_count(
    source: str,
    *,
    channel: str,
    channel_id: str,
    api_key: str | None,
    cookies_path: str,
) -> int:
    debug(f"fetch_count source={source} channel={channel} channel_id={channel_id}")
    if source == "studio":
        return fetch_studio_count(channel_id, cookies_path)
    if source == "official":
        if api_key is None:
            raise RuntimeError("Clé API YouTube manquante.")
        return fetch_official_count(api_key, channel)
    return fetch_live_count(channel_id)


def format_count(count: int) -> str:
    return f"{count:,}".replace(",", " ")


# Police bitmap 5x7, trait de 1 px : lisible sur LED, trous ouverts (0 ≠ 8, A ≠ R).
FONT_5X7: dict[str, tuple[str, ...]] = {
    "0": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "2": (" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"),
    "3": (" ### ", "#   #", "    #", "  ## ", "    #", "#   #", " ### "),
    "4": ("   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "),
    "5": ("#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "),
    "6": (" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "),
    "8": (" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "),
    "9": (" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "),
    "C": (" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "),
    "D": ("#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "F": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "),
    "G": (" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ### "),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": (" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "J": ("  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#   #", "#### ", "#  # ", "#   #", "#   #"),
    "S": (" ### ", "#   #", "#    ", " ### ", "    #", "#   #", " ### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"),
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"),
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
    "?": (" ### ", "#   #", "    #", "  ## ", "  #  ", "     ", "  #  "),
}


def _name_lines(name: str) -> list[str]:
    compact = name.replace(" ", "").upper()
    if len(compact) <= 5:
        return [compact]
    mid = (len(compact) + 1) // 2
    return [compact[:mid], compact[mid:]]


def _parse_hex_color(color: str) -> PixelColor:
    color_bytes = bytes.fromhex(color)
    if len(color_bytes) != 3:
        raise ValueError("Color must be 3 bytes (6 hex chars), e.g. '00d4ff'")
    return (color_bytes[0], color_bytes[1], color_bytes[2])


def _glyph(char: str) -> tuple[str, ...]:
    return FONT_5X7.get(char.upper(), FONT_5X7["?"])


def _text_pixel_size(text: str, gap: int = 1) -> tuple[int, int]:
    if not text:
        return 0, 0
    glyphs = [_glyph(char) for char in text]
    width = sum(len(glyph[0]) for glyph in glyphs) + gap * (len(glyphs) - 1)
    height = len(glyphs[0])
    return width, height


def _blit_glyph(
    image: Image.Image,
    glyph: tuple[str, ...],
    origin_x: int,
    origin_y: int,
    color: PixelColor,
) -> None:
    pixels = image.load()
    if pixels is None:
        return
    width, height = image.size
    for row, line in enumerate(glyph):
        for col, cell in enumerate(line):
            if cell == " ":
                continue
            x = origin_x + col
            y = origin_y + row
            if 0 <= x < width and 0 <= y < height:
                pixels[x, y] = color


def _blit_text(
    image: Image.Image,
    text: str,
    top: int,
    color: PixelColor,
    gap: int = 2,
) -> None:
    glyphs = [_glyph(char) for char in text]
    total_w, _total_h = _text_pixel_size(text, gap)
    cursor = (image.width - total_w) // 2
    for glyph in glyphs:
        _blit_glyph(image, glyph, cursor, top, color)
        cursor += len(glyph[0]) + gap


def _draw_corners(image: Image.Image, color: PixelColor, size: int = 2) -> None:
    width, height = image.size
    pixels = image.load()
    if pixels is None:
        return
    for i in range(size):
        pixels[i, 0] = color
        pixels[0, i] = color
        pixels[width - 1 - i, 0] = color
        pixels[width - 1, i] = color
        pixels[i, height - 1] = color
        pixels[0, height - 1 - i] = color
        pixels[width - 1 - i, height - 1] = color
        pixels[width - 1, height - 1 - i] = color


def _draw_circuit_line(image: Image.Image, y: int, color: PixelColor) -> None:
    width, height = image.size
    if y <= 0 or y >= height:
        return
    pixels = image.load()
    if pixels is None:
        return
    left = 6
    right = width - 7
    for x in range(left, right + 1):
        pixels[x, y] = color
    pixels[left, y] = color
    pixels[right, y] = color


def render_matrix_png(
    name: str,
    count_text: str,
    width: int,
    height: int,
    color: str | None,
    font_name: str,
) -> bytes:
    del font_name
    accent = _parse_hex_color(color) if color else BRAND_CYAN
    image = Image.new("RGB", (width, height), BRAND_BG)
    name_lines = _name_lines(name)
    glyph_h = 7
    name_top = 2
    line_gap = 3
    for index, line in enumerate(name_lines):
        _blit_text(image, line, name_top + index * (glyph_h + line_gap), BRAND_WHITE)
    separator_y = name_top + len(name_lines) * glyph_h + (len(name_lines) - 1) * line_gap + 2
    _draw_circuit_line(image, separator_y, accent)
    count_top = separator_y + 3
    _blit_text(image, count_text, count_top, accent)
    _draw_corners(image, accent)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def simulate_led_matrix(image: Image.Image, scale: int = 18, gap: int = 3) -> Image.Image:
    """Upscale 32x32 with gaps so each pixel looks like an LED."""
    width, height = image.size
    canvas = Image.new("RGB", (width * scale, height * scale), (8, 8, 10))
    draw = ImageDraw.Draw(canvas)
    source = image.load()
    if source is None:
        return canvas
    inset = gap
    for y in range(height):
        for x in range(width):
            color = source[x, y]
            if not isinstance(color, tuple):
                continue
            x0 = x * scale + inset
            y0 = y * scale + inset
            x1 = (x + 1) * scale - inset - 1
            y1 = (y + 1) * scale - inset - 1
            draw.rounded_rectangle([x0, y0, x1, y1], radius=2, fill=color)
    return canvas


def write_preview(
    name: str,
    count_text: str,
    font_name: str,
    color: str | None,
    output_dir: str = ".",
) -> tuple[str, str]:
    png = render_matrix_png(name, count_text, 32, 32, color, font_name)
    native = Image.open(BytesIO(png)).convert("RGB")
    led = simulate_led_matrix(native)
    native_path = f"{output_dir}/preview_32x32.png"
    led_path = f"{output_dir}/preview_led.png"
    native.save(native_path)
    led.save(led_path)
    return native_path, led_path


def connect_device(address: str) -> pypixelcolor.Client:
    device = pypixelcolor.Client(address)
    device.connect()
    try:
        device.set_brightness(100)
    except BLE_ERRORS as exc:
        print(f"Luminosité: {exc}", file=sys.stderr)
    info = device.get_device_info()
    print(f"Connecté au panneau {info.width}x{info.height}")
    return device


def disconnect_device(device: pypixelcolor.Client) -> None:
    try:
        device.disconnect()
    except BLE_ERRORS as exc:
        print(f"Déconnexion Bluetooth: {exc}", file=sys.stderr)


def display_count(
    device: pypixelcolor.Client,
    name: str,
    count_text: str,
    *,
    color: str | None,
    font: str,
    save_slot: int,
) -> None:
    info = device.get_device_info()
    png = render_matrix_png(
        name,
        count_text,
        info.width,
        info.height,
        color,
        font,
    )
    device.send_image_hex(png.hex(), ".png", resize_method="fit", save_slot=save_slot)
    debug(f"BLE send_image {info.width}x{info.height} slot={save_slot} text={count_text}")
    if save_slot >= 1:
        device.show_slot(save_slot)


def main() -> int:
    args = parse_args()
    set_debug(args.debug)
    debug(
        f"start source={args.source} channel={args.channel} cookies={args.cookies} "
        f"print_count={args.print_count} once={args.once}"
    )

    if args.preview:
        channel_name = args.name or "RYXACORE"
        native_path, led_path = write_preview(
            channel_name, args.preview_count, args.font, args.color
        )
        print(f"Simu 32x32: {native_path}")
        print(f"Simu LED:   {led_path}")
        return 0

    missing = []
    api_key = args.api_key
    if not args.channel:
        missing.append("--channel ou YOUTUBE_CHANNEL")
    if args.source == "official" and api_key is None:
        missing.append("--api-key ou YOUTUBE_API_KEY")
    if args.source == "studio" and not Path(args.cookies).is_file():
        missing.append(f"--cookies ({args.cookies} introuvable)")
    if missing:
        print("Paramètres manquants: " + ", ".join(missing), file=sys.stderr)
        if args.source == "studio":
            print("\n" + COOKIE_HELP, file=sys.stderr)
        else:
            print(
                "\nExemple:\n"
                "  python youtube_subs.py --channel @taChaine",
                file=sys.stderr,
            )
        return 2

    try:
        channel_id = resolve_channel_id(args.channel)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Impossible de résoudre la chaîne: {exc}", file=sys.stderr)
        return 1

    channel_name = args.name
    if not channel_name:
        try:
            channel_name = fetch_channel_name(channel_id)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f"Nom de chaîne indisponible ({exc}), fallback handle.", file=sys.stderr)
    if not channel_name:
        channel_name = args.channel.lstrip("@")

    print(f"Chaîne: {channel_name} ({channel_id})")
    if args.source == "studio":
        print(f"Source: YouTube Studio (cookies {args.cookies})")
    elif args.source == "live":
        print("Source: estimation publique (pas le chiffre Studio).")

    if args.print_count:
        try:
            count = fetch_count(
                args.source,
                channel=args.channel,
                channel_id=channel_id,
                api_key=api_key,
                cookies_path=args.cookies,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            print(f"Erreur HTTP {exc.code}: {body}", file=sys.stderr)
            return 1
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
            print(f"Erreur: {exc}", file=sys.stderr)
            return 1
        print(f"{channel_name} {format_count(count)}")
        return 0

    device: pypixelcolor.Client | None = None
    last_count: int | None = None
    min_interval = 15 if args.source == "studio" else 5 if args.source == "live" else 10

    try:
        device = connect_device(args.address)

        while True:
            try:
                count = fetch_count(
                    args.source,
                    channel=args.channel,
                    channel_id=channel_id,
                    api_key=api_key,
                    cookies_path=args.cookies,
                )
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                print(f"Erreur HTTP {exc.code}: {body}", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
                print(f"Erreur: {exc}", file=sys.stderr)
            else:
                if count != last_count:
                    count_text = str(count)
                    print(f"{time.strftime('%H:%M:%S')}  {channel_name} {format_count(count)}")
                    try:
                        display_count(
                            device,
                            channel_name,
                            count_text,
                            color=args.color,
                            font=args.font,
                            save_slot=args.save_slot,
                        )
                    except BLE_ERRORS as exc:
                        print(f"Bluetooth perdu ({exc}), reconnexion...", file=sys.stderr)
                        disconnect_device(device)
                        device = connect_device(args.address)
                        display_count(
                            device,
                            channel_name,
                            count_text,
                            color=args.color,
                            font=args.font,
                            save_slot=args.save_slot,
                        )
                    last_count = count
                else:
                    print(f"{time.strftime('%H:%M:%S')}  inchangé ({count})")

            if args.once:
                break
            time.sleep(max(args.interval, min_interval))

    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        if device is not None:
            disconnect_device(device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
