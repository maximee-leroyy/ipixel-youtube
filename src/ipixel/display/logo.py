"""YouTube logo: SVG → pyxelate sprite for the 32×32 panel."""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

import numpy as np
import pymupdf
from PIL import Image
from pyxelate import Pyx

from ipixel.assets import brand_file
from ipixel.constants import (
    BRAND_BG,
    BRAND_WHITE,
    BRAND_YT_RED,
    YOUTUBE_LOGO_PYX_HEIGHT,
)


def _rgba(pixel: object) -> tuple[int, int, int, int]:
    if isinstance(pixel, tuple) and len(pixel) >= 4:
        return int(pixel[0]), int(pixel[1]), int(pixel[2]), int(pixel[3])
    if isinstance(pixel, tuple) and len(pixel) >= 3:
        return int(pixel[0]), int(pixel[1]), int(pixel[2]), 255
    return 0, 0, 0, 0


def _fill_logo_cutout(image: Image.Image) -> Image.Image:
    """Paint the SVG play-button hole white so it survives a black canvas."""
    filled = image.convert("RGBA").copy()
    width, height = filled.size
    pixels = filled.load()
    if pixels is None:
        return filled
    outside: set[tuple[int, int]] = set()
    stack = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    while stack:
        x, y = stack.pop()
        if (x, y) in outside or not (0 <= x < width and 0 <= y < height):
            continue
        _red, _green, _blue, alpha = _rgba(pixels[x, y])
        if alpha > 32:
            continue
        outside.add((x, y))
        stack.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    for y in range(height):
        for x in range(width):
            _red, _green, _blue, alpha = _rgba(pixels[x, y])
            if alpha > 32:
                pixels[x, y] = (*BRAND_YT_RED, 255)
            elif (x, y) not in outside:
                pixels[x, y] = (*BRAND_WHITE, 255)
            else:
                pixels[x, y] = (0, 0, 0, 0)
    return filled


def _array_to_image(pixels: object) -> Image.Image:
    result = np.asarray(pixels)
    if result.dtype != np.uint8:
        max_value = float(result.max()) if result.size else 0.0
        if max_value <= 1.0:
            result = result * 255.0
        result = np.clip(result, 0, 255).astype(np.uint8)
    return Image.fromarray(result, mode="RGB")


def _crop_visible(image: Image.Image) -> Image.Image:
    pixels = image.load()
    if pixels is None:
        return image
    xs: list[int] = []
    ys: list[int] = []
    width, height = image.size
    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            if not isinstance(pixel, tuple):
                continue
            if int(pixel[0]) + int(pixel[1]) + int(pixel[2]) > 24:
                xs.append(x)
                ys.append(y)
    if not xs:
        return image
    return image.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))


def _open_logo_rgba() -> Image.Image:
    try:
        with brand_file("youtube.svg") as svg_path:
            document = pymupdf.open(svg_path)
            pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(24, 24), alpha=True)
            return Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGBA")
    except FileNotFoundError:
        pass
    with brand_file("youtube.png") as png_path:
        return Image.open(png_path).convert("RGBA")


@lru_cache(maxsize=1)
def load_youtube_logo() -> Image.Image:
    image = _open_logo_rgba()
    bbox = image.getbbox()
    if bbox is not None:
        image = image.crop(bbox)
    return _fill_logo_cutout(image)


def _composite_on_black(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image.convert("RGB")
    canvas = Image.new("RGB", image.size, BRAND_BG)
    canvas.paste(image, mask=image.split()[-1])
    return canvas


@lru_cache(maxsize=1)
def youtube_logo_sprite() -> Image.Image:
    """Pyxelate the SVG on a transparent canvas so rounded corners stay clean."""
    logo = load_youtube_logo()
    palette = np.array(
        [[[channel / 255.0 for channel in color]] for color in (BRAND_BG, BRAND_YT_RED, BRAND_WHITE)],
        dtype=float,
    )
    transformed = Pyx(
        height=YOUTUBE_LOGO_PYX_HEIGHT,
        palette=palette,
        dither="none",
        sobel=2,
        svd=False,
        alpha=0.6,
    ).fit_transform(np.asarray(logo))
    if transformed.ndim == 3 and transformed.shape[-1] == 4:
        sprite = Image.fromarray(np.clip(transformed, 0, 255).astype(np.uint8), mode="RGBA")
        return _crop_visible(_composite_on_black(sprite))
    return _crop_visible(_array_to_image(transformed))


def blit_logo(image: Image.Image, origin_x: int, origin_y: int, sprite: Image.Image | None = None) -> None:
    sprite = sprite if sprite is not None else youtube_logo_sprite()
    pixels = image.load()
    source = sprite.load()
    if pixels is None or source is None:
        return
    width, height = image.size
    sprite_w, sprite_h = sprite.size
    for row in range(sprite_h):
        for col in range(sprite_w):
            pixel = source[col, row]
            if not isinstance(pixel, tuple):
                continue
            red, green, blue = int(pixel[0]), int(pixel[1]), int(pixel[2])
            if red + green + blue < 24:
                continue
            x = origin_x + col
            y = origin_y + row
            if 0 <= x < width and 0 <= y < height:
                pixels[x, y] = (red, green, blue)
