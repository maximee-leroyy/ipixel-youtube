"""Resolve a YouTube handle to a channel ID and title."""

from __future__ import annotations

import re
import urllib.error

from ipixel.constants import INNERTUBE_BROWSE, INNERTUBE_CONTEXT, INNERTUBE_RESOLVE
from ipixel.debug import debug
from ipixel.youtube.http import http_get_text, http_post_json

CHANNEL_ID_RE = re.compile(r"UC[\w-]{22}")


def is_channel_id(channel: str) -> bool:
    return bool(CHANNEL_ID_RE.fullmatch(channel))


def _id_from_innertube(handle: str) -> str | None:
    payload = {
        "context": INNERTUBE_CONTEXT,
        "url": f"https://www.youtube.com/{handle}",
    }
    data = http_post_json(INNERTUBE_RESOLVE, payload)
    browse_id = data.get("endpoint", {}).get("browseEndpoint", {}).get("browseId")
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

    raise RuntimeError(f"Impossible de résoudre {channel!r} en ID de chaîne (UCxxxx). " + " | ".join(errors))


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
