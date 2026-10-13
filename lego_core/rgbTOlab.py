from typing import Final
import numpy as np
from PIL import Image
from skimage.color import rgb2lab
from typing import Final

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

def ConvertColorSpace_rgbTOlab(image: Image.Image) -> Image.Image:
    # normalize original image to rgb
    image = image.convert("RGB")

    # Convert image pixels to NumPy array and normalize RGB to [0, 1]
    pixels_rgb = np.asarray(image, dtype=np.float32) / 255.0

    # Convert every image pixel from RGB to CIELAB
    pixels_lab = rgb2lab(pixels_rgb)

    # Prepare the LEGO palette
    palette_rgb = (
        np.array(
            list(LEGO_PALETTE.values()),
            dtype=np.float32,
        )
        / 255.0
    )

    palette_lab = rgb2lab(palette_rgb.reshape(1, -1, 3))[0]

    # Calculate CIE76 distances from each pixel to each palette color
    distances = np.linalg.norm(
        pixels_lab[:, :, None, :] - palette_lab[None, None, :, :],
        axis=3,
    )

    # Find the closest palette color for each pixel
    closest_indices = np.argmin(distances, axis=2)

    # Replace each pixel with its matched LEGO RGB color
    palette_rgb_255 = np.array(list(LEGO_PALETTE.values()), dtype=np.uint8)
    output_pixels = palette_rgb_255[closest_indices]

    return Image.fromarray(output_pixels, mode="RGB")
