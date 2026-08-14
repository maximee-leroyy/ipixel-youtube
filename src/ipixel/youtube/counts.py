"""Public and official subscriber-count sources."""

from __future__ import annotations

import urllib.error
import urllib.parse

from ipixel.constants import MIXERNO_API, SOCIALCOUNTS_API, YOUTUBE_API
from ipixel.debug import debug
from ipixel.youtube.channel import is_channel_id
from ipixel.youtube.http import http_get_json
from ipixel.youtube.studio import fetch_studio_count


def format_count(count: int) -> str:
    """Thousands separator for the panel and the terminal (1.902)."""
    return f"{count:,}".replace(",", ".")


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
        raise RuntimeError(f"Chaîne introuvable: {channel!r}. Vérifie l'ID (UCxxxx) ou le handle (@nom).")

    stats = items[0].get("statistics") or {}
    if stats.get("hiddenSubscriberCount"):
        raise RuntimeError("Le nombre d'abonnés de cette chaîne est masqué.")

    count = stats.get("subscriberCount")
    if count is None:
        raise RuntimeError("L'API n'a pas renvoyé de subscriberCount.")
    official = int(count)
    debug(f"official subscriberCount={official} hidden={stats.get('hiddenSubscriberCount')}")
    return official


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
