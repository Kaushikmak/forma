from __future__ import annotations

from functools import lru_cache
from typing import TypeAlias

import numpy as np
from PIL import Image, ImageDraw

from config import Palette
from palette import get_palette

RGBColor: TypeAlias = tuple[int, int, int]


def shade(color: RGBColor, amount: int) -> RGBColor:
    """Lighten or darken an RGB color."""
    return tuple(max(0, min(255, channel + amount)) for channel in color)


@lru_cache(maxsize=None)
def render_tile(
    color: RGBColor,
    tile_size: int = 32,
) -> Image.Image:
    """
    Render a LEGO-style tile with a raised stud.
    Uses 4x supersampling downscaled with Lanczos for smooth, anti-aliased studs.
    """
    if tile_size < 4:
        raise ValueError("tile_size must be at least 4 pixels.")

    scale = 4
    render_size = tile_size * scale
    tile = Image.new("RGB", (render_size, render_size), color)
    draw = ImageDraw.Draw(tile)

    border_width = max(1, 1 * scale)
    draw.rectangle(
        (scale, scale, render_size - 1 - scale, render_size - 1 - scale),
        outline=shade(color, -45),
        width=border_width,
    )

    stud_left = render_size * 0.22
    stud_top = render_size * 0.16
    stud_right = render_size * 0.78
    stud_bottom = render_size * 0.72

    draw.ellipse(
        (
            stud_left + 1 * scale,
            stud_top + 2 * scale,
            stud_right + 1 * scale,
            stud_bottom + 2 * scale,
        ),
        fill=shade(color, -55),
    )

    draw.ellipse(
        (stud_left, stud_top, stud_right, stud_bottom),
        fill=shade(color, 20),
        outline=shade(color, -35),
        width=border_width,
    )

    draw.arc(
        (
            stud_left + 2 * scale,
            stud_top + 2 * scale,
            stud_right - 2 * scale,
            stud_bottom - 2 * scale,
        ),
        start=195,
        end=285,
        fill=shade(color, 55),
        width=max(1, 2 * scale),
    )

    # Downsample to target tile_size with Lanczos for anti-aliased stud curves
    return tile.resize((tile_size, tile_size), resample=Image.Resampling.LANCZOS)


def _build_atlas(
    palette: Palette,
    tile_size: int = 32,
) -> np.ndarray:
    """Build a pre-rendered tile atlas (shape: [num_colors, tile_size, tile_size, 3])."""
    if tile_size < 4:
        raise ValueError("tile_size must be at least 4 pixels.")

    palette_data = get_palette(palette)
    palette_colors = palette_data.rgb

    if palette_colors.ndim != 2 or palette_colors.shape[1] != 3:
        raise ValueError("Palette colors must have shape (palette_size, 3).")

    if palette_colors.shape[0] == 0:
        raise ValueError("Palette must contain at least one color.")

    atlas = np.stack(
        [
            np.asarray(
                render_tile(
                    (int(color[0]), int(color[1]), int(color[2])),
                    tile_size,
                )
            )
            for color in palette_colors
        ],
        axis=0,
    )
    atlas.flags.writeable = False
    return atlas


@lru_cache(maxsize=None)
def get_atlas(
    palette: Palette,
    tile_size: int = 32,
) -> np.ndarray:
    return _build_atlas(
        palette=palette,
        tile_size=tile_size,
    )


def render_indices(
    indices: np.ndarray,
    atlas: np.ndarray,
) -> np.ndarray:
    """Render a palette-index grid using a pre-built tile atlas."""
    index_grid = np.asarray(indices)
    atlas = np.asarray(atlas)

    if index_grid.ndim != 2 or index_grid.size == 0:
        raise ValueError("indices must be a non-empty 2D array.")

    if atlas.ndim != 4 or atlas.shape[-1] != 3:
        raise ValueError(
            "atlas must have shape (palette_size, tile_size, tile_size, 3)."
        )

    if atlas.shape[1] != atlas.shape[2]:
        raise ValueError("atlas tiles must be square.")

    if not np.issubdtype(index_grid.dtype, np.integer):
        raise ValueError("indices must contain integer palette indices.")

    if index_grid.min() < 0 or index_grid.max() >= atlas.shape[0]:
        raise ValueError("indices contain an invalid palette index.")

    rows, cols = index_grid.shape
    tile_size = atlas.shape[1]

    selected_tiles = atlas[index_grid]

    mosaic = selected_tiles.transpose(0, 2, 1, 3, 4).reshape(
        rows * tile_size,
        cols * tile_size,
        3,
    )

    return np.ascontiguousarray(mosaic)


def render_mosaic(
    indices: np.ndarray,
    palette: Palette,
    tile_size: int = 32,
) -> Image.Image:
    """Render a palette-index grid using the cached tile atlas."""
    atlas = get_atlas(
        palette=palette,
        tile_size=tile_size,
    )

    mosaic_rgb = render_indices(indices, atlas)

    return Image.fromarray(mosaic_rgb)
