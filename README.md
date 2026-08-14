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
  cli.py                 # argparse + boucle live
  youtube/               # cookies, Studio, APIs publiques
  display/               # polices bitmap, logo pyxelate, GIF, BLE
tests/
```

## Prérequis

- Python 3.11+
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

## Trouver le panneau

```bash
python -m pypixelcolor --scan
```

Note l’adresse (sur macOS c’est souvent un UUID, pas une adresse MAC) :

```text
LED_BLE_XXXXXXXX (00000000-0000-0000-0000-000000000000)
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

Autre chaîne ou autre panneau :

```bash
ipixel-youtube --channel @taChaine --address 00000000-0000-0000-0000-000000000000
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
| `--address` | UUID du panneau | Adresse Bluetooth |
| `--interval` | `15` | Secondes entre deux mises à jour |
| `--name` | nom YouTube | Texte en haut du panneau |
| `--brightness` | `100` | Luminosité globale du panneau 0–100 (`IPIXEL_BRIGHTNESS`) |
| `--color` | cyan RYXACORE | Accent hex, ex. `00d4ff` |
| `--save-slot` | `0` | Slot 1–10 en ROM ; `0` = affichage live. Ne pas sauver un GIF. |
| `--wipe-slot` | `1` | Efface ce slot à la connexion (`0` = ne rien effacer). |
| `--static` | | PNG fixe, sans animation. |
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
