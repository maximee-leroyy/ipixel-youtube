"""Bluetooth iPixel Color client: connect, wipe slot, send PNG/GIF."""

from __future__ import annotations

import sys

import pypixelcolor

from ipixel.constants import BLE_ERRORS, DEFAULT_BRIGHTNESS, SHEEN_FRAME_MS, SHEEN_FRAMES
from ipixel.debug import debug
from ipixel.display.drawing import drawing_gif, drawing_png, load_drawing
from ipixel.display.render import render_matrix_gif, render_matrix_png


def clamp_brightness(level: int) -> int:
    if not 0 <= level <= 100:
        raise ValueError("La luminosité doit être entre 0 et 100.")
    return level


def connect_device(
    address: str,
    wipe_slot: int = 0,
    brightness: int = DEFAULT_BRIGHTNESS,
) -> pypixelcolor.Client:
    device = pypixelcolor.Client(address)
    device.connect()
    level = clamp_brightness(brightness)
    try:
        device.set_brightness(level)
        print(f"Luminosité: {level}%")
    except BLE_ERRORS as exc:
        print(f"Luminosité: {exc}", file=sys.stderr)
    if wipe_slot >= 1:
        try:
            device.delete(wipe_slot)
            print(f"Slot {wipe_slot} effacé.")
        except BLE_ERRORS as exc:
            print(f"Slot {wipe_slot}: {exc}", file=sys.stderr)
    info = device.get_device_info()
    print(f"Connecté au panneau {info.width}x{info.height}")
    return device


def disconnect_device(device: pypixelcolor.Client) -> None:
    try:
        device.disconnect()
    except BLE_ERRORS as exc:
        print(f"Déconnexion Bluetooth: {exc}", file=sys.stderr)


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
            print("GIF: --save-slot ignoré (un GIF en ROM peut brick le panneau).")
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
        print(f"GIF {SHEEN_FRAMES} frames × {SHEEN_FRAME_MS} ms ({len(gif)} octets).")
        debug(f"BLE send_gif {info.width}x{info.height} bytes={len(gif)} text={count_text}")
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
            print("GIF: --save-slot ignoré (un GIF en ROM peut brick le panneau).")
            save_slot = 0
        payload = drawing_gif(frames, durations)
        device.send_image_hex(payload.hex(), ".gif", resize_method="crop", save_slot=0)
        print(f"GIF {len(frames)} frames ({len(payload)} octets) depuis {path}")
        debug(f"BLE send_drawing_gif {info.width}x{info.height} frames={len(frames)}")
        return
    payload = drawing_png(frames)
    device.send_image_hex(payload.hex(), ".png", resize_method="crop", save_slot=save_slot)
    debug(f"BLE send_drawing_png {info.width}x{info.height} slot={save_slot}")
    if save_slot >= 1:
        device.show_slot(save_slot)
    print(f"PNG 32x32 depuis {path}")
