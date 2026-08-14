"""Brand files (SVG/PNG) and generated preview output."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path

PREVIEW_DIRNAME = "preview"


def repo_assets_dir() -> Path:
    """Checkout `assets/` next to pyproject.toml, else `./assets`."""
    for parent in Path(__file__).resolve().parents:
        marker = parent / "pyproject.toml"
        assets = parent / "assets"
        if marker.is_file() and assets.is_dir():
            return assets
    return Path.cwd() / "assets"


def preview_dir(output_dir: str | Path | None = None) -> Path:
    folder = Path(output_dir) if output_dir is not None else repo_assets_dir() / PREVIEW_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@contextmanager
def brand_file(name: str) -> Iterator[Path]:
    """Yield a filesystem path to a bundled or checkout brand asset."""
    packaged = files("ipixel.assets").joinpath(name)
    if packaged.is_file():
        with as_file(packaged) as path:
            yield Path(path)
            return
    checkout = repo_assets_dir() / name
    if checkout.is_file():
        yield checkout
        return
    raise FileNotFoundError(f"Asset introuvable: {name} (package ipixel.assets ou assets/{name})")
