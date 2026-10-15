from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

from config import MosaicConfig
from image_pipeline import image_to_mosaic


def gif_to_mosaic_file(
    input_path: str | Path,
    output_path: str | Path,
    config: MosaicConfig,
    atlas: np.ndarray,
) -> None:
    """Convert an animated GIF into a LEGO-style animated GIF."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input GIF does not exist: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")
    if input_path.suffix.lower() != ".gif":
        raise ValueError("Input file must have a .gif extension.")
    if output_path.suffix.lower() != ".gif":
        raise ValueError("Output file must have a .gif extension.")

    frames: list[Image.Image] = []
    durations: list[int] = []

    with Image.open(input_path) as source:
        if source.format != "GIF":
            raise ValueError(f"Input file is not a valid GIF: {input_path}")

        loop = source.info.get("loop")
        default_duration = source.info.get("duration", 100)

        for frame in ImageSequence.Iterator(source):
            duration = frame.info.get("duration", default_duration)
            durations.append(
                max(0, int(default_duration if duration is None else duration))
            )

            rgba = frame.copy().convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            rgb_frame = Image.alpha_composite(background, rgba).convert("RGB")
            mosaic = image_to_mosaic(rgb_frame, config, atlas)
            frames.append(mosaic.quantize(colors=256))

    if not frames:
        raise ValueError(f"GIF contains no frames: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    save_options = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations,
        "disposal": 2,
        "optimize": False,
    }
    if loop is not None:
        save_options["loop"] = loop

    frames[0].save(output_path, **save_options)
