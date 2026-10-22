from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from skimage.color import rgb2lab

from config import Palette

# Curated solid LEGO colors (no duplicates, no unrenderable transparent/metallic colors)
CLASSIC_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    # Neutrals
    "white": (255, 255, 255),
    "black": (5, 19, 29),
    # Modern Bluish Grays
    "very_light_bluish_gray": (230, 227, 224),
    "light_bluish_gray": (160, 165, 169),
    "dark_bluish_gray": (108, 110, 104),
    # Reds / pinks
    "red": (201, 26, 9),
    "dark_red": (114, 14, 15),
    "rust": (179, 16, 4),
    "salmon": (242, 112, 94),
    "coral": (255, 105, 143),
    "pink": (252, 151, 172),
    "medium_dark_pink": (247, 133, 177),
    "bright_pink": (228, 173, 200),
    "light_pink": (254, 204, 207),
    "dark_pink": (200, 112, 160),
    "light_purple": (205, 98, 152),
    "magenta": (146, 57, 120),
    # Oranges / yellows
    "orange": (254, 138, 24),
    "medium_orange": (240, 143, 28),
    "dark_orange": (169, 85, 0),
    "light_orange": (249, 186, 97),
    "bright_light_orange": (248, 187, 61),
    "yellow": (242, 205, 55),
    "light_yellow": (251, 230, 150),
    "bright_light_yellow": (255, 240, 58),
    "cool_yellow": (255, 236, 108),
    # Greens
    "green": (35, 120, 65),
    "dark_green": (24, 70, 50),
    "bright_green": (75, 159, 74),
    "medium_green": (115, 220, 161),
    "light_green": (194, 218, 184),
    "lime": (187, 233, 11),
    "yellowish_green": (223, 238, 165),
    "olive_green": (155, 154, 90),
    "sand_green": (160, 188, 172),
    # Blues / teals
    "blue": (0, 85, 191),
    "dark_blue": (10, 52, 99),
    "dark_blue_violet": (32, 50, 176),
    "medium_blue": (90, 147, 219),
    "sky_blue": (125, 193, 216),
    "light_blue": (180, 210, 227),
    "bright_light_blue": (159, 195, 233),
    "dark_azure": (7, 139, 201),
    "medium_azure": (54, 174, 191),
    "dark_turquoise": (0, 143, 155),
    "light_turquoise": (85, 165, 175),
    "aqua": (179, 215, 209),
    "light_aqua": (211, 242, 234),
    "sand_blue": (96, 116, 161),
    # Purples
    "purple": (129, 0, 123),
    "dark_purple": (63, 54, 145),
    "medium_lilac": (76, 47, 146),
    "medium_lavender": (160, 110, 185),
    "lavender": (225, 213, 237),
    # Browns / earth tones
    "reddish_brown": (88, 42, 18),
    "dark_brown": (53, 33, 0),
    "brown": (124, 80, 58),
    "tan": (228, 205, 158),
    "warm_tan": (204, 163, 115),
    "dark_tan": (149, 138, 115),
    "sand_red": (149, 121, 119),
    # Skin tones
    "light_nougat": (246, 215, 179),
    "nougat": (208, 145, 104),
    "medium_nougat": (170, 125, 85),
    "medium_dark_flesh": (204, 112, 42),
}

# Extended palette including vintage grays, transparents, and metallics (with duplicates removed)
EXTENDED_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    **CLASSIC_PALETTE,
    # Vintage grays
    "very_light_gray": (230, 227, 218),
    "light_gray": (155, 161, 157),
    "dark_gray": (109, 110, 92),
    # Transparents (unique RGB values only; trans_red and trans_orange excluded as duplicates)
    "trans_clear": (252, 252, 252),
    "trans_yellow": (245, 205, 42),
    "trans_green": (132, 182, 141),
    "trans_light_blue": (104, 188, 197),
    "trans_dark_blue": (0, 32, 160),
    # Metallics / pearls
    "flat_silver": (137, 135, 136),
    "metallic_silver": (165, 169, 180),
    "chrome_silver": (224, 224, 224),
    "chrome_gold": (187, 165, 61),
    "pearl_gold": (170, 127, 46),
    "pearl_dark_gray": (107, 90, 90),
}

