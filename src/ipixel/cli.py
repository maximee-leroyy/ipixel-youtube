"""CLI: fetch a YouTube subscriber count and drive the LED panel."""

from __future__ import annotations

import sys
import time
import urllib.error
from pathlib import Path

import click
import pypixelcolor

from ipixel.constants import BLE_ERRORS, COOKIE_HELP, DEFAULT_BRIGHTNESS
from ipixel.debug import debug as log_debug
from ipixel.debug import set_debug
from ipixel.display.device import clamp_brightness, connect_device, disconnect_device, display_count, display_drawing
from ipixel.display.drawing import load_drawing, write_drawing_preview
from ipixel.display.render import write_preview
from ipixel.youtube.channel import fetch_channel_name, resolve_channel_id
from ipixel.youtube.counts import fetch_count, format_count, format_panel_count
from ipixel.youtube.http import http_error_detail


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
    print(f"{channel_name} {count_text}")
    print(f"Simu 32x32: {native_path}")
    print(f"Simu LED:   {led_path}")
    print(f"Ouvre le GIF: {gif_path}")
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
            print(f"Dessin illisible: {exc}", file=sys.stderr)
            return 2
        print(f"Dessin: {image_path}")
        print(f"Simu 32x32: {native_path}")
        print(f"Simu LED:   {led_path}")
        print(f"Ouvre le GIF: {gif_path}")
        return 0

    try:
        load_drawing(image_path)
    except (OSError, ValueError) as exc:
        print(f"Dessin illisible: {exc}", file=sys.stderr)
        return 2

    device: pypixelcolor.Client | None = None
    try:
        device = connect_device(address, wipe_slot=wipe_slot, brightness=brightness)
        display_drawing(device, image_path, save_slot=save_slot, static=static)
    except KeyboardInterrupt:
        print("\nArrêt.")
    except BLE_ERRORS as exc:
        print(f"Bluetooth: {exc}", file=sys.stderr)
        return 1
    finally:
        if device is not None:
            disconnect_device(device)
    return 0


