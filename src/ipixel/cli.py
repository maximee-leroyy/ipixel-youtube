"""CLI: fetch a YouTube subscriber count and drive the LED panel."""

from __future__ import annotations

import functools
import signal
import time
import urllib.error
from collections.abc import Callable
from pathlib import Path

import click

from ipixel.constants import BLE_ERRORS, COOKIE_HELP, DEFAULT_BRIGHTNESS
from ipixel.display.device import (
    Panel,
    clamp_brightness,
    connect_device,
    disconnect_device,
    display_count,
    display_drawing,
)
from ipixel.display.drawing import load_drawing, write_drawing_preview
from ipixel.display.render import write_preview
from ipixel.log import log, set_tag, setup_logging, tag_for
from ipixel.youtube.channel import fetch_channel_name, resolve_channel_id
from ipixel.youtube.counts import fetch_count, format_count, format_panel_count
from ipixel.youtube.http import http_error_detail


def _exit_on_sigterm(signum: int, frame: object) -> None:
    """Turn SIGTERM (`docker stop`) into a normal exit so `finally` closes the BLE link.

    Python's default SIGTERM action kills the process without cleanup: the panel
    then stays "connected" in the host's BlueZ and cannot be found on restart.
    """
    raise SystemExit(0)


def _save_preview(
    channel_name: str,
    count_text: str,
    font: str,
    color: str | None,
    preview_dir: str | None,
) -> int:
    native_path, led_path, gif_path = write_preview(
        channel_name,
        count_text,
        font,
        color,
        preview_dir,
    )
    log.info(f"{channel_name} {count_text}")
    log.info(f"Simu 32x32: {native_path}")
    log.info(f"Simu LED:   {led_path}")
    log.info(f"Open the GIF: {gif_path}")
    return 0


def _run_drawing(
    image_path: str,
    *,
    address: str,
    brightness: int,
    save_slot: int,
    wipe_slot: int,
    static: bool,
    preview: bool,
    preview_dir: str | None,
) -> int:
    if preview:
        try:
            native_path, led_path, gif_path = write_drawing_preview(image_path, preview_dir)
        except (OSError, ValueError) as exc:
            log.error(f"Unreadable drawing: {exc}")
            return 2
        log.info(f"Drawing: {image_path}")
        log.info(f"Simu 32x32: {native_path}")
        log.info(f"Simu LED:   {led_path}")
        log.info(f"Open the GIF: {gif_path}")
        return 0

    try:
        load_drawing(image_path)
    except (OSError, ValueError) as exc:
        log.error(f"Unreadable drawing: {exc}")
        return 2

    panel = Panel(address)
    try:
        connect_device(panel, wipe_slot=wipe_slot, brightness=brightness, attempts=3)
        display_drawing(panel, image_path, save_slot=save_slot, static=static)
    except KeyboardInterrupt:
        log.info("Stopped.")
    except BLE_ERRORS as exc:
        log.error(f"Bluetooth: {type(exc).__name__}: {exc}")
        return 1
    finally:
        disconnect_device(panel)
    return 0


def _exit_with_status(func: Callable[..., int]) -> Callable[..., None]:
    """Make the command's return value the process exit code.

    In standalone mode click ignores a command's return value, so `return 1` would
    exit with 0. ctx.exit() is click's way to set the code.
    """

    @functools.wraps(func)
    def wrapper(**kwargs: object) -> None:
        click.get_current_context().exit(func(**kwargs))

    return wrapper


