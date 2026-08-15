"""Simulate the 32x32 CHANNEL panel without Bluetooth."""

from io import BytesIO

from PIL import Image

from ipixel.display.device import clamp_brightness
from ipixel.display.render import apply_brightness, render_matrix_gif, render_matrix_png, write_preview
from ipixel.youtube.counts import format_count, format_panel_count


def test_format_count_groups_thousands() -> None:
    assert format_count(902) == "902"
    assert format_count(1093) == "1.093"
    assert format_count(1902) == "1.902"
    assert format_count(12345) == "12.345"
    assert format_count(999_999) == "999.999"
    assert format_count(1_000_000) == "1000000"
    assert format_count(20_201_148) == "20201148"


def test_format_panel_count_compacts_huge_channels() -> None:
    assert format_panel_count(1093) == "1.093"
    assert format_panel_count(20_201_148) == "20201148"
    assert format_panel_count(99_999_999) == "99999999"
    assert format_panel_count(100_000_000) == "100M"
    assert format_panel_count(513_297_760) == "513.3M"
    assert format_panel_count(1_000_000_000) == "1B"


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
    png = render_matrix_png("CHANNEL", format_count(1096), 32, 32, None, "CUSONG")
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
    png = render_matrix_png("CHANNEL", format_count(1080), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png))
    assert image.size == (32, 32)
    assert image.mode == "RGB"


def test_frame_is_not_blank() -> None:
    png = render_matrix_png("CHANNEL", format_count(1080), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    bright = 0
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if isinstance(pixel, tuple) and sum(pixel) > 40:
                bright += 1
    assert bright > 40


def test_youtube_logo_has_red_and_play() -> None:
    png = render_matrix_png("CHANNEL", format_count(1096), 32, 32, None, "CUSONG")
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
    png = render_matrix_png("CHANNEL", format_count(1096), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    cyan = (0, 245, 255)
    assert image.getpixel((0, 0)) == cyan
    assert image.getpixel((31, 0)) == cyan
    assert image.getpixel((0, 31)) == cyan
    assert image.getpixel((31, 31)) == cyan


def test_count_is_cyan_and_centered() -> None:
    png = render_matrix_png("CHANNEL", format_count(1096), 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    cyan_x: list[int] = []
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if pixel == (0, 245, 255) and 3 <= x <= 28 and 3 <= y <= 28:
                cyan_x.append(x)
    assert len(cyan_x) >= 20
    assert abs(sum(cyan_x) / len(cyan_x) - 16) < 1.5


def test_large_count_fits_32x32() -> None:
    from ipixel.display.fonts import FONT_3X5, FONT_5X7, _fit_count, _text_pixel_size

    text = format_count(20_201_148)
    fitted, font, gap, separator_gap = _fit_count(text, 32)
    assert fitted == "20201148"
    assert font is FONT_3X5
    width, height = _text_pixel_size(fitted, gap, font, separator_gap)
    assert width <= 32
    assert height == 5

    small, small_font, small_gap, small_sep = _fit_count(format_count(1093), 32)
    assert small == "1.093"
    assert small_font is FONT_5X7
    assert small_gap == 2
    assert small_sep is None

    huge = format_panel_count(513_297_760)
    assert huge == "513.3M"
    fitted_huge, font_huge, gap_huge, sep_huge = _fit_count(huge, 32)
    assert fitted_huge == "513.3M"
    assert font_huge is FONT_5X7
    width_huge, height_huge = _text_pixel_size(fitted_huge, gap_huge, font_huge, sep_huge)
    assert width_huge <= 32
    assert height_huge == 7

    png = render_matrix_png("SQUEEZIE", text, 32, 32, None, "CUSONG")
    image = Image.open(BytesIO(png)).convert("RGB")
    assert image.size == (32, 32)
    cyan = (0, 245, 255)
    xs: list[int] = []
    for y in range(32):
        for x in range(32):
            pixel = image.getpixel((x, y))
            if pixel == cyan and 4 <= y <= 27:
                xs.append(x)
    assert len(xs) >= 40
    assert min(xs) >= 0
    assert max(xs) <= 31
    assert max(xs) - min(xs) >= 20
    assert abs(sum(xs) / len(xs) - 16) < 2.5


def test_load_drawing_fits_32x32(tmp_path) -> None:
    from ipixel.display.drawing import load_drawing

    source = Image.new("RGB", (8, 4), (255, 0, 0))
    path = tmp_path / "red.png"
    source.save(path)
    frames, durations = load_drawing(path, 32, 32)
    assert len(frames) == 1
    assert durations[0] >= 20
    image = frames[0]
    assert image.size == (32, 32)
    assert image.getpixel((16, 16)) == (255, 0, 0)
    assert image.getpixel((0, 0)) == (0, 0, 0)


def test_drawing_preview_writes_files(tmp_path) -> None:
    from ipixel.display.drawing import write_drawing_preview

    source = Image.new("RGB", (32, 32), (0, 255, 0))
    path = tmp_path / "green.png"
    source.save(path)
    native_path, led_path, gif_path = write_drawing_preview(path, tmp_path)
    native = Image.open(native_path)
    led = Image.open(led_path)
    assert native.size == (32, 32)
    assert native.getpixel((0, 0)) == (0, 255, 0)
    assert min(led.size) >= 400
    gif = Image.open(gif_path)
    assert gif.format == "GIF"


def test_preview_gif_is_large() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        native_path, led_path, gif_path = write_preview("CHANNEL", format_count(1096), "CUSONG", None, folder)
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
    gif = render_matrix_gif("CHANNEL", format_count(1096), 32, 32, None, "CUSONG")
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
    test_large_count_fits_32x32()
    test_idle_gif_has_glass_sheen()
    test_preview_gif_is_large()
    test_brand_logo_files_exist()
    native_path, led_path, gif_path = write_preview("CHANNEL", format_count(1096), "CUSONG", None)
    print("OK 32x32")
    print(native_path)
    print(led_path)
    print(gif_path)