# Backwards compatibility alias
LEGO_PALETTE: Final[dict[str, tuple[int, int, int]]] = CLASSIC_PALETTE

MONOCHROME_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "white": (255, 255, 255),
    "very_light_bluish_gray": (230, 227, 224),
    "very_light_gray": (230, 227, 218),
    "light_bluish_gray": (160, 165, 169),
    "light_gray": (155, 161, 157),
    "flat_silver": (137, 135, 136),
    "metallic_silver": (165, 169, 180),
    "chrome_silver": (224, 224, 224),
    "dark_bluish_gray": (108, 110, 104),
    "dark_gray": (109, 110, 92),
    "pearl_dark_gray": (107, 90, 90),
    "black": (5, 19, 29),
}

PASTEL_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "salmon": (242, 112, 94),
    "coral": (255, 105, 143),
    "pink": (252, 151, 172),
    "light_pink": (254, 204, 207),
    "bright_pink": (228, 173, 200),
    "light_purple": (205, 98, 152),
    "light_yellow": (251, 230, 150),
    "bright_light_yellow": (255, 240, 58),
    "cool_yellow": (255, 236, 108),
    "light_green": (194, 218, 184),
    "yellowish_green": (223, 238, 165),
    "sand_green": (160, 188, 172),
    "sky_blue": (125, 193, 216),
    "light_blue": (180, 210, 227),
    "bright_light_blue": (159, 195, 233),
    "light_turquoise": (85, 165, 175),
    "aqua": (179, 215, 209),
    "light_aqua": (211, 242, 234),
    "sand_blue": (96, 116, 161),
    "medium_lavender": (160, 110, 185),
    "lavender": (225, 213, 237),
    "tan": (228, 205, 158),
    "warm_tan": (204, 163, 115),
    "dark_tan": (149, 138, 115),
    "light_nougat": (246, 215, 179),
    "trans_clear": (252, 252, 252),
    "trans_yellow": (245, 205, 42),
    "trans_green": (132, 182, 141),
    "trans_light_blue": (104, 188, 197),
}

CRAYON_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "white": (255, 255, 255),
    "black": (5, 19, 29),
    "red": (201, 26, 9),
    "rust": (179, 16, 4),
    "orange": (254, 138, 24),
    "medium_orange": (240, 143, 28),
    "bright_light_orange": (248, 187, 61),
    "yellow": (242, 205, 55),
    "green": (35, 120, 65),
    "bright_green": (75, 159, 74),
    "lime": (187, 233, 11),
    "blue": (0, 85, 191),
    "medium_blue": (90, 147, 219),
    "dark_azure": (7, 139, 201),
    "medium_azure": (54, 174, 191),
    "dark_turquoise": (0, 143, 155),
    "purple": (129, 0, 123),
    "dark_purple": (63, 54, 145),
    "magenta": (146, 57, 120),
    "pink": (252, 151, 172),
}

EARTH_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "reddish_brown": (88, 42, 18),
    "dark_brown": (53, 33, 0),
    "brown": (124, 80, 58),
    "tan": (228, 205, 158),
    "warm_tan": (204, 163, 115),
    "dark_tan": (149, 138, 115),
    "sand_red": (149, 121, 119),
    "nougat": (208, 145, 104),
    "medium_nougat": (170, 125, 85),
    "medium_dark_flesh": (204, 112, 42),
    "olive_green": (155, 154, 90),
    "sand_green": (160, 188, 172),
    "dark_green": (24, 70, 50),
    "sand_blue": (96, 116, 161),
    "dark_orange": (169, 85, 0),
    "chrome_gold": (187, 165, 61),
    "pearl_gold": (170, 127, 46),
}