@click.command(
    name="ipixel-youtube",
    context_settings={"help_option_names": ["-h", "--help"], "show_default": True},
)
@click.option(
    "--address",
    envvar="IPIXEL_ADDRESS",
    default=None,
    show_envvar=True,
    help="Bluetooth address of the panel (Linux MAC or macOS UUID). Required except with --preview / --print-count.",
)
@click.option(
    "--channel",
    envvar=["YOUTUBE_CHANNEL", "YOUTUBE_CHANNEL_ID"],
    default=None,
    show_envvar=True,
    help="Channel ID (UCxxxx) or handle (@myChannel).",
)
@click.option(
    "--source",
    envvar="YOUTUBE_SOURCE",
    type=click.Choice(["studio", "live", "official"], case_sensitive=True),
    default="studio",
    show_envvar=True,
    help="studio = exact YouTube Studio number (owner's cookies). "
    "live = Mixerno/SocialCounts estimate. "
    "official = rounded YouTube Data API (--api-key).",
)
@click.option(
    "--cookies",
    envvar="YOUTUBE_COOKIES",
    default="cookies.txt",
    show_envvar=True,
    help="Netscape cookies file (YouTube Studio session).",
)
@click.option(
    "--api-key",
    envvar="YOUTUBE_API_KEY",
    default=None,
    show_envvar=True,
    help="YouTube Data v3 API key, only for --source official.",
)
@click.option(
    "--interval",
    type=int,
    default=15,
    help="Seconds between two requests.",
)
@click.option(
    "--color",
    default=None,
    help="Accent color override (hex). Default: cyan.",
)
@click.option(
    "--brightness",
    type=int,
    metavar="0-100",
    envvar="IPIXEL_BRIGHTNESS",
    default=DEFAULT_BRIGHTNESS,
    show_envvar=True,
    help="Panel brightness 0-100 (hardware setting, ignored by --preview).",
)
@click.option(
    "--font",
    default="CUSONG",
    help="Font: CUSONG, SIMSUN or VCR_OSD_MONO (more readable at 32x32).",
)
@click.option(
    "--name",
    envvar="YOUTUBE_CHANNEL_NAME",
    default=None,
    show_envvar=True,
    help="Name shown at the top of the panel. Default: the real YouTube name.",
)
@click.option(
    "--save-slot",
    type=int,
    default=0,
    help="Slot 1-10 to save to ROM. 0 = live display, no ROM. Requires --static "
    "(a GIF in ROM can brick the panel). "
    "pypixelcolor docs: a slot with corrupted data can brick/bootloop. "
    "Only use a slot after a successful send without a slot.",
)
@click.option(
    "--wipe-slot",
    type=int,
    metavar="N",
    default=1,
    help="Erase this slot on connect (where the broken GIF was saved). 0 = erase nothing.",
)
@click.option(
    "--static",
    is_flag=True,
    help="Still PNG, no animation. Default: short GIF (sheen) live, no ROM slot.",
)
@click.option(
    "--image",
    "image_path",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="PNG/GIF/JPEG to show instead of the YouTube HUD. Resized to 32×32.",
)
@click.option(
    "--preview",
    is_flag=True,
    help="Generate an LED simulation in assets/preview/ without Bluetooth. "
    "With --image: simulates the drawing. Otherwise: uses the count from --channel/--source, "
    "unless --preview-count is given.",
)
@click.option(
    "--preview-dir",
    default=None,
    help="Folder for preview PNG/GIF files (default: assets/preview).",
)
@click.option(
    "--preview-count",
    default=None,
    help="Force a number in --preview instead of fetching the real count.",
)
@click.option(
    "--once",
    is_flag=True,
    help="Display once then exit (the text stays if --save-slot >= 1).",
)
@click.option(
    "--print-count",
    is_flag=True,
    help="Print the subscriber count in the terminal, without Bluetooth.",
)
@click.option(
    "--debug",
    is_flag=True,
    envvar="YOUTUBE_DEBUG",
    show_envvar=True,
    help="Detailed logs on stderr (HTTP, Studio session, BLE, pypixelcolor, bleak).",
)
@_exit_with_status
def main(
    address: str | None,
    channel: str | None,
    source: str,
    cookies: str,
    api_key: str | None,
    interval: int,
    color: str | None,
    brightness: int,
    font: str,
    name: str | None,
    save_slot: int,
    wipe_slot: int,
    static: bool,
    image_path: str | None,
    preview: bool,
    preview_dir: str | None,
    preview_count: str | None,
    once: bool,
    print_count: bool,
    debug: bool,
) -> int:
    """Show the live YouTube subscriber count on an iPixel Color."""
    setup_logging(debug)
    set_tag(tag_for(channel, address))
    signal.signal(signal.SIGTERM, _exit_on_sigterm)
    log.debug(
        f"start source={source} channel={channel} cookies={cookies} "
        f"image={image_path} print_count={print_count} once={once} brightness={brightness}"
    )

    try:
        brightness = clamp_brightness(brightness)
    except ValueError as exc:
        log.error(exc)
        return 2
    if save_slot >= 1 and not static:
        log.error("--save-slot requires --static: a GIF in ROM can brick the panel.")
        return 2

    if image_path:
        if not preview and not address:
            log.error("Missing parameters: --address or IPIXEL_ADDRESS")
            return 2
        return _run_drawing(
            image_path,
            address=address or "",
            brightness=brightness,
            save_slot=save_slot,
            wipe_slot=wipe_slot,
            static=static,
            preview=preview,
            preview_dir=preview_dir,
        )

    forced_count: str | None = None
    if preview_count is not None:
        forced_count = format_panel_count(int(preview_count)) if preview_count.isdigit() else preview_count

    missing = []
    if not channel:
        missing.append("--channel or YOUTUBE_CHANNEL")
    if forced_count is None and source == "official" and api_key is None:
        missing.append("--api-key or YOUTUBE_API_KEY")
    if forced_count is None and source == "studio" and not Path(cookies).is_file():
        missing.append(f"--cookies ({cookies} not found)")
    if not preview and not print_count and not address:
        missing.append("--address or IPIXEL_ADDRESS")
    if missing:
        log.error("Missing parameters: " + ", ".join(missing))
        if source == "studio":
            log.error(COOKIE_HELP)
        else:
            log.error("Example: ipixel-youtube --channel @yourChannel")
        return 2

    assert channel is not None
    try:
        channel_id = resolve_channel_id(channel)
    except (urllib.error.URLError, RuntimeError) as exc:
        log.error(f"Cannot resolve the channel: {exc}")
        return 1

    channel_name = name
    if not channel_name:
        try:
            channel_name = fetch_channel_name(channel_id)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            log.error(f"Channel name unavailable: {exc}. Retry or pass --name.")
            return 1
    if not channel_name:
        log.error(f"YouTube returns no name for {channel_id}. Pass --name.")
        return 1

    log.info(f"Channel: {channel_name} ({channel_id})")
    if source == "studio":
        log.info(f"Source: YouTube Studio (cookies {cookies})")
    elif source == "live":
        log.info("Source: public estimate (not the Studio number).")

    if preview and forced_count is not None:
        return _save_preview(channel_name, forced_count, font, color, preview_dir)

    if preview or print_count:
        try:
            count = fetch_count(
                source,
                channel=channel,
                channel_id=channel_id,
                api_key=api_key,
                cookies_path=cookies,
            )
        except urllib.error.HTTPError as exc:
            log.error(f"HTTP error {http_error_detail(exc)}")
            return 1
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
            log.error(f"Error: {exc}")
            return 1
        exact = format_count(count)
        panel = format_panel_count(count)
        if print_count:
            print(f"{channel_name} {exact}")
            if not preview:
                return 0
        if preview:
            return _save_preview(channel_name, panel, font, color, preview_dir)

    assert address is not None
    panel = Panel(address)
    last_count: int | None = None
    last_error: str | None = None
    min_interval = 15 if source == "studio" else 5 if source == "live" else 10
    # Daemon mode retries the BLE connection forever; one-shot runs give up after 3 tries.
    attempts = 3 if once else None

    try:
        connect_device(panel, wipe_slot=wipe_slot, brightness=brightness, attempts=attempts)

        while True:
            try:
                count = fetch_count(
                    source,
                    channel=channel,
                    channel_id=channel_id,
                    api_key=api_key,
                    cookies_path=cookies,
                )
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
                # The panel keeps showing the last image it received; we only report, once per distinct error.
                message = (
                    f"HTTP error {http_error_detail(exc)}"
                    if isinstance(exc, urllib.error.HTTPError)
                    else f"Error: {exc}"
                )
                if message != last_error:
                    log.error(message)
                    last_error = message
            else:
                last_error = None
                if count == last_count:
                    log.info(f"unchanged ({count})")
                else:
                    log.info(f"{channel_name} {format_count(count)}")
                    try:
                        display_count(
                            panel,
                            channel_name,
                            format_panel_count(count),
                            color=color,
                            font=font,
                            save_slot=save_slot,
                            animate=not static,
                        )
                        last_count = count
                    except BLE_ERRORS as exc:
                        # last_count is left unchanged, so the next loop sends the count again.
                        log.warning(f"Bluetooth lost ({type(exc).__name__}: {exc}), reconnecting...")
                        disconnect_device(panel)
                        connect_device(panel, wipe_slot=wipe_slot, brightness=brightness, attempts=attempts)
                        continue

            if once:
                break
            time.sleep(max(interval, min_interval))

    except KeyboardInterrupt:
        log.info("Stopped.")
    except BLE_ERRORS as exc:
        log.error(f"Bluetooth: {type(exc).__name__}: {exc}")
        return 1
    finally:
        disconnect_device(panel)
    return 0
