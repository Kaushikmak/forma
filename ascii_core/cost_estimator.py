from __future__ import annotations

import math
from dataclasses import dataclass

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    resolve_output_fps,
)
from config import FPS, AsciiConfig, Quality
from resource_limits import (
    MAX_OUTPUT_SIZE_BYTES,
    MAX_VIDEO_BITRATE_BPS,
    MIN_VIDEO_BITRATE_BPS,
    is_resource_limits_bypassed,
    validate_bitrate,
)


@dataclass(frozen=True)
class CostEstimate:
    """Estimated resource usage and credit cost for an ASCII conversion job."""

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
    Clamps into [MIN_VIDEO_BITRATE_BPS, MAX_VIDEO_BITRATE_BPS] and caps by 50 MiB output size limit.
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
        return max(1, estimate)

    clamped = max(MIN_VIDEO_BITRATE_BPS, min(estimate, MAX_VIDEO_BITRATE_BPS))
    max_payload_bits = int(MAX_OUTPUT_SIZE_BYTES * 0.90 * 8)
    bitrate_cap = max(MIN_VIDEO_BITRATE_BPS, int(max_payload_bits / duration_seconds))
    return min(clamped, bitrate_cap)


def estimate_image_cost(
    config: AsciiConfig,
    source_width: int,
    source_height: int,
) -> CostEstimate:
    """Estimate resource usage and credit cost for single image conversion."""
    out_w, out_h = calculate_output_dimensions(
        config.grid_width, config.tile_size, source_width, source_height
    )
    grid_w, grid_h = calculate_grid_dimensions(
        config.grid_width, source_width, source_height
    )
    tiles = grid_w * grid_h
    raw_rgb_bytes = out_w * out_h * 3
    estimated_size_bytes = int(out_w * out_h * 1.2)
    units = tiles
    credits = max(1, math.ceil(units / CREDIT_TILE_UNIT))

    return CostEstimate(
        output_width=out_w,
        output_height=out_h,
        output_fps=0.0,
        frame_count=1,
        processed_frames=1,
        duration_seconds=0.0,
        estimated_bitrate_bps=0,
        estimated_size_bytes=estimated_size_bytes,
        estimated_size_mb=round(estimated_size_bytes / (1024 * 1024), 2),
        raw_rgb_bytes=raw_rgb_bytes,
        processing_units=units,
        estimated_credits=credits,
    )


def estimate_gif_cost(
    config: AsciiConfig,
    source_width: int,
    source_height: int,
    frame_count: int,
    duration_seconds: float,
) -> CostEstimate:
    """Estimate resource usage and credit cost for animated GIF conversion."""
    out_w, out_h = calculate_output_dimensions(
        config.grid_width, config.tile_size, source_width, source_height
    )
    grid_w, grid_h = calculate_grid_dimensions(
        config.grid_width, source_width, source_height
    )
    tiles_per_frame = grid_w * grid_h
    total_tiles = tiles_per_frame * frame_count
    raw_rgb_bytes = out_w * out_h * 3 * frame_count
    # GIF typically compresses to ~0.5 bytes per pixel
    estimated_size_bytes = int(out_w * out_h * frame_count * 0.5)
    effective_fps = frame_count / max(0.001, duration_seconds)
    credits = max(1, math.ceil(total_tiles / CREDIT_TILE_UNIT))

    return CostEstimate(
        output_width=out_w,
        output_height=out_h,
        output_fps=effective_fps,
        frame_count=frame_count,
        processed_frames=frame_count,
        duration_seconds=duration_seconds,
        estimated_bitrate_bps=int((estimated_size_bytes * 8) / max(0.001, duration_seconds)),
        estimated_size_bytes=estimated_size_bytes,
        estimated_size_mb=round(estimated_size_bytes / (1024 * 1024), 2),
        raw_rgb_bytes=raw_rgb_bytes,
        processing_units=total_tiles,
        estimated_credits=credits,
    )


def estimate_video_cost(
    config: AsciiConfig,
    source_width: int,
    source_height: int,
    source_fps: float,
    frame_count: int,
    duration_seconds: float,
) -> CostEstimate:
    """Estimate resource usage and credit cost for video conversion."""
    out_w, out_h = calculate_output_dimensions(
        config.grid_width, config.tile_size, source_width, source_height
    )
    grid_w, grid_h = calculate_grid_dimensions(
        config.grid_width, source_width, source_height
    )
    out_fps = resolve_output_fps(config.fps, source_fps)
    processed_frames = max(1, int(round(duration_seconds * out_fps)))
    bitrate = select_bitrate_bps(
        out_w,
        out_h,
        out_fps,
        config.quality,
        duration_seconds,
        config.bitrate_mbps,
        config.bypass_limits,
    )
    estimated_size_bytes = int((bitrate * duration_seconds) / 8)
    tiles_per_frame = grid_w * grid_h
    total_tiles = tiles_per_frame * processed_frames
    credits = max(1, math.ceil(total_tiles / CREDIT_TILE_UNIT))

    return CostEstimate(
        output_width=out_w,
        output_height=out_h,
        output_fps=out_fps,
        frame_count=frame_count,
        processed_frames=processed_frames,
        duration_seconds=duration_seconds,
        estimated_bitrate_bps=bitrate,
        estimated_size_bytes=estimated_size_bytes,
        estimated_size_mb=round(estimated_size_bytes / (1024 * 1024), 2),
        raw_rgb_bytes=out_w * out_h * 3 * processed_frames,
        processing_units=total_tiles,
        estimated_credits=credits,
    )
