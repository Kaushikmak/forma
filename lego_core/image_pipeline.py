from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_image,
    load_rgb,
)
from config import MosaicConfig
from cost_estimator import estimate_image_cost
from quantizer import quantize_rgb
from resource_limits import (
    ResourceLimitError,
    validate_input_size,
    validate_output_resolution,
    validate_output_size,
    validate_processing_units,
)
from tile_renderer import get_atlas, render_indices


def image_to_mosaic(
    image: Image.Image,
    config: MosaicConfig,
) -> Image.Image:
    """
    Convert a PIL image into a LEGO-style mosaic.
    Normalizes transparency (composited onto white) and handles EXIF orientation.
    Only the first frame of multi-frame images (e.g. multi-page TIFF) is processed.
    """
    rgb_image = load_rgb(image)
    orig_w, orig_h = rgb_image.size
    if orig_w < 1 or orig_h < 1:
        raise ValueError("Image must have non-zero dimensions.")

    output_width, output_height = calculate_output_dimensions(
        config.grid_width, config.tile_size, orig_w, orig_h
    )
    validate_output_resolution(output_width, output_height, bypass=config.bypass_limits)

    estimate = estimate_image_cost(config, orig_w, orig_h)
    validate_processing_units(estimate.processing_units, bypass=config.bypass_limits)

    _, grid_height = calculate_grid_dimensions(config.grid_width, orig_w, orig_h)
    small_image = downscale_image(rgb_image, (config.grid_width, grid_height))
    small_rgb = np.asarray(small_image, dtype=np.uint8)

    indices = quantize_rgb(
        small_rgb,
        config.palette,
        config.quality,
    )

    atlas = get_atlas(
        config.palette,
        config.tile_size,
    )
    mosaic_rgb = render_indices(indices, atlas)
    return Image.fromarray(mosaic_rgb)


def image_to_mosaic_file(
    input_path: str | Path,
    output_path: str | Path,
    config: MosaicConfig,
) -> None:
    """Convert an image file into a LEGO mosaic file."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input image does not exist: {input_path}")

    validate_input_size(input_path.stat().st_size, bypass=config.bypass_limits)

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as image:
        mosaic = image_to_mosaic(image, config)

    save_kwargs = {}
    if output_path.suffix.lower() in (".jpg", ".jpeg"):
        save_kwargs["quality"] = 95
        save_kwargs["subsampling"] = 0

    mosaic.save(output_path, **save_kwargs)

    try:
        validate_output_size(output_path.stat().st_size, bypass=config.bypass_limits)
    except ResourceLimitError:
        output_path.unlink(missing_ok=True)
        raise
