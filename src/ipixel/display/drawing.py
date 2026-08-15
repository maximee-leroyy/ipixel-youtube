"""Load a user drawing and fit it to the 32×32 panel."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from ipixel.assets import preview_dir
from ipixel.display.render import save_gif, simulate_led_matrix


def fit_to_panel(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale with nearest-neighbor (pixel art) and center on a black canvas."""
    rgba = image.convert("RGBA")
    scale = min(width / rgba.width, height / rgba.height)
    new_w = max(1, round(rgba.width * scale))
    new_h = max(1, round(rgba.height * scale))
    resized = rgba.resize((new_w, new_h), Image.Resampling.NEAREST)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    canvas.paste(resized, ((width - new_w) // 2, (height - new_h) // 2), resized)
    return canvas


def load_drawing(path: str | Path, width: int = 32, height: int = 32) -> tuple[list[Image.Image], list[int]]:
    file = Path(path)
    if not file.is_file():
        raise FileNotFoundError(f"Dessin introuvable: {file}")
    frames: list[Image.Image] = []
    durations: list[int] = []
    with Image.open(file) as source:
        n_frames = getattr(source, "n_frames", 1)
        for index in range(n_frames):
            source.seek(index)
            frames.append(fit_to_panel(source.copy(), width, height))
            durations.append(max(20, int(source.info.get("duration", 100))))
    return frames, durations


def drawing_png(frames: list[Image.Image]) -> bytes:
    buffer = BytesIO()
    frames[0].save(buffer, format="PNG")
    return buffer.getvalue()


def drawing_gif(frames: list[Image.Image], durations: list[int]) -> bytes:
    return save_gif(frames, durations)


def write_drawing_preview(
    path: str | Path,
    output_dir: str | Path | None = None,
    width: int = 32,
    height: int = 32,
) -> tuple[str, str, str]:
    frames, durations = load_drawing(path, width, height)
    folder = preview_dir(output_dir)
    native_path = folder / "32x32.png"
    led_path = folder / "led.png"
    gif_path = folder / "preview.gif"
    frames[0].save(native_path)
    simulate_led_matrix(frames[0]).save(led_path)
    led_frames = [simulate_led_matrix(frame) for frame in frames]
    gif_path.write_bytes(save_gif(led_frames, durations))
    return str(native_path), str(led_path), str(gif_path)
