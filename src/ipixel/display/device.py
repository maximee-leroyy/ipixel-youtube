"""Bluetooth iPixel Color client: connect, wipe slot, send PNG/GIF."""

from __future__ import annotations

import contextlib
import errno
import random
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator

import pypixelcolor

from ipixel.constants import BLE_ERRORS, DEFAULT_BRIGHTNESS, SHEEN_FRAME_MS, SHEEN_FRAMES
from ipixel.debug import debug
from ipixel.display.drawing import drawing_gif, drawing_png, load_drawing
from ipixel.display.render import render_matrix_gif, render_matrix_png
from ipixel.log import log

# Socket UNIX abstrait = mutex libéré à la mort du process, partagé par tous les
# containers en network_mode: host (même namespace réseau). Un seul scan+connect
# BLE à la fois sur l'adaptateur : BlueZ rate les connexions LE concurrentes.
BLE_LOCK_NAME = "\0ipixel-ble-connect"
BLE_LOCK_WAIT = 90.0
RETRY_BASE = 3.0
RETRY_MAX = 60.0


def clamp_brightness(level: int) -> int:
    if not 0 <= level <= 100:
        raise ValueError("La luminosité doit être entre 0 et 100.")
    return level


@contextlib.contextmanager
def ble_lock(timeout: float = BLE_LOCK_WAIT) -> Iterator[None]:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout
    waited = False
    try:
        while True:
            try:
                sock.bind(BLE_LOCK_NAME)
                debug("BLE lock pris")
                break
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    # macOS : pas de socket abstrait -> pas de verrou.
                    debug(f"BLE lock indisponible ({exc}), on continue sans")
                    break
                if time.monotonic() >= deadline:
                    log.warning("Verrou BLE toujours pris après %.0fs, connexion quand même", timeout)
                    break
                if not waited:
                    log.info("Autre panneau en cours de connexion, attente du verrou BLE...")
                    waited = True
                time.sleep(0.5 + random.random())
        yield
    finally:
        sock.close()


def _release_stale_connection(address: str) -> None:
    """Drop a BlueZ link left by a killed container: a connected panel stops advertising."""
    if ":" not in address or shutil.which("bluetoothctl") is None:
        return
    try:
        out = subprocess.run(
            ["bluetoothctl", "disconnect", address],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        debug(f"bluetoothctl disconnect {address}: {exc}")
        return
    if "Successful disconnected" in out.stdout:
        log.info("Ancienne connexion BlueZ vers %s fermée", address)
        time.sleep(2)  # le panneau recommence à advertiser
    else:
        debug(f"bluetoothctl disconnect {address}: {(out.stdout or out.stderr).strip()}")


def _drop_client(device: pypixelcolor.Client) -> None:
    # Chaque Client lance un thread event loop : on le stoppe sinon il fuit à chaque essai.
    with contextlib.suppress(Exception):
        getattr(device, "_cleanup_loop")()  # noqa: B009


def _open(address: str, wipe_slot: int, brightness: int) -> pypixelcolor.Client:
    device = pypixelcolor.Client(address)
    try:
        with ble_lock():
            device.connect()
    except BaseException:
        _drop_client(device)
        raise
    level = clamp_brightness(brightness)
    try:
        device.set_brightness(level)
        log.info("Luminosité: %d%%", level)
    except BLE_ERRORS as exc:
        log.warning("Luminosité: %s", exc)
    if wipe_slot >= 1:
        try:
            device.delete(wipe_slot)
            log.info("Slot %d effacé.", wipe_slot)
        except BLE_ERRORS as exc:
            log.warning("Slot %d: %s", wipe_slot, exc)
    info = device.get_device_info()
    log.info("Connecté au panneau %s (%dx%d)", address, info.width, info.height)
    return device


def connect_device(
    address: str,
    wipe_slot: int = 0,
    brightness: int = DEFAULT_BRIGHTNESS,
    *,
    attempts: int | None = None,
) -> pypixelcolor.Client:
    """Connect with exponential backoff. attempts=None retries forever (daemon mode)."""
    attempt = 0
    while True:
        attempt += 1
        _release_stale_connection(address)
        try:
            return _open(address, wipe_slot, brightness)
        except BLE_ERRORS as exc:
            if attempts is not None and attempt >= attempts:
                raise
            delay = min(RETRY_MAX, RETRY_BASE * 2 ** min(attempt - 1, 5)) + random.uniform(0, 2)
            log.warning(
                "Connexion BLE %s échouée (essai %d): %s: %s ; nouvel essai dans %.0fs",
                address,
                attempt,
                type(exc).__name__,
                exc,
                delay,
            )
            time.sleep(delay)


def disconnect_device(device: pypixelcolor.Client) -> None:
    try:
        device.disconnect()
    except BLE_ERRORS as exc:
        log.warning("Déconnexion Bluetooth: %s", exc)
    finally:
        _drop_client(device)


def display_count(
    device: pypixelcolor.Client,
    name: str,
    count_text: str,
    *,
    color: str | None,
    font: str,
    save_slot: int,
    animate: bool,
) -> None:
    info = device.get_device_info()
    if animate:
        if save_slot >= 1:
            log.warning("GIF: --save-slot ignoré (un GIF en ROM peut brick le panneau).")
            save_slot = 0
        gif = render_matrix_gif(
            name,
            count_text,
            info.width,
            info.height,
            color,
            font,
        )
        device.send_image_hex(gif.hex(), ".gif", resize_method="crop", save_slot=0)
        debug(
            f"BLE send_gif {info.width}x{info.height} {SHEEN_FRAMES}x{SHEEN_FRAME_MS}ms "
            f"bytes={len(gif)} text={count_text}"
        )
        return
    png = render_matrix_png(
        name,
        count_text,
        info.width,
        info.height,
        color,
        font,
    )
    device.send_image_hex(png.hex(), ".png", resize_method="crop", save_slot=save_slot)
    debug(f"BLE send_png {info.width}x{info.height} slot={save_slot} text={count_text}")
    if save_slot >= 1:
        device.show_slot(save_slot)


def display_drawing(
    device: pypixelcolor.Client,
    path: str,
    *,
    save_slot: int,
    static: bool,
) -> None:
    info = device.get_device_info()
    frames, durations = load_drawing(path, info.width, info.height)
    animated = len(frames) > 1 and not static
    if animated:
        if save_slot >= 1:
            log.warning("GIF: --save-slot ignoré (un GIF en ROM peut brick le panneau).")
            save_slot = 0
        payload = drawing_gif(frames, durations)
        device.send_image_hex(payload.hex(), ".gif", resize_method="crop", save_slot=0)
        log.info("GIF %d frames (%d octets) depuis %s", len(frames), len(payload), path)
        return
    payload = drawing_png(frames)
    device.send_image_hex(payload.hex(), ".png", resize_method="crop", save_slot=save_slot)
    debug(f"BLE send_drawing_png {info.width}x{info.height} slot={save_slot}")
    if save_slot >= 1:
        device.show_slot(save_slot)
    log.info("PNG 32x32 depuis %s", path)
