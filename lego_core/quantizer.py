from functools import lru_cache
from typing import Final

import numpy as np
from skimage.color import rgb2lab

from config import Palette, Quality
from palette import get_palette

QUALITY_LUT_BITS: Final[dict[Quality, int]] = {
    Quality.STANDARD: 5,
    Quality.HIGH: 6,
}


def _build_color_lut(
    palette: Palette,
    bits: int,
) -> np.ndarray:
    levels = 1 << bits
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

    palette_lab = get_palette(palette).lab

    palette_squared = np.sum(
        palette_lab * palette_lab,
        axis=1,
    )

    lut_flat = np.empty(
        lab_samples.shape[0],
        dtype=np.uint8,
    )

    chunk_size = 65_536

    for start in range(0, len(lab_samples), chunk_size):
        end = min(
            start + chunk_size,
            len(lab_samples),
        )

        chunk = lab_samples[start:end]

        distances_squared = (
            np.sum(chunk * chunk, axis=1)[:, None]
            - 2.0 * (chunk @ palette_lab.T)
            + palette_squared[None, :]
        )

        lut_flat[start:end] = np.argmin(
            distances_squared,
            axis=1,
        ).astype(np.uint8)

    lut = lut_flat.reshape(
        levels,
        levels,
        levels,
    )
    lut.flags.writeable = False
    return lut


@lru_cache(maxsize=None)
def get_color_lut(
    palette: Palette,
    bits: int,
) -> np.ndarray:
    """Return a cached RGB-to-palette lookup table."""
    if bits < 1 or bits > 8:
        raise ValueError("LUT bits must be between 1 and 8.")

    return _build_color_lut(
        palette,
        bits,
    )


def prewarm_quantizer(
    palette: Palette,
    quality: Quality,
) -> None:
    """Precompute and cache lookup tables to prevent thread race conditions."""
    if quality != Quality.MAXIMUM:
        bits = QUALITY_LUT_BITS[quality]
        get_color_lut(palette, bits)


def _quantize_exact(
    rgb: np.ndarray,
    palette: Palette,
) -> np.ndarray:
    """Quantize RGB pixels using exact LAB distances."""
    height, width, _ = rgb.shape

    rgb_float = rgb.astype(np.float32) / 255.0

    lab = rgb2lab(rgb_float).astype(np.float32)

    pixels = lab.reshape(-1, 3)
    palette_lab = get_palette(palette).lab

    palette_squared = np.sum(
        palette_lab * palette_lab,
        axis=1,
    )

    result = np.empty(
        len(pixels),
        dtype=np.uint8,
    )

    chunk_size = 65_536

    for start in range(0, len(pixels), chunk_size):
        end = min(
            start + chunk_size,
            len(pixels),
        )

        chunk = pixels[start:end]

        distances_squared = (
            np.sum(chunk * chunk, axis=1)[:, None]
            - 2.0 * (chunk @ palette_lab.T)
            + palette_squared[None, :]
        )

        result[start:end] = np.argmin(
            distances_squared,
            axis=1,
        ).astype(np.uint8)

    return result.reshape(
        height,
        width,
    )


def quantize_rgb(
    rgb_image: np.ndarray,
    palette: Palette,
    quality: Quality = Quality.HIGH,
) -> np.ndarray:
    """Convert an HxWx3 RGB image to LEGO palette indices."""
    rgb = np.asarray(rgb_image)

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected an HxWx3 RGB array.")

    if rgb.dtype != np.uint8:
        rgb = np.clip(
            rgb,
            0,
            255,
        ).astype(np.uint8)

    if quality == Quality.MAXIMUM:
        return _quantize_exact(
            rgb,
            palette,
        )

    bits = QUALITY_LUT_BITS[quality]
    shift = 8 - bits

    quantized_rgb = rgb >> shift

    lut = get_color_lut(
        palette,
        bits,
    )

    return lut[
        quantized_rgb[..., 0],
        quantized_rgb[..., 1],
        quantized_rgb[..., 2],
    ]
