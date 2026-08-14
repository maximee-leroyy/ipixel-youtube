#!/usr/bin/env python3
"""Simulate the 32x32 RYXACORE panel without Bluetooth."""

from io import BytesIO

from PIL import Image

from youtube_subs import render_matrix_png, write_preview


def test_frame_is_exactly_32x32() -> None:
    png = render_matrix_png("RYXACORE", "1080", 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png))
    assert image.size == (32, 32)
    assert image.mode == "RGB"


def test_frame_is_not_blank() -> None:
    png = render_matrix_png("RYXACORE", "1080", 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    bright = 0
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if isinstance(pixel, tuple) and sum(pixel) > 40:
                bright += 1
    assert bright > 40


def test_youtube_play_is_present() -> None:
    png = render_matrix_png("RYXACORE", "1096", 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    red = 0
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if pixel == (255, 0, 0):
                red += 1
    assert red >= 20


if __name__ == "__main__":
    test_frame_is_exactly_32x32()
    test_frame_is_not_blank()
    test_youtube_play_is_present()
    native_path, led_path = write_preview("RYXACORE", "1096", "CUSONG", None)
    print("OK 32x32")
    print(native_path)
    print(led_path)
