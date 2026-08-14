"""CLI: fetch a YouTube subscriber count and drive the LED panel."""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
from pathlib import Path

import pypixelcolor

from ipixel.constants import BLE_ERRORS, COOKIE_HELP
from ipixel.debug import debug, set_debug
from ipixel.display.device import connect_device, disconnect_device, display_count
from ipixel.display.render import write_preview
from ipixel.youtube.channel import fetch_channel_name, resolve_channel_id
from ipixel.youtube.counts import fetch_count, format_count
from ipixel.youtube.http import http_error_detail


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ipixel-youtube",
        description="Affiche le nombre d'abonnés YouTube en live sur un iPixel Color.",
    )
    parser.add_argument(
        "--address",
        default=os.environ.get("IPIXEL_ADDRESS", "00000000-0000-0000-0000-000000000000"),
        help="Adresse Bluetooth du panneau. "
        "Ou variable d'environnement IPIXEL_ADDRESS. "
        "Trouve-la avec: python -m pypixelcolor --scan",
    )
    parser.add_argument(
        "--channel",
        default=os.environ.get(
            "YOUTUBE_CHANNEL",
            os.environ.get("YOUTUBE_CHANNEL_ID", "@example"),
        ),
        help="ID de chaîne (UCxxxx) ou handle (@maChaine). Ou variable YOUTUBE_CHANNEL.",
    )
    parser.add_argument(
        "--source",
        choices=("studio", "live", "official"),
        default="studio",
        help="studio = chiffre exact YouTube Studio (cookies du propriétaire). "
        "live = estimation Mixerno/SocialCounts. "
        "official = YouTube Data API arrondie (--api-key).",
    )
    parser.add_argument(
        "--cookies",
        default=os.environ.get("YOUTUBE_COOKIES", "cookies.txt"),
        help="Fichier cookies Netscape (session YouTube Studio). Ou variable YOUTUBE_COOKIES.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("YOUTUBE_API_KEY"),
        help="Clé API YouTube Data v3, seulement pour --source official.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Secondes entre deux requêtes (défaut: 15).",
    )
    parser.add_argument(
        "--color",
        default=None,
        help="Override couleur accent hex. Défaut: palette RYXACORE (bleu/violet/cyan).",
    )
    parser.add_argument(
        "--font",
        default="CUSONG",
        help="Police: CUSONG, SIMSUN ou VCR_OSD_MONO (défaut: CUSONG, plus lisible en 32x32).",
    )
    parser.add_argument(
        "--name",
        default=os.environ.get("YOUTUBE_CHANNEL_NAME"),
        help="Nom affiché en haut du panneau. Par défaut: le vrai nom YouTube (RYXACORE).",
    )
    parser.add_argument(
        "--save-slot",
        type=int,
        default=0,
        help="Slot 1-10 pour sauver en ROM. Défaut: 0 (affichage live, pas de ROM). "
        "La doc pypixelcolor: un slot avec data corrompue peut brick/bootloop. "
        "N'utilise un slot qu'après un envoi OK sans slot.",
    )
    parser.add_argument(
        "--wipe-slot",
        type=int,
        default=1,
        metavar="N",
        help="Efface ce slot à la connexion (défaut: 1, là où le GIF cassé a été sauvé). 0 = ne rien effacer.",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="PNG fixe, sans animation. Défaut: GIF court (reflet) en live, sans slot ROM.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Génère une simu LED dans assets/preview/ sans Bluetooth.",
    )
    parser.add_argument(
        "--preview-dir",
        default=None,
        help="Dossier des PNG/GIF de preview (défaut: assets/preview).",
    )
    parser.add_argument(
        "--preview-count",
        default="1093",
        help="Nombre affiché en mode --preview (défaut: 1093).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Affiche une seule fois puis quitte (le texte reste si --save-slot >= 1).",
    )
    parser.add_argument(
        "--print-count",
        action="store_true",
        help="Affiche le nombre d'abonnés dans le terminal, sans Bluetooth.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("YOUTUBE_DEBUG", "").lower() in {"1", "true", "yes"},
        help="Logs détaillés sur stderr (HTTP, session Studio, extraction). Ou variable YOUTUBE_DEBUG=1.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    set_debug(args.debug)
    debug(
        f"start source={args.source} channel={args.channel} cookies={args.cookies} "
        f"print_count={args.print_count} once={args.once}"
    )

    if args.preview:
        channel_name = args.name or "RYXACORE"
        preview_count = args.preview_count
        if preview_count.isdigit():
            preview_count = format_count(int(preview_count))
        native_path, led_path, gif_path = write_preview(
            channel_name, preview_count, args.font, args.color, args.preview_dir
        )
        print(f"Simu 32x32: {native_path}")
        print(f"Simu LED:   {led_path}")
        print(f"Ouvre le GIF: {gif_path}")
        return 0

    missing = []
    api_key = args.api_key
    if not args.channel:
        missing.append("--channel ou YOUTUBE_CHANNEL")
    if args.source == "official" and api_key is None:
        missing.append("--api-key ou YOUTUBE_API_KEY")
    if args.source == "studio" and not Path(args.cookies).is_file():
        missing.append(f"--cookies ({args.cookies} introuvable)")
    if missing:
        print("Paramètres manquants: " + ", ".join(missing), file=sys.stderr)
        if args.source == "studio":
            print("\n" + COOKIE_HELP, file=sys.stderr)
        else:
            print(
                "\nExemple:\n  ipixel-youtube --channel @taChaine",
                file=sys.stderr,
            )
        return 2

    try:
        channel_id = resolve_channel_id(args.channel)
    except (urllib.error.URLError, RuntimeError) as exc:
        print(f"Impossible de résoudre la chaîne: {exc}", file=sys.stderr)
        return 1

    channel_name = args.name
    if not channel_name:
        try:
            channel_name = fetch_channel_name(channel_id)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            print(f"Nom de chaîne indisponible ({exc}), fallback handle.", file=sys.stderr)
    if not channel_name:
        channel_name = args.channel.lstrip("@")

    print(f"Chaîne: {channel_name} ({channel_id})")
    if args.source == "studio":
        print(f"Source: YouTube Studio (cookies {args.cookies})")
    elif args.source == "live":
        print("Source: estimation publique (pas le chiffre Studio).")

    if args.print_count:
        try:
            count = fetch_count(
                args.source,
                channel=args.channel,
                channel_id=channel_id,
                api_key=api_key,
                cookies_path=args.cookies,
            )
        except urllib.error.HTTPError as exc:
            print(f"Erreur HTTP {http_error_detail(exc)}", file=sys.stderr)
            return 1
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
            print(f"Erreur: {exc}", file=sys.stderr)
            return 1
        print(f"{channel_name} {format_count(count)}")
        return 0

    device: pypixelcolor.Client | None = None
    last_count: int | None = None
    last_error: str | None = None
    min_interval = 15 if args.source == "studio" else 5 if args.source == "live" else 10

    try:
        device = connect_device(args.address, wipe_slot=args.wipe_slot)

        while True:
            try:
                count = fetch_count(
                    args.source,
                    channel=args.channel,
                    channel_id=channel_id,
                    api_key=api_key,
                    cookies_path=args.cookies,
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
                    count_text = format_count(count)
                    print(f"{time.strftime('%H:%M:%S')}  {channel_name} {format_count(count)}")
                    try:
                        display_count(
                            device,
                            channel_name,
                            count_text,
                            color=args.color,
                            font=args.font,
                            save_slot=args.save_slot,
                            animate=not args.static,
                        )
                    except BLE_ERRORS as exc:
                        print(f"Bluetooth perdu ({exc}), reconnexion...", file=sys.stderr)
                        disconnect_device(device)
                        device = connect_device(args.address, wipe_slot=args.wipe_slot)
                        display_count(
                            device,
                            channel_name,
                            count_text,
                            color=args.color,
                            font=args.font,
                            save_slot=args.save_slot,
                            animate=not args.static,
                        )
                    last_count = count
                else:
                    print(f"{time.strftime('%H:%M:%S')}  inchangé ({count})")

            if args.once:
                break
            time.sleep(max(args.interval, min_interval))

    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        if device is not None:
            disconnect_device(device)
    return 0
