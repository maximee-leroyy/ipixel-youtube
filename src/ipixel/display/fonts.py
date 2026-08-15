"""Bitmap fonts and blitting for the 32×32 panel."""

from __future__ import annotations

from PIL import Image

from ipixel.constants import PixelColor

FONT_5X7: dict[str, tuple[str, ...]] = {
    "0": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "2": (" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"),
    "3": (" ### ", "#   #", "    #", "  ## ", "    #", "#   #", " ### "),
    "4": ("   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "),
    "5": ("#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "),
    "6": (" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "),
    "8": (" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "),
    "9": (" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "),
    ".": ("  ", "  ", "  ", "  ", "  ", "##", "##"),
    ",": ("  ", "  ", "  ", "  ", "  ", "##", " #"),
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "),
    "C": (" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "),
    "D": ("#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "F": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "),
    "G": (" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ### "),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": (" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "J": ("  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#   #", "#### ", "#  # ", "#   #", "#   #"),
    "S": (" ### ", "#   #", "#    ", " ### ", "    #", "#   #", " ### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"),
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"),
    " ": ("     ", "     ", "     ", "     ", "     ", "     ", "     "),
    "?": (" ### ", "#   #", "    #", "  ## ", "  #  ", "     ", "  #  "),
}

# Condensed digits for large counts (20.201.148, etc.) on 32×32.
FONT_3X7: dict[str, tuple[str, ...]] = {
    "0": ("###", "# #", "# #", "# #", "# #", "# #", "###"),
    "1": (" # ", "## ", " # ", " # ", " # ", " # ", "###"),
    "2": ("###", "  #", "  #", "###", "#  ", "#  ", "###"),
    "3": ("###", "  #", "  #", "###", "  #", "  #", "###"),
    "4": ("# #", "# #", "# #", "###", "  #", "  #", "  #"),
    "5": ("###", "#  ", "#  ", "###", "  #", "  #", "###"),
    "6": ("###", "#  ", "#  ", "###", "# #", "# #", "###"),
    "7": ("###", "  #", "  #", " # ", " # ", "#  ", "#  "),
    "8": ("###", "# #", "# #", "###", "# #", "# #", "###"),
    "9": ("###", "# #", "# #", "###", "  #", "  #", "###"),
    ".": ("  ", "  ", "  ", "  ", "  ", "##", "##"),
    ",": ("  ", "  ", "  ", "  ", "  ", "##", " #"),
    " ": (" ", " ", " ", " ", " ", " ", " "),
    "?": ("###", "# #", "  #", " # ", " # ", "   ", " # "),
}

FONT_4X5: dict[str, tuple[str, ...]] = {
    "A": (" ## ", "#  #", "####", "#  #", "#  #"),
    "B": ("### ", "#  #", "### ", "#  #", "### "),
    "C": (" ## ", "#   ", "#   ", "#   ", " ## "),
    "D": ("### ", "#  #", "#  #", "#  #", "### "),
    "E": ("####", "#   ", "### ", "#   ", "####"),
    "F": ("####", "#   ", "### ", "#   ", "#   "),
    "G": (" ###", "#   ", "# ##", "#  #", " ###"),
    "H": ("#  #", "#  #", "####", "#  #", "#  #"),
    "I": ("####", " #  ", " #  ", " #  ", "####"),
    "J": ("  ##", "   #", "   #", "#  #", " ## "),
    "K": ("#  #", "# # ", "##  ", "# # ", "#  #"),
    "L": ("#   ", "#   ", "#   ", "#   ", "####"),
    "M": ("#  #", "####", "#  #", "#  #", "#  #"),
    "N": ("#  #", "## #", "# ##", "#  #", "#  #"),
    "O": (" ## ", "#  #", "#  #", "#  #", " ## "),
    "P": ("### ", "#  #", "### ", "#   ", "#   "),
    "Q": (" ## ", "#  #", "#  #", "# # ", " # #"),
    "R": ("### ", "#  #", "### ", "# # ", "#  #"),
    "S": (" ###", "#   ", " ## ", "   #", "### "),
    "T": ("####", " #  ", " #  ", " #  ", " #  "),
    "U": ("#  #", "#  #", "#  #", "#  #", " ## "),
    "V": ("#  #", "#  #", "#  #", " ## ", "  # "),
    "W": ("#  #", "#  #", "#  #", "####", "#  #"),
    "X": ("#  #", " ## ", "  # ", " ## ", "#  #"),
    "Y": ("#  #", "#  #", " ## ", " #  ", " #  "),
    "Z": ("####", "   #", " ## ", "#   ", "####"),
    " ": ("    ", "    ", "    ", "    ", "    "),
    "?": (" ## ", "#  #", "  # ", "    ", " #  "),
}

