from functools import lru_cache
from typing import TypeAlias
import numpy as np
from PIL import Image, ImageDraw

RGBColor: TypeAlias = tuple[int, int, int]
ColorGrid: TypeAlias = list[list[RGBColor]]


def shade(color: RGBColor, amount: int) -> RGBColor:
    """Lighten or darken an RGB color by a fixed amount"""
    return tuple(max(0, min(255, channel + amount)) for channel in color)


@lru_cache(maxsize=None)
def render_tile(color: RGBColor, tile_size: int = 32) -> Image.Image:
    """Render a single LEGO-style tile with a raised stud.
    Treat the returned cached image as read-only; callers should not modify it
    """
    if tile_size < 4:
        raise ValueError("tile_size must be at least 4 pixels.")

    tile = Image.new("RGB", (tile_size, tile_size), color)
    draw = ImageDraw.Draw(tile)

    draw.rectangle(
        (1, 1, tile_size - 2, tile_size - 2),
        outline=shade(color, -45),
        width=1,
    )

    stud_left = tile_size * 0.22
    stud_top = tile_size * 0.16
    stud_right = tile_size * 0.78
    stud_bottom = tile_size * 0.72

    draw.ellipse(
        (stud_left + 1, stud_top + 2, stud_right + 1, stud_bottom + 2),
        fill=shade(color, -55),
    )
    draw.ellipse(
        (stud_left, stud_top, stud_right, stud_bottom),
        fill=shade(color, 20),
        outline=shade(color, -35),
        width=1,
    )
    draw.arc(
        (stud_left + 2, stud_top + 2, stud_right - 2, stud_bottom - 2),
        start=195,
        end=285,
        fill=shade(color, 55),
        width=2,
    )
    return tile


def build_atlas(tile_size: int = 32, colors: np.ndarray | None = None) -> np.ndarray:
    """Build an (palette, tile_height, tile_width, RGB) uint8 tile atlas

    If colors is omitted, the LEGO palette is imported lazily from rgbTOlab.
    Atlas index order must match the palette-index order used by quantize_rgb()
    """
    if colors is None:
        from rgbTOlab import _PALETTE_RGB_UINT8

        colors = _PALETTE_RGB_UINT8

    palette_colors = np.asarray(colors, dtype=np.uint8)
    if palette_colors.ndim != 2 or palette_colors.shape[1] != 3:
        raise ValueError("colors must have shape (palette_size, 3).")

    return np.stack(
        [
            np.asarray(render_tile(tuple(int(c) for c in color), tile_size))
            for color in palette_colors
        ],
        axis=0,
    )


def render_indices(indices: np.ndarray, atlas: np.ndarray) -> np.ndarray:
    """Expand a 2D palette-index grid into RGB mosaic array"""
    index_grid = np.asarray(indices)
    if index_grid.ndim != 2 or index_grid.size == 0:
        raise ValueError("indices must be a non-empty 2D array.")
    if atlas.ndim != 4 or atlas.shape[-1] != 3 or atlas.shape[1] != atlas.shape[2]:
        raise ValueError(
            "atlas must have shape (palette_size, tile_size, tile_size, 3)."
        )
    if not np.issubdtype(index_grid.dtype, np.integer):
        raise ValueError("indices must contain integer palette indices.")
    if index_grid.min() < 0 or index_grid.max() >= atlas.shape[0]:
        raise ValueError("indices contain a value outside the atlas palette.")

    rows, cols = index_grid.shape
    tile_size = atlas.shape[1]
    # positions and tile pixels into the final mosaic layout
    selected_tiles = atlas[index_grid]
    mosaic = selected_tiles.transpose(0, 2, 1, 3, 4).reshape(
        rows * tile_size, cols * tile_size, 3
    )
    return np.ascontiguousarray(mosaic)


def render_grid(color_grid: ColorGrid, tile_size: int = 32) -> Image.Image:
    """Compatibility helper: render an arbitrary RGB color grid as a mosaic"""
    if not color_grid or not color_grid[0]:
        raise ValueError("Color grid must not be empty.")
    cols = len(color_grid[0])
    if any(len(row) != cols for row in color_grid):
        raise ValueError("All rows in the color grid must have equal length.")

    rows = len(color_grid)
    mosaic = np.empty((rows * tile_size, cols * tile_size, 3), dtype=np.uint8)
    for row_index, row in enumerate(color_grid):
        y = row_index * tile_size
        for col_index, color in enumerate(row):
            x = col_index * tile_size
            tile = np.asarray(render_tile(tuple(int(c) for c in color), tile_size))
            mosaic[y : y + tile_size, x : x + tile_size] = tile
    return Image.fromarray(mosaic)
