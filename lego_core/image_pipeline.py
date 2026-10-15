from pathlib import Path

import numpy as np
from PIL import Image

from config import MosaicConfig
from quantizer import quantize_rgb
from tile_renderer import render_indices


def image_to_mosaic(
    image: Image.Image,
    config: MosaicConfig,
    atlas: np.ndarray,
) -> Image.Image:
    """Convert a PIL image into a LEGO-style mosaic."""
    image = image.convert("RGB")
    original_width, original_height = image.size

    if original_width < 1 or original_height < 1:
        raise ValueError("Image must have non-zero dimensions.")

    atlas_array = np.asarray(atlas)
    if (
        atlas_array.ndim != 4
        or atlas_array.shape[1] != config.tile_size
        or atlas_array.shape[2] != config.tile_size
    ):
        raise ValueError("Atlas tile size must match config.tile_size.")

    grid_height = max(
        1,
        round(config.grid_width * original_height / original_width),
    )

    small_image = image.resize(
        (config.grid_width, grid_height),
        Image.Resampling.LANCZOS,
    )
    small_rgb = np.asarray(small_image, dtype=np.uint8)
    indices = quantize_rgb(small_rgb)
    mosaic_rgb = render_indices(indices, atlas_array)

    return Image.fromarray(mosaic_rgb)


def image_to_mosaic_file(
    input_path: str | Path,
    output_path: str | Path,
    config: MosaicConfig,
    atlas: np.ndarray,
) -> None:
    """Convert an image file into a LEGO mosaic file."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input image does not exist: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as image:
        mosaic = image_to_mosaic(image, config, atlas)

    mosaic.save(output_path)
