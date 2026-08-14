#!/usr/bin/env python3
"""Display a live YouTube subscriber count on an iPixel Color LED matrix.

Live counters (Mixerno, SocialCounts) do not get YouTube Studio's exact
number. They interpolate between the official rounded API value. That is
what public "exact" live sub counters actually show.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO

import pypixelcolor
from bleak.exc import BleakError
from PIL import Image, ImageDraw

BLE_ERRORS = (BleakError, OSError, RuntimeError, TimeoutError, ConnectionError)

YOUTUBE_API = "https://www.googleapis.com/youtube/v3/channels"
INNERTUBE_RESOLVE = "https://www.youtube.com/youtubei/v1/navigation/resolve_url?prettyPrint=false"
INNERTUBE_BROWSE = "https://www.youtube.com/youtubei/v1/browse?prettyPrint=false"
MIXERNO_API = "https://mixerno.space/api/youtube-channel-counter/user/{channel_id}"
SOCIALCOUNTS_API = "https://api.socialcounts.org/youtube-live-subscriber-count/{channel_id}"
INNERTUBE_CONTEXT = {
    "client": {
        "hl": "en",
        "gl": "US",
        "clientName": "WEB",
        "clientVersion": "2.20240815.00.00",
    }
}
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
        choices=("live", "official"),
        default="live",
        help="live = estimation Mixerno/SocialCounts (comme les compteurs publics). "
        "official = YouTube Data API arrondie (nécessite --api-key).",
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
        default="1080",
        help="Nombre affiché en mode --preview (défaut: 1080).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Affiche une seule fois puis quitte (le texte reste si --save-slot >= 1).",
    )
    return parser.parse_args()


def http_get_json(url: str, timeout: int = 15) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def http_post_json(url: str, payload: dict, timeout: int = 15) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


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
        return browse_id
    return None


def _id_from_channel_page(handle: str) -> str | None:
    url = f"https://www.youtube.com/{handle}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")

    for pattern in (
        r'"externalId":"(UC[\w-]{22})"',
        r'"browseId":"(UC[\w-]{22})"',
        r'"channelId":"(UC[\w-]{22})"',
        r"/channel/(UC[\w-]{22})",
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def resolve_channel_id(channel: str) -> str:
    if is_channel_id(channel):
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
        return title.strip()
    page_title = data.get("header", {}).get("pageHeaderRenderer", {}).get("pageTitle")
    if isinstance(page_title, str) and page_title.strip():
        return page_title.strip()
    return None


def fetch_live_count(channel_id: str) -> int:
    """Same approach as public live counters: Mixerno, then SocialCounts."""
    errors: list[str] = []

    try:
        payload = http_get_json(SOCIALCOUNTS_API.format(channel_id=channel_id))
        counters = payload.get("counters") or {}
        estimation = counters.get("estimation") or {}
        if "subscriberCount" in estimation:
            return int(estimation["subscriberCount"])
        if "est_sub" in payload:
            return int(payload["est_sub"])
        errors.append("SocialCounts: champ subscriberCount absent")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"SocialCounts: {exc}")

    try:
        payload = http_get_json(MIXERNO_API.format(channel_id=channel_id))
        for item in payload.get("counts") or []:
            if item.get("value") == "subscribers":
                return int(item["count"])
        errors.append("Mixerno: champ subscribers absent")
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
    return int(count)


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
    if save_slot >= 1:
        device.show_slot(save_slot)


def main() -> int:
    args = parse_args()

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
    if missing:
        print("Paramètres manquants: " + ", ".join(missing), file=sys.stderr)
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

    device: pypixelcolor.Client | None = None
    last_count: int | None = None
    min_interval = 5 if args.source == "live" else 10

    try:
        device = connect_device(args.address)

        while True:
            try:
                if args.source == "live":
                    count = fetch_live_count(channel_id)
                else:
                    if api_key is None:
                        print("Clé API YouTube manquante.", file=sys.stderr)
                        return 2
                    count = fetch_official_count(api_key, args.channel)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode(errors="replace")
                print(f"Erreur HTTP {exc.code}: {body}", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
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
