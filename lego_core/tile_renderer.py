from typing import TypeAlias
from functools import lru_cache
from PIL import Image, ImageDraw

RGBColor: TypeAlias = tuple[int, int, int]
ColorGrid: TypeAlias = list[list[RGBColor]]


def shade(color: RGBColor, amount: int) -> RGBColor:
    """Lighten or darken an RGB color by a fixed amount"""
    return tuple(max(0, min(255, channel + amount)) for channel in color)


@lru_cache(maxsize=None)
def render_tile(
    color: RGBColor,
    tile_size: int = 32,
) -> Image.Image:
    """Render a single LEGO-style tile with a raised stud"""
    tile = Image.new("RGB", (tile_size, tile_size), color)
    draw = ImageDraw.Draw(tile)

    # Tile border
    draw.rectangle(
        (1, 1, tile_size - 2, tile_size - 2),
        outline=shade(color, -45),
        width=1,
    )

    # Stud dimensions
    stud_left = tile_size * 0.22
    stud_top = tile_size * 0.16
    stud_right = tile_size * 0.78
    stud_bottom = tile_size * 0.72

    # Stud shadow
    draw.ellipse(
        (
            stud_left + 1,
            stud_top + 2,
            stud_right + 1,
            stud_bottom + 2,
        ),
        fill=shade(color, -55),
    )

    # Raised stud
    draw.ellipse(
        (stud_left, stud_top, stud_right, stud_bottom),
        fill=shade(color, 20),
        outline=shade(color, -35),
        width=1,
    )

    # Stud highlight
    draw.arc(
        (
            stud_left + 2,
            stud_top + 2,
            stud_right - 2,
            stud_bottom - 2,
        ),
        start=195,
        end=285,
        fill=shade(color, 55),
        width=2,
    )

    return tile


def render_grid(
    color_grid: ColorGrid,
    tile_size: int = 32,
) -> Image.Image:
    """Render a grid of RGB colors as a LEGO-style mosaic"""
    if not color_grid or not color_grid[0]:
        raise ValueError("Color grid must not be empty.")

    cols = len(color_grid[0])

    if any(len(row) != cols for row in color_grid):
        raise ValueError("All rows in the color grid must have equal length")

    rows = len(color_grid)

    mosaic = Image.new(
        "RGB",
        (cols * tile_size, rows * tile_size),
        "white",
    )

    for row_index, row in enumerate(color_grid):
        for col_index, color in enumerate(row):
            tile = render_tile(color, tile_size)

            mosaic.paste(
                tile,
                (col_index * tile_size, row_index * tile_size),
            )

    return mosaic
