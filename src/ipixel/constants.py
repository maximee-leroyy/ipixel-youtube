"""Shared constants: brand palette, YouTube endpoints, BLE errors."""

from __future__ import annotations

from bleak.exc import BleakError

BLE_ERRORS = (BleakError, OSError, RuntimeError, TimeoutError, ConnectionError)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3/channels"
INNERTUBE_RESOLVE = "https://www.youtube.com/youtubei/v1/navigation/resolve_url?prettyPrint=false"
INNERTUBE_BROWSE = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"
MIXERNO_API = "https://mixerno.space/api/youtube-channel-counter/user/{channel_id}"
SOCIALCOUNTS_API = "https://api.socialcounts.org/youtube-live-subscriber-count/{channel_id}"
STUDIO_ORIGIN = "https://studio.youtube.com"
STUDIO_CHANNELS_API = "https://studio.youtube.com/youtubei/v1/creator/get_creator_channels?alt=json"
STUDIO_ANALYTICS_API = "https://studio.youtube.com/youtubei/v1/yta_web/get_screen?alt=json"
INNERTUBE_CONTEXT = {
    "client": {
        "hl": "en",
        "gl": "US",
        "clientName": "WEB",
        "clientVersion": "2.20240815.00.00",
    }
}
STUDIO_COOKIE_NAMES = ("SAPISID", "__Secure-1PAPISID", "__Secure-3PAPISID")
STUDIO_SESSION_TTL_S = 8 * 60
WEB_CREATOR_CLIENT_NAME = "62"
STUDIO_SUBSCRIBER_KEYS = {
    "subscriberCount",
    "totalSubscriberCount",
    "currentSubscriberCount",
    "subscribers",
}
COOKIE_HELP = """\
The exact number (YouTube Studio → Current subscribers) is not public.
You need the channel owner's session.

1. Sign in to https://studio.youtube.com with the channel's account
2. Export the cookies (Chrome extension "Get cookies.txt LOCALLY")
3. Save the cookies.txt file at the project root
4. Run again: ipixel-youtube --cookies cookies.txt

The script rewrites this file when Google sends new cookies.
Export again only after a logout, or if the script says the session expired.

Without cookies, you can still show the public estimate:
  ipixel-youtube --source live
"""
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

BRAND_BG = (0, 0, 0)
BRAND_WHITE = (255, 255, 255)
BRAND_CYAN = (0, 245, 255)
BRAND_YT_RED = (255, 0, 0)
BRAND_CAPTION = (200, 200, 208)
PixelColor = tuple[int, int, int]

# 13 px: play triangle 1-3-4-3-1 + rounded corners (RGBA + sobel=2).
YOUTUBE_LOGO_PYX_HEIGHT = 13
SHEEN_FRAME_MS = 100
SHEEN_FRAMES = 24
SHEEN_HALF_WIDTH = 3
DEFAULT_BRIGHTNESS = 100
