"""Compose the 32×32 HUD: logo, count, name, corners, glass sheen."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from ipixel.assets import preview_dir
from ipixel.constants import (
    BRAND_BG,
    BRAND_CAPTION,
    BRAND_CYAN,
    BRAND_WHITE,
    DEFAULT_BRIGHTNESS,
    SHEEN_FRAME_MS,
    SHEEN_FRAMES,
    SHEEN_HALF_WIDTH,
    PixelColor,
)
from ipixel.display.fonts import FONT_4X5, _blit_text, _draw_corners, _name_lines, _text_pixel_size
from ipixel.display.logo import blit_logo, youtube_logo_sprite


def parse_hex_color(color: str) -> PixelColor:
    color_bytes = bytes.fromhex(color)
    if len(color_bytes) != 3:
        raise ValueError("Color must be 3 bytes (6 hex chars), e.g. '00d4ff'")
    return (color_bytes[0], color_bytes[1], color_bytes[2])


def render_matrix_image(
    name: str,
    count_text: str,
    width: int,
    height: int,
    color: str | None,
    font_name: str,
) -> Image.Image:
    del font_name
    accent = parse_hex_color(color) if color else BRAND_CYAN
    image = Image.new("RGB", (width, height), BRAND_BG)
    logo = youtube_logo_sprite()
    logo_w, logo_h = logo.size
    count_gap = 2 if _text_pixel_size(count_text, 2)[0] <= width - 4 else 1
    _, count_h = _text_pixel_size(count_text, count_gap)
    name_lines = _name_lines(name)
    label_h = 5
    label_gap_y = 1
    label_block = len(name_lines) * label_h + max(0, len(name_lines) - 1) * label_gap_y
    # The pyxelated pill already has 1 px of visual padding on top/bottom.
    gap_a = 0 if logo_h >= 13 else 1 if logo_h >= 10 else 2
    gap_b = 1 if logo_h >= 10 else 2
    block_h = logo_h + gap_a + count_h + gap_b + label_block
    top = max(0, (height - block_h) // 2)
    logo_y = top
    count_y = logo_y + logo_h + gap_a
    label_y = count_y + count_h + gap_b
    blit_logo(image, (width - logo_w) // 2, logo_y)
    _blit_text(image, count_text, count_y, accent, gap=count_gap)
    for index, line in enumerate(name_lines):
        _blit_text(
            image,
            line,
            label_y + index * (label_h + label_gap_y),
            BRAND_CAPTION,
            gap=1,
            font=FONT_4X5,
        )
    _draw_corners(image, accent)
    return image


def _mix_rgb(color: PixelColor, other: PixelColor, amount: float) -> PixelColor:
    amount = min(1.0, max(0.0, amount))
    return (
        int(color[0] + (other[0] - color[0]) * amount),
        int(color[1] + (other[1] - color[1]) * amount),
        int(color[2] + (other[2] - color[2]) * amount),
    )


def apply_glass_sheen(
    image: Image.Image,
    front: int,
    half_width: int = SHEEN_HALF_WIDTH,
) -> Image.Image:
    """Diagonal specular highlight across lit pixels only."""
    glazed = image.copy()
    pixels = glazed.load()
    if pixels is None:
        return glazed
    width, height = glazed.size
    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            if not isinstance(pixel, tuple):
                continue
            rgb = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
            if rgb[0] + rgb[1] + rgb[2] < 28:
                continue
            dist = abs(x + y - front)
            if dist > half_width:
                continue
            amount = 1.0 * (1.0 - dist / (half_width + 1))
            pixels[x, y] = _mix_rgb(rgb, BRAND_WHITE, amount)
    return glazed


def save_gif(frames: list[Image.Image], durations: list[int]) -> bytes:
    rgb_frames = [frame.convert("RGB") for frame in frames]
    width, height = rgb_frames[0].size
    sheet = Image.new("RGB", (width * len(rgb_frames), height))
    for index, frame in enumerate(rgb_frames):
        sheet.paste(frame, (index * width, 0))
    palette = sheet.quantize(
        colors=32,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    paletted = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in rgb_frames]
    buffer = BytesIO()
    paletted[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=paletted[1:],
        duration=durations,
        loop=0,
        disposal=1,
        optimize=False,
    )
    return buffer.getvalue()


def render_matrix_frames(
    name: str,
    count_text: str,
    width: int,
    height: int,
    color: str | None,
    font_name: str,
) -> tuple[list[Image.Image], list[int]]:
    base = render_matrix_image(name, count_text, width, height, color, font_name)
    frames: list[Image.Image] = []
    durations: list[int] = []
    first_front = -SHEEN_HALF_WIDTH
    last_front = width + height + SHEEN_HALF_WIDTH
    span = last_front - first_front
    for index in range(SHEEN_FRAMES):
        front = first_front + int(span * index / max(SHEEN_FRAMES - 1, 1))
        frames.append(apply_glass_sheen(base, front))
        durations.append(SHEEN_FRAME_MS)
    return frames, durations


def render_matrix_png(
    name: str,
    count_text: str,
    width: int,
    height: int,
    color: str | None,
    font_name: str,
) -> bytes:
    image = render_matrix_image(name, count_text, width, height, color, font_name)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_matrix_gif(
    name: str,
    count_text: str,
    width: int,
    height: int,
    color: str | None,
    font_name: str,
) -> bytes:
    """Idle loop: a glass sheen sweeps the widget, then rests."""
    frames, durations = render_matrix_frames(name, count_text, width, height, color, font_name)
    return save_gif(frames, durations)


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


def apply_brightness(image: Image.Image, level: int) -> Image.Image:
    """Scale RGB channels. 100 = unchanged, 0 = black."""
    amount = max(0, min(100, int(level))) / 100.0
    if amount >= 1.0:
        return image
    table = [int(channel * amount) for channel in range(256)]
    bands = image.getbands()
    return image.point(table * len(bands))


def write_preview(
    name: str,
    count_text: str,
    font_name: str,
    color: str | None,
    output_dir: str | Path | None = None,
    brightness: int = DEFAULT_BRIGHTNESS,
) -> tuple[str, str, str]:
    folder = preview_dir(output_dir)
    png = render_matrix_png(name, count_text, 32, 32, color, font_name)
    frames, durations = render_matrix_frames(name, count_text, 32, 32, color, font_name)
    native = apply_brightness(Image.open(BytesIO(png)).convert("RGB"), brightness)
    led = simulate_led_matrix(native)
    led_frames = [simulate_led_matrix(apply_brightness(frame.convert("RGB"), brightness)) for frame in frames]
    native_path = folder / "32x32.png"
    led_path = folder / "led.png"
    gif_path = folder / "preview.gif"
    native.save(native_path)
    led.save(led_path)
    gif_path.write_bytes(save_gif(led_frames, durations))
    return str(native_path), str(led_path), str(gif_path)