COOL_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "green": (35, 120, 65),
    "dark_green": (24, 70, 50),
    "bright_green": (75, 159, 74),
    "medium_green": (115, 220, 161),
    "light_green": (194, 218, 184),
    "lime": (187, 233, 11),
    "yellowish_green": (223, 238, 165),
    "olive_green": (155, 154, 90),
    "sand_green": (160, 188, 172),
    "blue": (0, 85, 191),
    "dark_blue": (10, 52, 99),
    "dark_blue_violet": (32, 50, 176),
    "medium_blue": (90, 147, 219),
    "sky_blue": (125, 193, 216),
    "light_blue": (180, 210, 227),
    "bright_light_blue": (159, 195, 233),
    "dark_azure": (7, 139, 201),
    "medium_azure": (54, 174, 191),
    "dark_turquoise": (0, 143, 155),
    "light_turquoise": (85, 165, 175),
    "aqua": (179, 215, 209),
    "light_aqua": (211, 242, 234),
    "sand_blue": (96, 116, 161),
    "purple": (129, 0, 123),
    "dark_purple": (63, 54, 145),
    "medium_lilac": (76, 47, 146),
    "medium_lavender": (160, 110, 185),
    "lavender": (225, 213, 237),
    "trans_dark_blue": (0, 32, 160),
    "trans_green": (132, 182, 141),
}

WARM_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    "red": (201, 26, 9),
    "dark_red": (114, 14, 15),
    "rust": (179, 16, 4),
    "salmon": (242, 112, 94),
    "coral": (255, 105, 143),
    "pink": (252, 151, 172),
    "medium_dark_pink": (247, 133, 177),
    "bright_pink": (228, 173, 200),
    "light_pink": (254, 204, 207),
    "dark_pink": (200, 112, 160),
    "light_purple": (205, 98, 152),
    "magenta": (146, 57, 120),
    "orange": (254, 138, 24),
    "medium_orange": (240, 143, 28),
    "dark_orange": (169, 85, 0),
    "light_orange": (249, 186, 97),
    "bright_light_orange": (248, 187, 61),
    "yellow": (242, 205, 55),
    "light_yellow": (251, 230, 150),
    "bright_light_yellow": (255, 240, 58),
    "cool_yellow": (255, 236, 108),
    "light_nougat": (246, 215, 179),
    "nougat": (208, 145, 104),
    "medium_nougat": (170, 125, 85),
    "medium_dark_flesh": (204, 112, 42),
    "trans_yellow": (245, 205, 42),
}

@dataclass(frozen=True)
class PaletteData:
    colors: dict[str, tuple[int, int, int]]
    rgb: np.ndarray
    lab: np.ndarray


def _build_palette(
    colors: dict[str, tuple[int, int, int]],
) -> PaletteData:
    rgb = np.asarray(
        list(colors.values()),
        dtype=np.uint8,
    )
    rgb.flags.writeable = False

    rgb_float = rgb.astype(np.float32)

    lab = rgb2lab((rgb_float / 255.0).reshape(1, -1, 3))[0].astype(np.float32)
    lab.flags.writeable = False

    return PaletteData(
        colors=colors,
        rgb=rgb,
        lab=lab,
    )


PALETTES: Final[dict[Palette, PaletteData]] = {
    Palette.CLASSIC: _build_palette(CLASSIC_PALETTE),
    Palette.EXTENDED: _build_palette(EXTENDED_PALETTE),
    Palette.MONOCHROME: _build_palette(MONOCHROME_PALETTE),
    Palette.PASTEL: _build_palette(PASTEL_PALETTE),
    Palette.CRAYON: _build_palette(CRAYON_PALETTE),
    Palette.EARTH: _build_palette(EARTH_PALETTE),
    Palette.COOL: _build_palette(COOL_PALETTE),
    Palette.WARM: _build_palette(WARM_PALETTE),
}


def get_palette(palette: Palette) -> PaletteData:
    try:
        return PALETTES[palette]
    except KeyError:
        val = getattr(palette, "value", str(palette))
        raise ValueError(f"Unsupported palette: {val}")
