"""Bundled brand files and the preview output folder."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path

# Relative to the working directory: ./assets/preview in a checkout, /app/assets/preview in the image.
DEFAULT_PREVIEW_DIR = Path("assets") / "preview"


def preview_dir(output_dir: str | Path | None = None) -> Path:
    folder = Path(output_dir) if output_dir is not None else DEFAULT_PREVIEW_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@contextmanager
def brand_file(name: str) -> Iterator[Path]:
    """Yield a filesystem path to a brand file shipped inside the ipixel.assets package."""
    with as_file(files("ipixel.assets").joinpath(name)) as path:
        yield Path(path)
