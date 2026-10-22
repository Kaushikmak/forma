"""
ascii_core: High-performance ASCII tile mosaic conversion package for Forma.
Supports images, animated GIFs, and videos with customizable palettes and character ramps.
"""

from __future__ import annotations

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_frame,
    downscale_image,
    grid_from_pil,
    is_video,
    load_grid,
    load_rgb,
    make_active,
)
from config import (
    PAPER,
    RAMPS,
    FPS,
    AsciiConfig,
    Palette,
    Quality,
)
from cost_estimator import (
    CostEstimate,
    estimate_gif_cost,
    estimate_image_cost,
    estimate_video_cost,
    select_bitrate_bps,
)
from gif_pipeline import gif_to_ascii_file
from image_pipeline import image_to_ascii, image_to_ascii_file
from main import convert, convert_image, convert_video
from palette import AsciiPaletteData, get_palette, list_palettes
from quantizer import (
    compute_levels,
    luminance,
    pick_indices,
    quantize_ascii,
    sample_video_levels,
)
from resource_limits import (
    ResourceLimitError,
    is_resource_limits_bypassed,
    set_bypass_resource_limits,
)
from tile_renderer import (
    FONT_PATHS,
    build_glyphs,
    get_glyphs,
    load_font,
    render,
    render_ascii_tiles,
)
from video_pipeline import video_to_ascii_file

__all__ = [
    "AsciiConfig",
    "Palette",
    "Quality",
    "FPS",
    "PAPER",
    "RAMPS",
    "FONT_PATHS",
    "AsciiPaletteData",
    "CostEstimate",
    "ResourceLimitError",
    "load_font",
    "build_glyphs",
    "get_glyphs",
    "render",
    "render_ascii_tiles",
    "luminance",
    "compute_levels",
    "pick_indices",
    "quantize_ascii",
    "sample_video_levels",
    "load_rgb",
    "grid_from_pil",
    "load_grid",
    "make_active",
    "calculate_grid_dimensions",
    "calculate_output_dimensions",
    "downscale_image",
    "downscale_frame",
    "is_video",
    "get_palette",
    "list_palettes",
    "estimate_image_cost",
    "estimate_gif_cost",
    "estimate_video_cost",
    "select_bitrate_bps",
    "image_to_ascii",
    "image_to_ascii_file",
    "gif_to_ascii_file",
    "video_to_ascii_file",
    "convert",
    "convert_image",
    "convert_video",
    "set_bypass_resource_limits",
    "is_resource_limits_bypassed",
]
