from __future__ import annotations

import math
from dataclasses import dataclass

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    resolve_output_fps,
)
from config import FPS, MosaicConfig, Quality
from resource_limits import (
    MAX_OUTPUT_SIZE_BYTES,
    MAX_VIDEO_BITRATE_BPS,
    MIN_VIDEO_BITRATE_BPS,
    ResourceLimitError,
    is_resource_limits_bypassed,
    validate_bitrate,
)


@dataclass(frozen=True)
class CostEstimate:
    """Estimated resource usage and credit cost for a media-processing job."""

    output_width: int
    output_height: int
    output_fps: float
    frame_count: int
    processed_frames: int
    duration_seconds: float
    estimated_bitrate_bps: int
    estimated_size_bytes: int
    estimated_size_mb: float
    raw_rgb_bytes: int
    processing_units: int
    estimated_credits: int


# ---------------------------------------------------------------------------
# Video bitrate estimation & selection
# ---------------------------------------------------------------------------

QUALITY_BITRATE_MULTIPLIER = {
    Quality.STANDARD: 0.65,
    Quality.HIGH: 1.0,
    Quality.MAXIMUM: 1.35,
}

BASE_BITS_PER_PIXEL = 0.08
CREDIT_TILE_UNIT = 10_000


def _estimate_bitrate(
    width: int,
    height: int,
    fps: float,
    quality: Quality,
) -> int:
    """Estimate encoded video bitrate in bits per second."""
    if width < 1 or height < 1:
        raise ValueError("width and height must be positive.")
    if fps <= 0:
        raise ValueError("fps must be positive.")

    pixels_per_second = (width * height) * fps
    multiplier = QUALITY_BITRATE_MULTIPLIER[quality]
    bitrate = pixels_per_second * BASE_BITS_PER_PIXEL * multiplier
    return max(1, int(round(bitrate)))


