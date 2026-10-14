from pathlib import Path
import numpy as np
from PIL import Image
from rgbTOlab import quantize_rgb
from tile_renderer import build_atlas, render_indices

INPUT_PATH = Path("samples/imageSamples/sample2.jpeg")
OUTPUT_PATH = Path("output/lego_mosaic1.png")
GRID_WIDTH = 64
TILE_SIZE = 16


def image_to_mosaic(
    image: Image.Image,
    grid_width: int = GRID_WIDTH,
    tile_size: int = TILE_SIZE,
) -> Image.Image:
    """Convert a PIL image into a LEGO-style mosaic image"""
    if grid_width < 1:
        raise ValueError("grid_width must be positive")
    image = image.convert("RGB")
    original_width, original_height = image.size
    grid_height = max(1, round(grid_width * original_height / original_width))

    small_image = image.resize(
        (grid_width, grid_height),
        Image.Resampling.LANCZOS,
    )
    small_rgb = np.asarray(small_image, dtype=np.uint8)
    indices = quantize_rgb(small_rgb)
    atlas = build_atlas(tile_size)
    mosaic_rgb = render_indices(indices, atlas)
    return Image.fromarray(mosaic_rgb)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(INPUT_PATH) as source:
        original_size = source.size
        mosaic = image_to_mosaic(source)

    mosaic.save(OUTPUT_PATH)
    print(f"Input resolution: {original_size[0]} x {original_size[1]} pixels")
    print(f"Grid width: {GRID_WIDTH} tiles")
    print(f"Output resolution: {mosaic.width} x {mosaic.height} pixels")
    print(f"Saved image: {OUTPUT_PATH}")


main()
