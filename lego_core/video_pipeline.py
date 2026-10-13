import cv2
import numpy as np
from PIL import Image

from rgbTOlab import ConvertColorSpace_rgbTOlab
from tile_renderer import render_grid

INPUT_PATH = "samples/videoSamples/sample1.mp4"
OUTPUT_PATH = "output/lego_mosaic1_newpalete.mp4"

GRID_WIDTH = 64
TILE_SIZE = 32


def process_frame(frame: np.ndarray) -> np.ndarray:
    """Convert one video frame into a LEGO mosaic."""
    # OpenCV uses BGR; Pillow uses RGB
    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    original_width, original_height = image.size
    grid_height = max(
        1,
        round(GRID_WIDTH * original_height / original_width),
    )

    small_image = image.resize(
        (GRID_WIDTH, grid_height),
        Image.Resampling.LANCZOS,
    )

    quantized_image = ConvertColorSpace_rgbTOlab(small_image)

    pixels = np.asarray(quantized_image.convert("RGB"))

    color_grid = [[tuple(map(int, pixel)) for pixel in row] for row in pixels]

    lego_image = render_grid(color_grid, TILE_SIZE)

    # Convert RGB back to BGR for OpenCV's video writer
    return cv2.cvtColor(
        np.array(lego_image),
        cv2.COLOR_RGB2BGR,
    )


def main() -> None:
    capture = cv2.VideoCapture(INPUT_PATH)

    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {INPUT_PATH}")

    fps = capture.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        capture.release()
        raise RuntimeError("Could not determine video frame rate.")

    writer = None
    frame_count = 0

    try:
        while True:
            success, frame = capture.read()

            if not success:
                break

            lego_frame = process_frame(frame)

            # initialize output video using the first frame's dimensions
            if writer is None:
                height, width = lego_frame.shape[:2]

                writer = cv2.VideoWriter(
                    OUTPUT_PATH,
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    (width, height),
                )

                if not writer.isOpened():
                    raise RuntimeError(f"Could not create output video: {OUTPUT_PATH}")

            writer.write(lego_frame)
            frame_count += 1

            if frame_count % 30 == 0:
                print(f"Processed {frame_count} frames...")

    finally:
        capture.release()

        if writer is not None:
            writer.release()

    if frame_count == 0:
        raise RuntimeError("No frames were read from the input video.")

    print(f"Grid width: {GRID_WIDTH} tiles")
    print(f"Output resolution: {width} x {height} pixels")
    print(f"Frames processed: {frame_count}")
    print(f"Frame rate: {fps:.2f} FPS")
    print(f"Saved video: {OUTPUT_PATH}")


main()
