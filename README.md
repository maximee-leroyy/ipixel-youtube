# ipixel-youtube

Live YouTube subscriber counter for iPixel Color 32×32 LED matrices.

Compteur d’abonnés YouTube en live pour une matrice LED **iPixel Color 32×32**.

Le script récupère le nombre d’abonnés de [RYXACORE](https://www.youtube.com/@example), compose une image 32×32 aux couleurs de la chaîne, et l’envoie au panneau via Bluetooth avec [pypixelcolor](https://lucagoc.fr/pypixelcolor/main/).

![Simulation LED 32×32](preview_led.png)

## Prérequis

- Python 3.11+
- Un panneau iPixel Color (testé en 32×32)
- Bluetooth allumé, panneau sous tension

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

Par défaut : chaîne `@example` et l’adresse du panneau déjà configurée.

```bash
python youtube_subs.py
```

Le panneau affiche le nom en blanc, le nombre d’abonnés en cyan, et se met à jour toutes les 15 secondes. Ctrl+C arrête le live ; le dernier écran reste en mémoire (slot 1).

Autre chaîne ou autre panneau :

```bash
python youtube_subs.py --channel @taChaine --address 00000000-0000-0000-0000-000000000000
```

## Simuler sans matériel

Génère `preview_32x32.png` (pixels bruts) et `preview_led.png` (rendu type panneau) :

```bash
python youtube_subs.py --preview
python test_matrix_32.py
```

## Options utiles

| Option | Défaut | Rôle |
| --- | --- | --- |
| `--channel` | `@example` | Handle ou ID `UC…` |
| `--address` | UUID du panneau | Adresse Bluetooth |
| `--interval` | `15` | Secondes entre deux mises à jour |
| `--name` | nom YouTube | Texte en haut du panneau |
| `--color` | cyan RYXACORE | Accent hex, ex. `00d4ff` |
| `--save-slot` | `1` | Slot 1–10 ; `0` = ne pas sauver |
| `--source live` | `live` | Estimation type compteurs publics |
| `--source official` | | YouTube Data API (arrondi, `--api-key` requis) |
| `--preview` | | Simu 32×32 sans Bluetooth |

Variables d’environnement équivalentes : `IPIXEL_ADDRESS`, `YOUTUBE_CHANNEL`, `YOUTUBE_CHANNEL_NAME`, `YOUTUBE_API_KEY`.

## Compteur « live »

L’API officielle YouTube arrondit le nombre d’abonnés au-delà de 1 000. Le mode `--source live` (défaut) utilise les mêmes sources que les compteurs publics (SocialCounts / Mixerno) : c’est une **estimation**, pas le chiffre exact de YouTube Studio.

## Qualité

```bash
uvx ruff check . --fix && uvx ty check .
```
