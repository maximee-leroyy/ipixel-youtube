"""Simulate the 32x32 RYXACORE panel without Bluetooth."""

from io import BytesIO

from PIL import Image

from ipixel.display.device import clamp_brightness
from ipixel.display.render import apply_brightness, render_matrix_gif, render_matrix_png, write_preview
from ipixel.youtube.counts import format_count


def test_format_count_groups_thousands() -> None:
    assert format_count(902) == "902"
    assert format_count(1093) == "1.093"
    assert format_count(1902) == "1.902"
    assert format_count(12345) == "12.345"


def test_clamp_brightness() -> None:
    assert clamp_brightness(0) == 0
    assert clamp_brightness(40) == 40
    assert clamp_brightness(100) == 100
    try:
        clamp_brightness(101)
    except ValueError:
        pass
    else:
        raise AssertionError("101 should be rejected")


def test_apply_brightness_scales_pixels() -> None:
    png = render_matrix_png("RYXACORE", format_count(1096), 32, 32, None, "CUSONG")
    full = Image.open(BytesIO(png)).convert("RGB")
    dim = apply_brightness(full, 50)
    cyan = (0, 245, 255)
    found = False
    for y in range(32):
        for x in range(32):
            if full.getpixel((x, y)) == cyan:
                assert dim.getpixel((x, y)) == (0, 122, 127)
                found = True
                break
        if found:
            break
    assert found


def test_frame_is_exactly_32x32() -> None:
    png = render_matrix_png("RYXACORE", format_count(1080), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png))
    assert image.size == (32, 32)
    assert image.mode == "RGB"


def test_frame_is_not_blank() -> None:
    png = render_matrix_png("RYXACORE", format_count(1080), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    bright = 0
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if isinstance(pixel, tuple) and sum(pixel) > 40:
                bright += 1
    assert bright > 40


def test_youtube_logo_has_red_and_play() -> None:
    png = render_matrix_png("RYXACORE", format_count(1096), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    red = 0
    white = 0
    white_rows: list[int] = []
    for y in range(16):
        row_white = 0
        for x in range(32):
            pixel = image.getpixel((x, y))
            if pixel == (255, 0, 0):
                red += 1
            elif pixel == (255, 255, 255):
                white += 1
                row_white += 1
        white_rows.append(row_white)
    assert red >= 40
    assert white >= 8
    widths = [count for count in white_rows if count]
    assert widths[0] <= widths[len(widths) // 2]
    assert widths[-1] <= widths[len(widths) // 2]
    assert max(widths) >= 3


def test_hud_corners_are_present() -> None:
    png = render_matrix_png("RYXACORE", format_count(1096), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    cyan = (0, 245, 255)
    assert image.getpixel((0, 0)) == cyan
    assert image.getpixel((31, 0)) == cyan
    assert image.getpixel((0, 31)) == cyan
    assert image.getpixel((31, 31)) == cyan


def test_count_is_cyan_and_centered() -> None:
    png = render_matrix_png("RYXACORE", format_count(1096), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    cyan_x: list[int] = []
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if pixel == (0, 245, 255) and 3 <= x <= 28 and 3 <= y <= 28:
                cyan_x.append(x)
    assert len(cyan_x) >= 20
    assert abs(sum(cyan_x) / len(cyan_x) - 16) < 1.5


def test_preview_gif_is_large() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        native_path, led_path, gif_path = write_preview("RYXACORE", format_count(1096), "CUSONG", None, folder)
        assert native_path.endswith("32x32.png")
        assert led_path.endswith("led.png")
        image = Image.open(gif_path)
        assert min(image.size) >= 400
        assert getattr(image, "n_frames", 1) >= 6


def test_brand_logo_files_exist() -> None:
    from ipixel.assets import brand_file

    with brand_file("youtube.svg") as svg:
        assert svg.is_file()
        assert svg.stat().st_size > 0


def test_idle_gif_has_glass_sheen() -> None:
    gif = render_matrix_gif("RYXACORE", format_count(1096), 32, 32, None, "CUSONG")
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
    test_format_count_groups_thousands()
    test_clamp_brightness()
    test_apply_brightness_scales_pixels()
    test_frame_is_exactly_32x32()
    test_frame_is_not_blank()
    test_youtube_logo_has_red_and_play()
    test_hud_corners_are_present()
    test_count_is_cyan_and_centered()
    test_idle_gif_has_glass_sheen()
    test_preview_gif_is_large()
    test_brand_logo_files_exist()
    native_path, led_path, gif_path = write_preview("RYXACORE", format_count(1096), "CUSONG", None)
    print("OK 32x32")
    print(native_path)
    print(led_path)
    print(gif_path)