def select_bitrate_bps(
    width: int,
    height: int,
    fps: float,
    quality: Quality,
    duration_seconds: float,
    configured_mbps: float | None = None,
    bypass_limits: bool | None = None,
) -> int:
    """
    Select the video bitrate in bits per second.

    - If configured_mbps is provided by the user, validate it (never clamp).
    - If auto-selected, clamp into [MIN_VIDEO_BITRATE_BPS, MAX_VIDEO_BITRATE_BPS]
      and cap by the 50 MiB output size limit (leaving 10% margin for container overhead).
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive.")

    should_bypass = bypass_limits if bypass_limits is not None else is_resource_limits_bypassed()

    if configured_mbps is not None:
        if configured_mbps <= 0:
            raise ValueError("configured bitrate must be positive.")
        bps = int(round(configured_mbps * 1_000_000))
        validate_bitrate(bps, bypass=should_bypass)
        return bps

    estimate = _estimate_bitrate(width, height, fps, quality)
    if should_bypass:
        return max(MIN_VIDEO_BITRATE_BPS, min(estimate, MAX_VIDEO_BITRATE_BPS))

    # Size cap based on MAX_OUTPUT_SIZE_BYTES with 10% margin for container/muxing
    size_cap = int((MAX_OUTPUT_SIZE_BYTES * 8 * 0.9) / duration_seconds)
    if size_cap < MIN_VIDEO_BITRATE_BPS:
        raise ResourceLimitError(
            f"Video duration ({duration_seconds:.1f}s) is too long to fit within the "
            f"output size limit at minimum acceptable bitrate."
        )

    return max(MIN_VIDEO_BITRATE_BPS, min(estimate, MAX_VIDEO_BITRATE_BPS, size_cap))


def _calculate_processing_units(
    processed_frames: int,
    grid_width: int,
    grid_height: int,
) -> int:
    """One processing unit represents one LEGO tile processed for one frame."""
    if processed_frames < 1 or grid_width < 1 or grid_height < 1:
        raise ValueError("parameters must be positive.")
    return processed_frames * grid_width * grid_height


def _calculate_credits(processing_units: int, base_credits: int = 1) -> int:
    """Calculate billing / token bucket credits based on processing units and base fee."""
    return max(1, base_credits + math.ceil(processing_units / CREDIT_TILE_UNIT))


# ---------------------------------------------------------------------------
# Video estimation
# ---------------------------------------------------------------------------


def estimate_video_cost(
    config: MosaicConfig,
    source_width: int,
    source_height: int,
    source_fps: float,
    frame_count: int,
) -> CostEstimate:
    """
    Estimate resource usage and credits for a video job.

    `frame_count` is the number of source frames.
    """
    if source_width < 1 or source_height < 1:
        raise ValueError("source dimensions must be positive.")
    if source_fps <= 0:
        raise ValueError("source_fps must be positive.")
    if frame_count < 1:
        raise ValueError("frame_count must be positive.")

    output_fps = resolve_output_fps(config.fps, source_fps)
    output_width, output_height = calculate_output_dimensions(
        config.grid_width, config.tile_size, source_width, source_height
    )
    _, grid_height = calculate_grid_dimensions(
        config.grid_width, source_width, source_height
    )

    duration_seconds = frame_count / source_fps
    output_frame_count = max(1, int(round(duration_seconds * output_fps)))

    # Only unique frames are actually quantized and rendered.
    # When raising FPS, source frames are repeated without re-processing.
    # When lowering FPS, dropped frames are skipped.
    processed_frames = max(1, min(frame_count, output_frame_count))

    bitrate_bps = select_bitrate_bps(
        width=output_width,
        height=output_height,
        fps=output_fps,
        quality=config.quality,
        duration_seconds=duration_seconds,
        configured_mbps=config.bitrate_mbps,
        bypass_limits=config.bypass_limits,
    )

    estimated_size_bytes = int(bitrate_bps * duration_seconds / 8)
    processing_units = _calculate_processing_units(
        processed_frames=processed_frames,
        grid_width=config.grid_width,
        grid_height=grid_height,
    )

    credits = _calculate_credits(processing_units, base_credits=2)

    return CostEstimate(
        output_width=output_width,
        output_height=output_height,
        output_fps=output_fps,
        frame_count=output_frame_count,
        processed_frames=processed_frames,
        duration_seconds=duration_seconds,
        estimated_bitrate_bps=bitrate_bps,
        estimated_size_bytes=estimated_size_bytes,
        estimated_size_mb=(estimated_size_bytes / (1024 * 1024)),
        raw_rgb_bytes=output_width * output_height * 3,
        processing_units=processing_units,
        estimated_credits=credits,
    )


# ---------------------------------------------------------------------------
# Image estimation
# ---------------------------------------------------------------------------


def estimate_image_cost(
    config: MosaicConfig,
    source_width: int,
    source_height: int,
) -> CostEstimate:
    """Estimate resource usage and credits for a single image."""
    output_width, output_height = calculate_output_dimensions(
        config.grid_width, config.tile_size, source_width, source_height
    )
    _, grid_height = calculate_grid_dimensions(
        config.grid_width, source_width, source_height
    )

    raw_rgb_bytes = output_width * output_height * 3
    processing_units = _calculate_processing_units(
        processed_frames=1,
        grid_width=config.grid_width,
        grid_height=grid_height,
    )
    credits = _calculate_credits(processing_units, base_credits=1)

    return CostEstimate(
        output_width=output_width,
        output_height=output_height,
        output_fps=0.0,
        frame_count=1,
        processed_frames=1,
        duration_seconds=0.0,
        estimated_bitrate_bps=0,
        estimated_size_bytes=raw_rgb_bytes,
        estimated_size_mb=(raw_rgb_bytes / (1024 * 1024)),
        raw_rgb_bytes=raw_rgb_bytes,
        processing_units=processing_units,
        estimated_credits=credits,
    )


# ---------------------------------------------------------------------------
# GIF estimation
# ---------------------------------------------------------------------------


def estimate_gif_cost(
    config: MosaicConfig,
    source_width: int,
    source_height: int,
    source_frame_count: int,
    duration_seconds: float,
) -> CostEstimate:
    """Estimate resource usage and credits for an animated GIF."""
    if source_width < 1 or source_height < 1:
        raise ValueError("source dimensions must be positive.")
    if source_frame_count < 1:
        raise ValueError("source_frame_count must be positive.")
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive.")

    source_fps = source_frame_count / duration_seconds
    output_fps = resolve_output_fps(config.fps, source_fps)
    output_width, output_height = calculate_output_dimensions(
        config.grid_width, config.tile_size, source_width, source_height
    )
    _, grid_height = calculate_grid_dimensions(
        config.grid_width, source_width, source_height
    )

    output_frame_count = max(1, int(round(duration_seconds * output_fps)))
    processed_frames = max(1, min(source_frame_count, output_frame_count))

    processing_units = _calculate_processing_units(
        processed_frames=processed_frames,
        grid_width=config.grid_width,
        grid_height=grid_height,
    )
    # GIF is 256-color LZW compressed, roughly 1 byte per pixel per frame before compression
    estimated_size_bytes = int(output_width * output_height * output_frame_count * 0.4)
    credits = _calculate_credits(processing_units, base_credits=2)

    return CostEstimate(
        output_width=output_width,
        output_height=output_height,
        output_fps=output_fps,
        frame_count=output_frame_count,
        processed_frames=processed_frames,
        duration_seconds=duration_seconds,
        estimated_bitrate_bps=0,
        estimated_size_bytes=estimated_size_bytes,
        estimated_size_mb=(estimated_size_bytes / (1024 * 1024)),
        raw_rgb_bytes=output_width * output_height * 3,
        processing_units=processing_units,
        estimated_credits=credits,
    )
