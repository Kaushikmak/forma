from PIL import Image
from rgbTOlab import ConvertColorSpace_rgbTOlab
from tile_renderer import render_grid

INPUT_PATH = "samples/imageSamples/sample1.png"
GRID_WIDTH = 64
TILE_SIZE = 32

image = Image.open(INPUT_PATH).convert("RGB")

original_width, original_height = image.size
grid_height = round(GRID_WIDTH * original_height / original_width)

small_image = image.resize(
    (GRID_WIDTH, grid_height),
    Image.Resampling.LANCZOS,
)

quantized_image = ConvertColorSpace_rgbTOlab(small_image)

# Convert the quantized pixels into an RGB color grid
color_grid = [
    [quantized_image.getpixel((x, y)) for x in range(GRID_WIDTH)]
    for y in range(grid_height)
]

legoImage = render_grid(color_grid, TILE_SIZE)

legoImage.save("output/lego_mosaic.png")
legoImage.show()

print(f"Grid: {GRID_WIDTH} x {grid_height} tiles")
print(f"Output: {legoImage.width} x {legoImage.height} pixels")
