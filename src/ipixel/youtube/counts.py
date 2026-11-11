"""Public and official subscriber-count sources."""

from __future__ import annotations

import urllib.error
import urllib.parse

from ipixel.constants import MIXERNO_API, SOCIALCOUNTS_API, YOUTUBE_API
from ipixel.log import log
from ipixel.youtube.channel import is_channel_id
from ipixel.youtube.http import http_get_json
from ipixel.youtube.studio import fetch_studio_count


def format_count(count: int) -> str:
    """Thousands separators below 1 million (1.902). No dots at 1.000.000+."""
    if count >= 1_000_000:
        return str(count)
    return f"{count:,}".replace(",", ".")


def format_panel_count(count: int) -> str:
    """Compact enough for 32×32: 5×7 below 1M, digits to 8 figures, then 513.3M."""
    if count >= 1_000_000_000:
        text = f"{count / 1_000_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}B"
    if count >= 100_000_000:
        text = f"{count / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    return format_count(count)


def fetch_live_count(channel_id: str) -> int:
    """Same approach as public live counters: Mixerno, then SocialCounts."""
    errors: list[str] = []

    try:
        payload = http_get_json(SOCIALCOUNTS_API.format(channel_id=channel_id))
        counters = payload.get("counters") or {}
        estimation = counters.get("estimation") or {}
        if "subscriberCount" in estimation:
            count = int(estimation["subscriberCount"])
            log.debug(f"SocialCounts estimation={count}")
            return count
        if "est_sub" in payload:
            count = int(payload["est_sub"])
            log.debug(f"SocialCounts est_sub={count}")
            return count
        errors.append("SocialCounts: subscriberCount field missing")
        log.debug("SocialCounts: subscriberCount field missing")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"SocialCounts: {exc}")

    try:
        payload = http_get_json(MIXERNO_API.format(channel_id=channel_id))
        for item in payload.get("counts") or []:
            if item.get("value") == "subscribers":
                count = int(item["count"])
                log.debug(f"Mixerno subscribers={count}")
                return count
        errors.append("Mixerno: subscribers field missing")
        log.debug("Mixerno: subscribers field missing")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Mixerno: {exc}")

    raise RuntimeError("Live counters unreachable: " + " | ".join(errors))


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
        raise RuntimeError(f"Channel not found: {channel!r}. Check the ID (UCxxxx) or the handle (@name).")

    stats = items[0].get("statistics") or {}
    if stats.get("hiddenSubscriberCount"):
        raise RuntimeError("This channel's subscriber count is hidden.")

    count = stats.get("subscriberCount")
    if count is None:
        raise RuntimeError("The API did not return a subscriberCount.")
    official = int(count)
    log.debug(f"official subscriberCount={official} hidden={stats.get('hiddenSubscriberCount')}")
    return official


def fetch_count(
    source: str,
    *,
    channel: str,
    channel_id: str,
    api_key: str | None,
    cookies_path: str,
) -> int:
    log.debug(f"fetch_count source={source} channel={channel} channel_id={channel_id}")
    if source == "studio":
        return fetch_studio_count(channel_id, cookies_path)
    if source == "official":
        if api_key is None:
            raise RuntimeError("YouTube API key missing.")
        return fetch_official_count(api_key, channel)
    return fetch_live_count(channel_id)
