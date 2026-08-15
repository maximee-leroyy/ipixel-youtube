# ipixel-youtube

Live YouTube subscriber counter for iPixel Color 32×32 LED matrices.

Compteur d’abonnés YouTube en live pour une matrice LED **iPixel Color 32×32**.

Le script récupère le nombre d’abonnés de [RYXACORE](https://www.youtube.com/@example), pixelise le vrai logo YouTube (SVG) avec [pyxelate](https://github.com/sedthh/pyxelate), compose le 32×32, et l’envoie au panneau via Bluetooth avec [pypixelcolor](https://lucagoc.fr/pypixelcolor/main/).

![Simulation LED 32×32](assets/preview/led.png)

## Architecture

```text
assets/
  youtube.svg            # marque officielle Simple Icons
  youtube.png            # fallback raster
  preview/               # PNG/GIF générés (--preview)
src/ipixel/
  cli.py                 # Click + boucle live
  youtube/               # cookies, Studio, APIs publiques
  display/               # polices bitmap, logo pyxelate, GIF, BLE
tests/
```

## Prérequis

- Python 3.13.7
- Un panneau iPixel Color (testé en 32×32)
- Bluetooth allumé, panneau sous tension

## Installation

```bash
uv sync
```

Sans uv :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Container (Linux / GHCR)

Image Linux **amd64** et **arm64** (Pi 5) : `ghcr.io/maximee-leroyy/ipixel-youtube`.

```bash
nerdctl pull ghcr.io/maximee-leroyy/ipixel-youtube:latest
nerdctl compose run --rm ipixel scan
export IPIXEL_ADDRESS=AA:BB:CC:DD:EE:FF
nerdctl compose up -d
```

Sans Compose :

```bash
nerdctl run --rm --network host --privileged \
  -v /run/dbus/system_bus_socket:/host/dbus/system_bus_socket \
  -v ./cookies.txt:/app/cookies.txt \
  -e IPIXEL_ADDRESS=AA:BB:CC:DD:EE:FF \
  ghcr.io/maximee-leroyy/ipixel-youtube:latest
```

`--print-count` / `--preview` / `--source live` : `nerdctl compose run --rm ipixel --print-count`. Dessin : `-v ./mon.gif:/app/drawing.gif:ro` puis `--image /app/drawing.gif`.

Scan et panneau BLE : **Linux** (Pi 5), BlueZ hôte allumé (`sudo systemctl enable --now bluetooth`). Sur Mac, nerdctl est une VM sans HCI : `--print-count` seulement.

Build local : `nerdctl compose build`. L’image est publiée sur GHCR à chaque push sur `main` (Actions → Container image). Le paquet GHCR est privé au premier push : Package settings → Change visibility → Public.

## Trouver le panneau

```bash
nerdctl compose run --rm ipixel scan
```

Note l’adresse Linux (MAC `AA:BB:CC:…`), pas un UUID macOS :

```text
LED_BLE_XXXXXXXX (AA:BB:CC:DD:EE:FF)
```

## Lancer

Le chiffre **exact** (celui de YouTube Studio → *Abonnés actuels*, ex. 1 093) n’est pas public. Il faut la session du propriétaire.

1. Connecte-toi à [YouTube Studio](https://studio.youtube.com) avec le compte de la chaîne
2. Exporte les cookies (extension Chrome **Get cookies.txt LOCALLY**)
3. Enregistre le fichier `cookies.txt` à la racine du projet (déjà dans `.gitignore`)

```bash
ipixel-youtube
# équivalent :
python -m ipixel
```

Vérifier le chiffre sans Bluetooth :

```bash
ipixel-youtube --print-count
```

Le panneau affiche le nom, le nombre d’abonnés en cyan, et un **reflet** en boucle (GIF court, sans ROM). Ctrl+C arrête le live. `--static` envoie un PNG fixe. N’utilise `--save-slot 1` qu’avec `--static`, après un affichage correct.

## Afficher un dessin (sans HUD YouTube)

À la place de l’icône YouTube + compteur + nom de chaîne, tu peux envoyer n’importe quel PNG, JPEG ou GIF. L’image est recadrée/redimensionnée en **32×32** (nearest-neighbor, centré sur fond noir — idéal pour du pixel art).

Prépare un PNG 32×32 (Aseprite, Piskel, Photoshop…) puis :

```bash
# Simu LED sans Bluetooth
ipixel-youtube --image dessin.png --preview

# Envoi au panneau
ipixel-youtube --image dessin.png --address AA:BB:CC:DD:EE:FF
```

Un GIF animé est envoyé tel quel (boucle). `--static` n’envoie que la première frame en PNG.

## Autre chaîne ou autre panneau

```bash
ipixel-youtube --channel @taChaine --address AA:BB:CC:DD:EE:FF
```

Estimation publique (arrondie / interpolée, **pas** le 1 093 Studio) :

```bash
ipixel-youtube --source live
```

## Simuler sans matériel

Génère `assets/preview/preview.gif` en grande simu LED (le 32×32 brut est illisible à l’écran) :

```bash
ipixel-youtube --preview
pytest tests/test_matrix_32.py
```

## Options utiles

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--channel` | `@example` | Handle ou ID `UC…` |
| `--address` | *(requis)* | Adresse Bluetooth (`IPIXEL_ADDRESS`) |
| `--interval` | `15` | Secondes entre deux mises à jour |
| `--name` | nom YouTube | Texte en haut du panneau |
| `--brightness` | `100` | Luminosité globale du panneau 0–100 (`IPIXEL_BRIGHTNESS`) |
| `--color` | cyan RYXACORE | Accent hex, ex. `00d4ff` |
| `--save-slot` | `0` | Slot 1–10 en ROM ; `0` = affichage live. Ne pas sauver un GIF. |
| `--wipe-slot` | `1` | Efface ce slot à la connexion (`0` = ne rien effacer). |
| `--static` | | PNG fixe, sans animation. |
| `--image` | | PNG/GIF/JPEG à la place du HUD YouTube (32×32). |
| `--source studio` | `studio` | Chiffre exact YouTube Studio (`--cookies`) |
| `--cookies` | `cookies.txt` | Session Netscape du propriétaire |
| `--source live` | | Estimation type compteurs publics |
| `--source official` | | YouTube Data API (arrondi, `--api-key` requis) |
| `--print-count` | | Affiche le nombre dans le terminal, sans Bluetooth |
| `--debug` | | Logs HTTP / session Studio sur stderr |
| `--preview` | | Simu 32×32 sans Bluetooth, fichiers dans `assets/preview/` |
| `--preview-dir` | `assets/preview` | Dossier des PNG/GIF générés |

Variables d’environnement équivalentes : `IPIXEL_ADDRESS`, `IPIXEL_BRIGHTNESS`, `YOUTUBE_CHANNEL`, `YOUTUBE_CHANNEL_NAME`, `YOUTUBE_API_KEY`, `YOUTUBE_COOKIES`, `YOUTUBE_DEBUG`.

## Compteur exact vs « live »

L’API officielle YouTube arrondit le nombre d’abonnés au-delà de 1 000 (1 093 → 1 090 / 1 100). Les compteurs publics (SocialCounts / Mixerno) interpolent entre ces paliers : ce n’est **pas** *Abonnés actuels* dans Studio.

`--source studio` (défaut) lit ce chiffre via ta session YouTube Studio. Les cookies expirent de temps en temps : réexporte `cookies.txt` si le script parle de session expirée.

## Qualité

```bash
uvx ruff check . --fix && uvx ty check src tests
uv run pytest
```
