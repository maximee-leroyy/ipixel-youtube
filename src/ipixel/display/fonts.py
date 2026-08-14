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

BitmapFont = dict[str, tuple[str, ...]]


def _name_lines(name: str) -> list[str]:
    compact = name.replace(" ", "").upper()
    if len(compact) <= 5:
        return [compact]
    mid = (len(compact) + 1) // 2
    return [compact[:mid], compact[mid:]]


def _glyph(char: str, font: BitmapFont = FONT_5X7) -> tuple[str, ...]:
    return font.get(char.upper(), font.get("?", FONT_5X7["?"]))


def _text_pixel_size(
    text: str,
    gap: int = 1,
    font: BitmapFont = FONT_5X7,
) -> tuple[int, int]:
    if not text:
        return 0, 0
    glyphs = [_glyph(char, font) for char in text]
    width = sum(len(glyph[0]) for glyph in glyphs) + gap * (len(glyphs) - 1)
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
) -> None:
    glyphs = [_glyph(char, font) for char in text]
    total_w, _total_h = _text_pixel_size(text, gap, font)
    right = image.width if x_max is None else x_max
    cursor = x_min + max(0, (right - x_min - total_w) // 2)
    for glyph in glyphs:
        _blit_glyph(image, glyph, cursor, top, color)
        cursor += len(glyph[0]) + gap


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