FONT_3X5: dict[str, tuple[str, ...]] = {
    "0": ("###", "# #", "# #", "# #", "###"),
    "1": (" # ", "## ", " # ", " # ", "###"),
    "2": ("###", "  #", "###", "#  ", "###"),
    "3": ("###", "  #", "###", "  #", "###"),
    "4": ("# #", "# #", "###", "  #", "  #"),
    "5": ("###", "#  ", "###", "  #", "###"),
    "6": ("###", "#  ", "###", "# #", "###"),
    "7": ("###", "  #", "  #", " # ", " # "),
    "8": ("###", "# #", "###", "# #", "###"),
    "9": ("###", "# #", "###", "  #", "###"),
    ".": ("  ", "  ", "  ", "##", "##"),
    ",": ("  ", "  ", "  ", "##", " #"),
    "A": (" # ", "# #", "###", "# #", "# #"),
    "B": ("## ", "# #", "## ", "# #", "## "),
    "C": (" ##", "#  ", "#  ", "#  ", " ##"),
    "D": ("## ", "# #", "# #", "# #", "## "),
    "E": ("###", "#  ", "## ", "#  ", "###"),
    "F": ("###", "#  ", "## ", "#  ", "#  "),
    "G": (" ##", "#  ", "# #", "# #", " ##"),
    "H": ("# #", "# #", "###", "# #", "# #"),
    "I": ("###", " # ", " # ", " # ", "###"),
    "J": ("  #", "  #", "  #", "# #", " # "),
    "K": ("# #", "# #", "## ", "# #", "# #"),
    "L": ("#  ", "#  ", "#  ", "#  ", "###"),
    "M": ("# #", "###", "# #", "# #", "# #"),
    "N": ("# #", "## ", "# #", "# #", "# #"),
    "O": (" # ", "# #", "# #", "# #", " # "),
    "P": ("## ", "# #", "## ", "#  ", "#  "),
    "Q": (" # ", "# #", "# #", " ##", "  #"),
    "R": ("## ", "# #", "## ", "# #", "# #"),
    "S": (" ##", "#  ", " # ", "  #", "## "),
    "T": ("###", " # ", " # ", " # ", " # "),
    "U": ("# #", "# #", "# #", "# #", " # "),
    "V": ("# #", "# #", "# #", "# #", " # "),
    "W": ("# #", "# #", "# #", "###", "# #"),
    "X": ("# #", "# #", " # ", "# #", "# #"),
    "Y": ("# #", "# #", " # ", " # ", " # "),
    "Z": ("###", "  #", " # ", "#  ", "###"),
    " ": (" ", " ", " ", " ", " "),
    "?": ("## ", "  #", " # ", "   ", " # "),
}

# Same digits, 1-wide baseline dots for counts like 20.201.148.
FONT_3X5_NARROW: dict[str, tuple[str, ...]] = {
    **FONT_3X5,
    ".": (" ", " ", " ", "#", "#"),
    ",": (" ", " ", " ", "#", "#"),
}

BitmapFont = dict[str, tuple[str, ...]]
CountStyle = tuple[str, BitmapFont, int, int | None]


def _name_lines(name: str) -> list[str]:
    folded = name.replace(" ", "").upper()
    if len(folded) <= 5:
        return [folded]
    mid = (len(folded) + 1) // 2
    return [folded[:mid], folded[mid:]]


