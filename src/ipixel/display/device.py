"""Bluetooth iPixel Color panel: connect (with retries), wipe slot, send PNG/GIF.

How a connection works, and why:

1. Close any BlueZ link left to this address (Linux). A container killed
   without a clean exit leaves the panel "connected" in the host's BlueZ;
   a connected panel stops advertising, so the next scan cannot find it
   (BleakDeviceNotFoundError).
2. Take the host-wide BLE lock (Linux). Several containers share one
   Bluetooth adapter, and BlueZ fails when two LE connections start at once.
3. Connect, retrying with exponential backoff on any BLE error.

pypixelcolor's sync `Client` starts one thread per instance and offers no
public way to stop it, so retries would leak threads. `Panel` instead runs
pypixelcolor's public `AsyncClient` on one event loop for the process.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import random
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Coroutine, Iterator
from typing import Any

import pypixelcolor
from pypixelcolor.lib.device_info import DeviceInfo

from ipixel.constants import BLE_ERRORS, DEFAULT_BRIGHTNESS, SHEEN_FRAME_MS, SHEEN_FRAMES
from ipixel.display.drawing import drawing_gif, drawing_png, load_drawing
from ipixel.display.render import render_matrix_gif, render_matrix_png
from ipixel.log import log

# Abstract UNIX socket name (leading NUL): no file on disk, released by the
# kernel when the process dies. Abstract names are scoped to the network
# namespace, so every container in `network_mode: host` sees the same one.
BLE_LOCK_NAME = "\0ipixel-ble-connect"
BLE_LOCK_WAIT_S = 90.0
RETRY_BASE_S = 3.0
RETRY_MAX_S = 60.0
# BlueZ only exists on Linux; on macOS (CoreBluetooth) steps 1 and 2 do not apply.
ON_BLUEZ = sys.platform == "linux"


class Panel:
    """One iPixel panel, driven from synchronous code through a private event loop."""

    def __init__(self, address: str) -> None:
        self.address = address
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, name="ble-loop", daemon=True).start()
        self._client: pypixelcolor.AsyncClient | None = None

    def _run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    @property
    def client(self) -> pypixelcolor.AsyncClient:
        if self._client is None:
            raise RuntimeError(f"Panel {self.address} not connected.")
        return self._client

    @property
    def info(self) -> DeviceInfo:
        return self.client.get_device_info()

    def connect(self) -> None:
        # A fresh AsyncClient per attempt: a failed attempt leaves no half-open state behind.
        client = pypixelcolor.AsyncClient(self.address)
        self._run(client.connect())
        self._client = client

    def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            self._run(client.disconnect())

    def set_brightness(self, level: int) -> None:
        self._run(self.client.set_brightness(level))

    def delete(self, slot: int) -> None:
        self._run(self.client.delete(slot))

    def show_slot(self, slot: int) -> None:
        self._run(self.client.show_slot(slot))

    def send(self, payload: bytes, extension: str, save_slot: int) -> None:
        self._run(self.client.send_image_hex(payload.hex(), extension, resize_method="crop", save_slot=save_slot))


def clamp_brightness(level: int) -> int:
    if not 0 <= level <= 100:
        raise ValueError("Brightness must be between 0 and 100.")
    return level


@contextlib.contextmanager
def ble_lock(timeout: float = BLE_LOCK_WAIT_S) -> Iterator[None]:
    """Hold the host-wide BLE connect lock. Raises TimeoutError after `timeout` seconds."""
    if not ON_BLUEZ:
        yield
        return
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        announced = False
        while True:
            try:
                sock.bind(BLE_LOCK_NAME)
                break
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    raise
            if time.monotonic() >= deadline:
                raise TimeoutError(f"BLE lock still held after {timeout:.0f}s")
            if not announced:
                log.info("Another panel is connecting, waiting for the BLE lock...")
                announced = True
            time.sleep(0.5 + random.random())
        yield


def release_stale_connection(address: str) -> None:
    """Close a BlueZ link left by a killed process, so the panel advertises again."""
    if not ON_BLUEZ:
        return
    out = subprocess.run(
        ["bluetoothctl", "disconnect", address],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if "Successful disconnected" in out.stdout:
        log.info("Old BlueZ connection to %s closed", address)
        time.sleep(2)  # give the panel time to start advertising again
    else:
        log.debug(f"bluetoothctl disconnect {address}: {(out.stdout or out.stderr).strip()}")


def retry_delay(attempt: int) -> float:
    """Backoff before the next attempt: 3, 6, 12... capped at 60 s, plus up to 2 s of jitter."""
    return min(RETRY_MAX_S, RETRY_BASE_S * 2 ** min(attempt - 1, 5)) + random.uniform(0, 2)


def _setup(panel: Panel, wipe_slot: int, brightness: int) -> None:
    panel.set_brightness(brightness)
    log.info("Brightness: %d%%", brightness)
    if wipe_slot >= 1:
        panel.delete(wipe_slot)
        log.info("Slot %d wiped.", wipe_slot)
    log.info("Connected to panel %s (%dx%d)", panel.address, panel.info.width, panel.info.height)


def connect_device(
    panel: Panel,
    wipe_slot: int = 0,
    brightness: int = DEFAULT_BRIGHTNESS,
    *,
    attempts: int | None,
) -> None:
    """Connect and set up the panel. `attempts=None` retries forever (daemon mode)."""
    attempt = 0
    while True:
        attempt += 1
        release_stale_connection(panel.address)
        try:
            with ble_lock():
                panel.connect()
            _setup(panel, wipe_slot, brightness)
            return
        except BLE_ERRORS as exc:
            disconnect_device(panel)
            if attempts is not None and attempt >= attempts:
                raise
            delay = retry_delay(attempt)
            log.warning(
                "BLE connection to %s failed (attempt %d): %s: %s; retrying in %.0fs",
                panel.address,
                attempt,
                type(exc).__name__,
                exc,
                delay,
            )
            time.sleep(delay)


def disconnect_device(panel: Panel) -> None:
    """Disconnect; a failure is logged (the link is already gone or going)."""
    try:
        panel.disconnect()
    except BLE_ERRORS as exc:
        log.warning("Bluetooth disconnect %s: %s: %s", panel.address, type(exc).__name__, exc)


def display_count(
    panel: Panel,
    name: str,
    count_text: str,
    *,
    color: str | None,
    font: str,
    save_slot: int,
    animate: bool,
) -> None:
    info = panel.info
    if animate:
        gif = render_matrix_gif(name, count_text, info.width, info.height, color, font)
        panel.send(gif, ".gif", save_slot=0)
        log.debug(
            f"BLE send_gif {info.width}x{info.height} {SHEEN_FRAMES}x{SHEEN_FRAME_MS}ms "
            f"bytes={len(gif)} text={count_text}"
        )
        return
    png = render_matrix_png(name, count_text, info.width, info.height, color, font)
    panel.send(png, ".png", save_slot=save_slot)
    log.debug(f"BLE send_png {info.width}x{info.height} slot={save_slot} text={count_text}")
    if save_slot >= 1:
        panel.show_slot(save_slot)


def display_drawing(
    panel: Panel,
    path: str,
    *,
    save_slot: int,
    static: bool,
) -> None:
    info = panel.info
    frames, durations = load_drawing(path, info.width, info.height)
    if len(frames) > 1 and not static:
        payload = drawing_gif(frames, durations)
        panel.send(payload, ".gif", save_slot=0)
        log.info("GIF %d frames (%d bytes) from %s", len(frames), len(payload), path)
        return
    payload = drawing_png(frames)
    panel.send(payload, ".png", save_slot=save_slot)
    if save_slot >= 1:
        panel.show_slot(save_slot)
    log.info("PNG 32x32 from %s", path)
