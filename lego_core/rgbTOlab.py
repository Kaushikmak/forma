from functools import lru_cache
from typing import Final
import numpy as np
from PIL import Image
from skimage.color import rgb2lab

LEGO_PALETTE: Final[dict[str, tuple[int, int, int]]] = {
    # Neutrals
    "white": (255, 255, 255),
    "black": (5, 19, 29),
    # Grays
    "very_light_gray": (230, 227, 218),
    "very_light_bluish_gray": (230, 227, 224),
    "light_gray": (155, 161, 157),
    "light_bluish_gray": (160, 165, 169),
    "dark_gray": (109, 110, 92),
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
    # Transparent (blend with the background, so treat with care in mosaics)
    "trans_clear": (252, 252, 252),
    "trans_red": (201, 26, 9),
    "trans_orange": (240, 143, 28),
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


_PALETTE_RGB_UINT8: Final[np.ndarray] = np.asarray(
    list(LEGO_PALETTE.values()), dtype=np.uint8
)
_PALETTE_RGB_FLOAT: Final[np.ndarray] = _PALETTE_RGB_UINT8.astype(np.float32)
_PALETTE_LAB: Final[np.ndarray] = rgb2lab(
    (_PALETTE_RGB_FLOAT / 255.0).reshape(1, -1, 3)
)[0].astype(np.float32)

LUT_BITS: Final[int] = 6
_LUT_LEVELS: Final[int] = 1 << LUT_BITS
_LUT_SHIFT: Final[int] = 8 - LUT_BITS


def _build_color_lut() -> np.ndarray:
    """Build a 3D lookup table mapping quantized RGB bins to palette indices"""
    levels = _LUT_LEVELS
    step = 256.0 / levels
    # Use each RGB bin's center as its representative color
    axis = (np.arange(levels, dtype=np.float32) * step + step / 2.0) / 255.0
    red, green, blue = np.meshgrid(axis, axis, axis, indexing="ij")
    rgb_samples = np.stack((red, green, blue), axis=-1).reshape(-1, 3)
    lab_samples = rgb2lab(rgb_samples.reshape(1, -1, 3))[0].astype(np.float32)

    palette_lab = _PALETTE_LAB
    palette_squared = np.sum(palette_lab * palette_lab, axis=1)
    lut_flat = np.empty(lab_samples.shape[0], dtype=np.uint8)

    # Chunk the distance calculation to keep peak memory bounded
    chunk_size = 65_536
    for start in range(0, len(lab_samples), chunk_size):
        end = min(start + chunk_size, len(lab_samples))
        chunk = lab_samples[start:end]
        distances_squared = (
            np.sum(chunk * chunk, axis=1)[:, None]
            - 2.0 * (chunk @ palette_lab.T)
            + palette_squared[None, :]
        )
        lut_flat[start:end] = np.argmin(distances_squared, axis=1).astype(np.uint8)

    return lut_flat.reshape(levels, levels, levels)


@lru_cache(maxsize=1)
def get_color_lut() -> np.ndarray:
    """Return the shared lookup table, building it on first use"""
    return _build_color_lut()


def quantize_rgb(rgb_image: np.ndarray) -> np.ndarray:
    """Return palette indices for an HxWx3 uint8 RGB image using the LUT

    The six-bit lookup is an approximation of exact CIELAB matching: RGB values
    within each four-value channel bin share the same palette match
    """
    rgb = np.asarray(rgb_image)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected an HxWx3 RGB array")
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    quantized_rgb = rgb >> _LUT_SHIFT
    lut = get_color_lut()
    return lut[quantized_rgb[..., 0], quantized_rgb[..., 1], quantized_rgb[..., 2]]


def ConvertColorSpace_rgbTOlab(image: Image.Image) -> Image.Image:
    """Map an image to the closest LEGO palette RGB colors using the LUT"""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    indices = quantize_rgb(rgb)
    return Image.fromarray(_PALETTE_RGB_UINT8[indices])
