from functools import lru_cache
from typing import Final

import numpy as np
from skimage.color import rgb2lab

from config import Palette
from palette import get_palette

LUT_BITS: Final[int] = 6

_LUT_LEVELS: Final[int] = 1 << LUT_BITS
_LUT_SHIFT: Final[int] = 8 - LUT_BITS


def _build_color_lut(palette: Palette) -> np.ndarray:
    levels = _LUT_LEVELS
    step = 256.0 / levels

    axis = (np.arange(levels, dtype=np.float32) * step + step / 2.0) / 255.0

    red, green, blue = np.meshgrid(
        axis,
        axis,
        axis,
        indexing="ij",
    )

    rgb_samples = np.stack(
        (red, green, blue),
        axis=-1,
    ).reshape(-1, 3)

    lab_samples = rgb2lab(rgb_samples.reshape(1, -1, 3))[0].astype(np.float32)

    palette_data = get_palette(palette)
    palette_lab = palette_data.lab

    # Precompute palette squared norms for the distance calculation.
    palette_squared = np.sum(
        palette_lab * palette_lab,
        axis=1,
    )

    lut_flat = np.empty(
        lab_samples.shape[0],
        dtype=np.uint8,
    )

    # Chunk distance calculations to limit peak memory usage.
    chunk_size = 65_536

    for start in range(0, len(lab_samples), chunk_size):
        end = min(start + chunk_size, len(lab_samples))
        chunk = lab_samples[start:end]

        # Squared CIE76 distance; avoids unnecessary square roots.
        distances_squared = (
            np.sum(chunk * chunk, axis=1)[:, None]
            - 2.0 * (chunk @ palette_lab.T)
            + palette_squared[None, :]
        )

        lut_flat[start:end] = np.argmin(
            distances_squared,
            axis=1,
        ).astype(np.uint8)

    return lut_flat.reshape(
        levels,
        levels,
        levels,
    )


@lru_cache(maxsize=1)
def get_color_lut(palette: Palette) -> np.ndarray:
    """Return the cached RGB-to-palette lookup table."""
    return _build_color_lut(palette)


def quantize_rgb(rgb_image: np.ndarray, palette: Palette) -> np.ndarray:
    """Convert an HxWx3 RGB image to LEGO palette indices."""
    rgb = np.asarray(rgb_image)

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected an HxWx3 RGB array.")

    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    quantized_rgb = rgb >> _LUT_SHIFT

    lut = get_color_lut(palette)

    return lut[
        quantized_rgb[..., 0],
        quantized_rgb[..., 1],
        quantized_rgb[..., 2],
    ]
