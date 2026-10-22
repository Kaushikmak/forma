from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_image,
    load_rgb,
    make_active,
)
from config import RAMPS, AsciiConfig
from cost_estimator import estimate_image_cost
from quantizer import quantize_ascii
from resource_limits import (
    ResourceLimitError,
    validate_input_size,
    validate_output_resolution,
    validate_output_size,
    validate_processing_units,
)
from tile_renderer import get_glyphs, render_ascii_tiles


def image_to_ascii(
    image: Image.Image,
    config: AsciiConfig,
) -> tuple[Image.Image, str | None]:
    """
    Convert a PIL Image into an ASCII mosaic Image.
    Returns:
        (mosaic_image, plain_text_ascii_or_none)
    """
    orig_w, orig_h = image.size
    if orig_w < 1 or orig_h < 1:
        raise ValueError("Image must have non-zero dimensions.")

    output_width, output_height = calculate_output_dimensions(
        config.grid_width, config.tile_size, orig_w, orig_h
    )
    validate_output_resolution(output_width, output_height, bypass=config.bypass_limits)

    estimate = estimate_image_cost(config, orig_w, orig_h)
    validate_processing_units(estimate.processing_units, bypass=config.bypass_limits)

    # Convert to RGBA for alpha channel awareness
    rgba_image = image.convert("RGBA")
    grid_w, grid_h = calculate_grid_dimensions(config.grid_width, orig_w, orig_h)
    if config.grid_height is not None:
        grid_h = config.grid_height

    small = downscale_image(rgba_image, (grid_w, grid_h))
    rgb_img = small.convert("RGB")
    alpha = np.asarray(small.getchannel("A"), dtype=np.float32) / 255.0

    # Color enhancements
    if config.contrast != 1.0:
        from PIL import ImageEnhance

        rgb_img = ImageEnhance.Contrast(rgb_img).enhance(config.contrast)
    if config.saturation != 1.0:
        from PIL import ImageEnhance

        rgb_img = ImageEnhance.Color(rgb_img).enhance(config.saturation)

    rgb = np.asarray(rgb_img, dtype=np.float32)
    if config.gamma != 1.0:
        rgb = 255.0 * (rgb / 255.0) ** (1.0 / config.gamma)

    ramp_str = RAMPS.get(config.ramp, config.ramp)
    _, idx, _ = quantize_ascii(
        rgb,
        len(ramp_str),
        invert=config.invert,
        auto_levels=config.auto_levels,
        quality=config.quality,
    )
    active = make_active(alpha, rgb, config.skip_white)

    gap = 1 if config.gap is None else config.gap
    glyphs = get_glyphs(ramp_str, config.tile_size, gap, config.font_scale)
    mosaic_arr = render_ascii_tiles(
        rgb=rgb,
        idx=idx,
        active=active,
        glyphs=glyphs,
        config=config,
        even=False,
    )
    mosaic_img = Image.fromarray(mosaic_arr)

    txt_content = None
    if config.write_txt:
        ramp_arr = np.array(list(ramp_str))
        chars = ramp_arr[idx]
        lines = [
            "".join(chars[y, x] if active[y, x] else " " for x in range(chars.shape[1]))
            for y in range(chars.shape[0])
        ]
        txt_content = "\n".join(lines) + "\n"

    return mosaic_img, txt_content


# Lego-core API alias
def image_to_mosaic(
    image: Image.Image,
    config: AsciiConfig,
) -> Image.Image:
    mosaic_img, _ = image_to_ascii(image, config)
    return mosaic_img


def image_to_ascii_file(
    input_path: str | Path,
    output_path: str | Path,
    config: AsciiConfig,
) -> None:
    """Convert an image file to an ASCII mosaic image file and optional .txt file."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input image does not exist: {input_path}")

    validate_input_size(input_path.stat().st_size, bypass=config.bypass_limits)

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as image:
        mosaic_img, txt_content = image_to_ascii(image, config)

    save_kwargs = {}
    if output_path.suffix.lower() in (".jpg", ".jpeg"):
        save_kwargs["quality"] = 95
        save_kwargs["subsampling"] = 0

    mosaic_img.save(output_path, **save_kwargs)

    if txt_content is not None:
        txt_path = output_path.with_suffix(".txt")
        txt_path.write_text(txt_content, encoding="utf-8")

    try:
        validate_output_size(output_path.stat().st_size, bypass=config.bypass_limits)
    except ResourceLimitError:
        output_path.unlink(missing_ok=True)
        if txt_content is not None:
            output_path.with_suffix(".txt").unlink(missing_ok=True)
        raise