@click.command(
    name="ipixel-youtube",
    context_settings={"help_option_names": ["-h", "--help"], "show_default": True},
)
@click.option(
    "--address",
    envvar="IPIXEL_ADDRESS",
    default="00000000-0000-0000-0000-000000000000",
    show_envvar=True,
    help="Adresse Bluetooth du panneau. Trouve-la avec: python -m pypixelcolor --scan",
)
@click.option(
    "--channel",
    envvar=["YOUTUBE_CHANNEL", "YOUTUBE_CHANNEL_ID"],
    default="@example",
    show_envvar=True,
    help="ID de chaîne (UCxxxx) ou handle (@maChaine).",
)
@click.option(
    "--source",
    type=click.Choice(["studio", "live", "official"], case_sensitive=True),
    default="studio",
    help="studio = chiffre exact YouTube Studio (cookies du propriétaire). "
    "live = estimation Mixerno/SocialCounts. "
    "official = YouTube Data API arrondie (--api-key).",
)
@click.option(
    "--cookies",
    envvar="YOUTUBE_COOKIES",
    default="cookies.txt",
    show_envvar=True,
    help="Fichier cookies Netscape (session YouTube Studio).",
)
@click.option(
    "--api-key",
    envvar="YOUTUBE_API_KEY",
    default=None,
    show_envvar=True,
    help="Clé API YouTube Data v3, seulement pour --source official.",
)
@click.option(
    "--interval",
    type=int,
    default=15,
    help="Secondes entre deux requêtes.",
)
@click.option(
    "--color",
    default=None,
    help="Override couleur accent hex. Défaut: palette RYXACORE (bleu/violet/cyan).",
)
@click.option(
    "--brightness",
    type=int,
    metavar="0-100",
    envvar="IPIXEL_BRIGHTNESS",
    default=DEFAULT_BRIGHTNESS,
    show_envvar=True,
    help="Luminosité du panneau 0-100 (réglage matériel, ignoré par --preview).",
)
@click.option(
    "--font",
    default="CUSONG",
    help="Police: CUSONG, SIMSUN ou VCR_OSD_MONO (plus lisible en 32x32).",
)
@click.option(
    "--name",
    envvar="YOUTUBE_CHANNEL_NAME",
    default=None,
    show_envvar=True,
    help="Nom affiché en haut du panneau. Par défaut: le vrai nom YouTube (RYXACORE).",
)
@click.option(
    "--save-slot",
    type=int,
    default=0,
    help="Slot 1-10 pour sauver en ROM. 0 = affichage live, pas de ROM. "
    "La doc pypixelcolor: un slot avec data corrompue peut brick/bootloop. "
    "N'utilise un slot qu'après un envoi OK sans slot.",
)
@click.option(
    "--wipe-slot",
    type=int,
    metavar="N",
    default=1,
    help="Efface ce slot à la connexion (là où le GIF cassé a été sauvé). 0 = ne rien effacer.",
)
@click.option(
    "--static",
    is_flag=True,
    help="PNG fixe, sans animation. Défaut: GIF court (reflet) en live, sans slot ROM.",
)
@click.option(
    "--image",
    "image_path",
    type=click.Path(exists=True, dir_okay=False, path_type=str),
    default=None,
    help="PNG/GIF/JPEG à afficher à la place du HUD YouTube. Redimensionné en 32×32.",
)
@click.option(
    "--preview",
    is_flag=True,
    help="Génère une simu LED dans assets/preview/ sans Bluetooth. "
    "Avec --image: simule le dessin. Sinon: utilise le compteur de --channel/--source, "
    "sauf si --preview-count est fourni.",
)
@click.option(
    "--preview-dir",
    default=None,
    help="Dossier des PNG/GIF de preview (défaut: assets/preview).",
)
@click.option(
    "--preview-count",
    default=None,
    help="Force un nombre en --preview au lieu de récupérer le vrai compteur.",
)
@click.option(
    "--once",
    is_flag=True,
    help="Affiche une seule fois puis quitte (le texte reste si --save-slot >= 1).",
)
@click.option(
    "--print-count",
    is_flag=True,
    help="Affiche le nombre d'abonnés dans le terminal, sans Bluetooth.",
)
@click.option(
    "--debug",
    is_flag=True,
    envvar="YOUTUBE_DEBUG",
    show_envvar=True,
    help="Logs détaillés sur stderr (HTTP, session Studio, extraction).",
)
def main(
    address: str,
    channel: str,
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
    """Affiche le nombre d'abonnés YouTube en live sur un iPixel Color."""
    set_debug(debug)
    log_debug(
        f"start source={source} channel={channel} cookies={cookies} "
        f"image={image_path} print_count={print_count} once={once} brightness={brightness}"
    )

    try:
        brightness = clamp_brightness(brightness)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    if image_path:
        return _run_drawing(
            image_path,
            address=address,
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
    elif preview and source == "studio" and not Path(cookies).is_file():
        return _save_preview(name or "RYXACORE", format_count(1093), font, color, preview_dir)

    missing = []
    if not channel:
        missing.append("--channel ou YOUTUBE_CHANNEL")
    if source == "official" and api_key is None:
        missing.append("--api-key ou YOUTUBE_API_KEY")
    if source == "studio" and not Path(cookies).is_file():
        missing.append(f"--cookies ({cookies} introuvable)")
    if missing:
        print("Paramètres manquants: " + ", ".join(missing), file=sys.stderr)
        if source == "studio":
            print("\n" + COOKIE_HELP, file=sys.stderr)
        else:
            print(
                "\nExemple:\n  ipixel-youtube --channel @taChaine",
                file=sys.stderr,
            )
        return 2

    try:
        channel_id = resolve_channel_id(channel)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Impossible de résoudre la chaîne: {exc}", file=sys.stderr)
        return 1

    channel_name = name
    if not channel_name:
        try:
            channel_name = fetch_channel_name(channel_id)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f"Nom de chaîne indisponible ({exc}), fallback handle.", file=sys.stderr)
    if not channel_name:
        channel_name = channel.lstrip("@")

    print(f"Chaîne: {channel_name} ({channel_id})")
    if source == "studio":
        print(f"Source: YouTube Studio (cookies {cookies})")
    elif source == "live":
        print("Source: estimation publique (pas le chiffre Studio).")

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
            print(f"Erreur HTTP {http_error_detail(exc)}", file=sys.stderr)
            return 1
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
            print(f"Erreur: {exc}", file=sys.stderr)
            return 1
        exact = format_count(count)
        panel = format_panel_count(count)
        if print_count:
            print(f"{channel_name} {exact}")
            if not preview:
                return 0
        if preview:
            return _save_preview(channel_name, panel, font, color, preview_dir)

    device: pypixelcolor.Client | None = None
    last_count: int | None = None
    last_error: str | None = None
    min_interval = 15 if source == "studio" else 5 if source == "live" else 10

    try:
        device = connect_device(address, wipe_slot=wipe_slot, brightness=brightness)

        while True:
            try:
                count = fetch_count(
                    source,
                    channel=channel,
                    channel_id=channel_id,
                    api_key=api_key,
                    cookies_path=cookies,
                )
            except urllib.error.HTTPError as exc:
                if last_count is not None:
                    message = f"Studio indisponible, on garde {last_count}"
                    shown = f"{time.strftime('%H:%M:%S')}  {message}"
                else:
                    message = f"Erreur HTTP {http_error_detail(exc)}"
                    shown = message
                if message != last_error:
                    print(shown, file=sys.stderr)
                    last_error = message
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
                if last_count is not None:
                    message = f"Studio indisponible, on garde {last_count}"
                    shown = f"{time.strftime('%H:%M:%S')}  {message}"
                else:
                    message = f"Erreur: {exc}"
                    shown = message
                if message != last_error:
                    print(shown, file=sys.stderr)
                    last_error = message
            else:
                last_error = None
                if count != last_count:
                    count_text = format_panel_count(count)
                    print(f"{time.strftime('%H:%M:%S')}  {channel_name} {format_count(count)}")
                    try:
                        display_count(
                            device,
                            channel_name,
                            count_text,
                            color=color,
                            font=font,
                            save_slot=save_slot,
                            animate=not static,
                        )
                    except BLE_ERRORS as exc:
                        print(f"Bluetooth perdu ({exc}), reconnexion...", file=sys.stderr)
                        disconnect_device(device)
                        device = connect_device(address, wipe_slot=wipe_slot, brightness=brightness)
                        display_count(
                            device,
                            channel_name,
                            count_text,
                            color=color,
                            font=font,
                            save_slot=save_slot,
                            animate=not static,
                        )
                    last_count = count
                else:
                    print(f"{time.strftime('%H:%M:%S')}  inchangé ({count})")

            if once:
                break
            time.sleep(max(interval, min_interval))

    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        if device is not None:
            disconnect_device(device)
    return 0
