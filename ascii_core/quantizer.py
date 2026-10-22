from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from common import grid_from_pil
from config import Quality


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Compute perceptual luminance (0..255) from RGB image array."""
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return np.clip(rgb @ weights, 0, 255)


def compute_levels(lum: np.ndarray) -> tuple[float, float]:
    """Compute 2nd and 98th percentile brightness bounds to avoid outliers."""
    lo, hi = np.percentile(lum, [2, 98])
    return float(lo), float(hi)


def pick_indices(
    lum: np.ndarray,
    n_ramp: int,
    invert: bool = False,
    levels: tuple[float, float] | None = None,
) -> np.ndarray:
    """
    Map brightness to ramp indices (ramp is dense -> sparse).
    Dark -> dense (low index), light -> sparse (high index); invert flips it.
    levels = (lo, hi) to stretch with fixed levels, or None for plain 0..255.
    """
    if levels is not None:
        lo, hi = levels
        norm_lum = np.clip((lum - lo) / (hi - lo + 1e-6), 0.0, 1.0)
    else:
        norm_lum = np.clip(lum / 255.0, 0.0, 1.0)

    t = (1.0 - norm_lum) if invert else norm_lum
    indices = (t * (n_ramp - 1)).round().astype(int)
    return np.clip(indices, 0, n_ramp - 1)


def sample_video_levels(
    cv2: Any,
    cap: Any,
    start_frame: int,
    end_frame: int,
    width: int,
    height: int,
    contrast: float = 1.15,
    saturation: float = 1.15,
    gamma: float = 1.0,
    samples: int = 24,
) -> tuple[float, float] | None:
    """Measure brightness levels once from evenly spaced frames to avoid flicker."""
    total = max(1, end_frame - start_frame)
    positions = np.unique(
        np.linspace(start_frame, start_frame + total - 1, samples).astype(int)
    )
    lums = []
    for pos in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        # BGR -> PIL
        pil_frame = Image.fromarray(frame[:, :, ::-1])
        rgb, _ = grid_from_pil(pil_frame, width, height, contrast, saturation, gamma)
        lums.append(luminance(rgb).ravel())

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    if not lums:
        return None

    return compute_levels(np.concatenate(lums))


def quantize_ascii(
    rgb: np.ndarray,
    ramp_len: int,
    invert: bool = False,
    auto_levels: bool = True,
    levels: tuple[float, float] | None = None,
    quality: Quality = Quality.HIGH,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float] | None]:
    """
    Map RGB array to ASCII ramp indices and return (lum, idx, computed_levels).
    """
    lum = luminance(rgb)
    if levels is None and auto_levels and quality != Quality.STANDARD:
        levels = compute_levels(lum)

    idx = pick_indices(lum, ramp_len, invert=invert, levels=levels)
    return lum, idx, levels