def _glyph(char: str, font: BitmapFont = FONT_5X7) -> tuple[str, ...]:
    unknown = font.get("?", FONT_5X7["?"])
    return font.get(char.upper(), unknown)


def _is_separator(char: str) -> bool:
    return char in {".", ","}


def _glyph_gaps(text: str, gap: int, separator_gap: int | None) -> list[int]:
    if len(text) < 2:
        return []
    tight = gap if separator_gap is None else separator_gap
    return [
        tight if _is_separator(text[index]) or _is_separator(text[index + 1]) else gap
        for index in range(len(text) - 1)
    ]


def _fit_count(text: str, max_width: int) -> CountStyle:
    """5×7 below 1 million when it fits; compact 3×5 for bigger counts."""
    styles: tuple[tuple[BitmapFont, int, int | None], ...] = (
        (FONT_5X7, 2, None),
        (FONT_5X7, 1, None),
        (FONT_5X7, 0, None),
        (FONT_3X5, 1, None),
        (FONT_3X5, 1, 0),
        (FONT_3X5_NARROW, 1, 0),
        (FONT_3X5_NARROW, 0, 0),
        (FONT_3X7, 1, 0),
        (FONT_3X7, 0, 0),
    )
    for font, gap, separator_gap in styles:
        if _text_pixel_size(text, gap, font, separator_gap)[0] <= max_width:
            return text, font, gap, separator_gap
    compact = "".join(char for char in text if not _is_separator(char))
    for font, gap, separator_gap in styles:
        if _text_pixel_size(compact, gap, font, separator_gap)[0] <= max_width:
            return compact, font, gap, separator_gap
    return compact, FONT_3X5_NARROW, 0, 0


def _text_pixel_size(
    text: str,
    gap: int = 1,
    font: BitmapFont = FONT_5X7,
    separator_gap: int | None = None,
) -> tuple[int, int]:
    if not text:
        return 0, 0
    glyphs = [_glyph(char, font) for char in text]
    width = sum(len(glyph[0]) for glyph in glyphs) + sum(_glyph_gaps(text, gap, separator_gap))
    height = len(glyphs[0])
    return width, height


def _blit_glyph(
    image: Image.Image,
    glyph: tuple[str, ...],
    origin_x: int,
    origin_y: int,
    color: PixelColor,
) -> None:
    pixels = image.load()
    if pixels is None:
        return
    width, height = image.size
    for row, line in enumerate(glyph):
        for col, cell in enumerate(line):
            if cell == " ":
                continue
            x = origin_x + col
            y = origin_y + row
            if 0 <= x < width and 0 <= y < height:
                pixels[x, y] = color


def _blit_text(
    image: Image.Image,
    text: str,
    top: int,
    color: PixelColor,
    gap: int = 2,
    x_min: int = 0,
    x_max: int | None = None,
    font: BitmapFont = FONT_5X7,
    separator_gap: int | None = None,
) -> None:
    glyphs = [_glyph(char, font) for char in text]
    total_w, _total_h = _text_pixel_size(text, gap, font, separator_gap)
    right = image.width if x_max is None else x_max
    cursor = x_min + max(0, (right - x_min - total_w) // 2)
    gaps = _glyph_gaps(text, gap, separator_gap)
    for index, glyph in enumerate(glyphs):
        _blit_glyph(image, glyph, cursor, top, color)
        cursor += len(glyph[0])
        if index < len(gaps):
            cursor += gaps[index]


def _draw_corners(image: Image.Image, color: PixelColor, size: int = 3) -> None:
    width, height = image.size
    pixels = image.load()
    if pixels is None:
        return
    for i in range(size):
        pixels[i, 0] = color
        pixels[0, i] = color
        pixels[width - 1 - i, 0] = color
        pixels[width - 1, i] = color
        pixels[i, height - 1] = color
        pixels[0, height - 1 - i] = color
        pixels[width - 1 - i, height - 1] = color
        pixels[width - 1, height - 1 - i] = color
