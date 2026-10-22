from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

if TYPE_CHECKING:
    from config import FPS

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv", ".flv"}


def is_video(path: str | Path) -> bool:
    """Return whether a path points to a supported video container."""
    return Path(path).suffix.lower() in VIDEO_EXTS


def load_rgb(image: Image.Image) -> Image.Image:
    """Normalize a PIL Image to RGB: apply EXIF orientation and composite transparency on white."""
    transposed = ImageOps.exif_transpose(image)
    if transposed is not None:
        image = transposed

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")

    return image.convert("RGB")


def calculate_grid_dimensions(
    grid_width: int,
    source_width: int,
    source_height: int,
) -> tuple[int, int]:
    """Calculate the mosaic grid (width, height) preserving aspect ratio."""
    if grid_width < 1:
        raise ValueError("grid_width must be positive.")
    if source_width < 1 or source_height < 1:
        raise ValueError("source dimensions must be positive.")

    grid_height = max(
        1,
        round(grid_width * source_height / source_width),
    )
    return grid_width, grid_height


def calculate_output_dimensions(
    grid_width: int,
    tile_size: int,
    source_width: int,
    source_height: int,
) -> tuple[int, int]:
    """Calculate output pixel dimensions (output_width, output_height)."""
    if tile_size < 1:
        raise ValueError("tile_size must be positive.")

    _, grid_height = calculate_grid_dimensions(grid_width, source_width, source_height)
    return grid_width * tile_size, grid_height * tile_size


def resolve_output_fps(
    config_fps: FPS | str,
    source_fps: float,
) -> float:
    """Resolve target output FPS from configuration and source frame rate."""
    if source_fps <= 0:
        raise ValueError("source_fps must be positive.")

    val = config_fps.value if hasattr(config_fps, "value") else str(config_fps)
    if val == "original":
        return float(source_fps)

    return float(val)


def downscale_image(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Downscale a PIL Image using box (area) averaging to avoid high-frequency ringing."""
    return image.resize(target_size, resample=Image.Resampling.BOX)


def downscale_frame(frame_bgr: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
    """Downscale an OpenCV BGR frame using INTER_AREA interpolation."""
    import cv2

    return cv2.resize(frame_bgr, target_size, interpolation=cv2.INTER_AREA)


def normalize_gif_delay(delay_ms: int | float | None) -> int:
    """
    Normalize GIF frame delay in milliseconds.
    Delays of 10 ms or less (or missing) are treated as 100 ms by web browsers.
    """
    if delay_ms is None:
        return 100
    delay_int = int(round(delay_ms))
    return 100 if delay_int <= 10 else delay_int


def grid_from_pil(
    img: Image.Image,
    width: int,
    height: int | None = None,
    contrast: float = 1.15,
    saturation: float = 1.15,
    gamma: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Resize a PIL image to (width x height) tiles.
    Returns:
        rgb: (h, w, 3) float32
        alpha: (h, w) float32
    """
    img = img.convert("RGBA")

    # tiles are square, so no aspect-ratio correction is needed
    if height is None:
        height = max(1, round(img.height * width / img.width))

    # BOX = true average color of each tile's region (best for mosaics)
    small = img.resize((width, height), Image.Resampling.BOX)
    rgb_img = small.convert("RGB")
    alpha = np.asarray(small.getchannel("A"), dtype=np.float32) / 255.0

    if contrast != 1.0:
        rgb_img = ImageEnhance.Contrast(rgb_img).enhance(contrast)
    if saturation != 1.0:
        rgb_img = ImageEnhance.Color(rgb_img).enhance(saturation)

    rgb = np.asarray(rgb_img, dtype=np.float32)
    if gamma != 1.0:
        rgb = 255.0 * (rgb / 255.0) ** (1.0 / gamma)
    return rgb, alpha


def load_grid(
    path: str | Path,
    width: int,
    height: int | None = None,
    contrast: float = 1.15,
    saturation: float = 1.15,
    gamma: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Load an image file and compute resized color grid and alpha."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return grid_from_pil(img, width, height, contrast, saturation, gamma)


def make_active(alpha: np.ndarray, rgb: np.ndarray, skip_white: int = 0) -> np.ndarray:
    """Compute boolean mask of active cells (excluding transparent and optional near-white cells)."""
    active = alpha > 0.5
    if skip_white > 0:
        active &= ~(rgb.min(axis=2) >= (255 - skip_white))
    return active
