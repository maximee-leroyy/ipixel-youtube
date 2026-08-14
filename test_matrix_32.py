#!/usr/bin/env python3
"""Simulate the 32x32 RYXACORE panel without Bluetooth."""

from io import BytesIO

from PIL import Image

from youtube_subs import render_matrix_gif, render_matrix_png, write_preview


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


def test_hud_corners_are_present() -> None:
    png = render_matrix_png("RYXACORE", "1096", 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    cyan = (0, 245, 255)
    assert image.getpixel((0, 0)) == cyan
    assert image.getpixel((31, 0)) == cyan
    assert image.getpixel((0, 31)) == cyan
    assert image.getpixel((31, 31)) == cyan
    assert image.getpixel((2, 0)) == cyan
    assert image.getpixel((0, 2)) == cyan


def test_play_button_is_centered() -> None:
    png = render_matrix_png("RYXACORE", "1096", 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    white_x: list[int] = []
    red_x: list[int] = []
    cyan_x: list[int] = []
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if pixel == (255, 255, 255) and y < 10:
                white_x.append(x)
            elif pixel == (255, 0, 0):
                red_x.append(x)
            elif pixel == (0, 245, 255) and 3 <= x <= 28 and 3 <= y <= 28:
                cyan_x.append(x)
    assert white_x
    assert abs(sum(red_x) / len(red_x) - 15.5) < 0.6
    assert abs(sum(white_x) / len(white_x) - 16) < 1.2
    assert abs(sum(cyan_x) / len(cyan_x) - 16) < 1.2


def test_preview_gif_is_large() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        _native, _led, gif_path = write_preview("RYXACORE", "1096", "CUSONG", None, folder)
        image = Image.open(gif_path)
        assert min(image.size) >= 400
        assert getattr(image, "n_frames", 1) >= 6


def test_idle_gif_has_glass_sheen() -> None:
    gif = render_matrix_gif("RYXACORE", "1096", 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(gif))
    assert image.format == "GIF"
    n_frames = getattr(image, "n_frames", 1)
    assert 12 <= n_frames <= 32
    assert len(gif) < 20 * 1024
    frames: list[Image.Image] = []
    for index in range(n_frames):
        image.seek(index)
        frame = image.convert("RGB")
        assert frame.size == (32, 32)
        frames.append(frame.copy())
    blobs = {frame.tobytes() for frame in frames}
    assert len(blobs) >= 8


if __name__ == "__main__":
    test_frame_is_exactly_32x32()
    test_frame_is_not_blank()
    test_youtube_play_is_present()
    test_hud_corners_are_present()
    test_play_button_is_centered()
    test_idle_gif_has_glass_sheen()
    test_preview_gif_is_large()
    native_path, led_path, gif_path = write_preview("RYXACORE", "1096", "CUSONG", None)
    print("OK 32x32")
    print(native_path)
    print(led_path)
    print(gif_path)
