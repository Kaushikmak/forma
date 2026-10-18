from __future__ import annotations

# Hard resource limits


MAX_INPUT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MiB 

MAX_OUTPUT_SIZE_BYTES = 50 * 1024 * 1024  # 50 MiB 
MAX_OUTPUT_PIXELS = 12_000_000  # 12 MP

MAX_VIDEO_DURATION_SECONDS = 60.0
MAX_VIDEO_FPS = 60.0

MAX_GIF_DURATION_SECONDS = 30.0
MAX_GIF_FRAMES = 300

MAX_PROCESSING_UNITS = 100_000_000

MAX_WORKERS = 32
MAX_BUFFER_SIZE = 128

MIN_VIDEO_BITRATE_BPS = 500_000
MAX_VIDEO_BITRATE_BPS = 20_000_000


# Exceptions


class ResourceLimitError(ValueError):
    """Raised when a requested job exceeds a resource limit."""


# Input validation


def validate_input_size(size_bytes: int) -> None:
    """Reject input files that exceed the configured input limit."""

    if size_bytes < 0:
        raise ValueError("Input file size cannot be negative.")

    if size_bytes > MAX_INPUT_SIZE_BYTES:
        raise ResourceLimitError(
            f"Input file is too large: "
            f"{_format_mib(size_bytes):.2f} MiB. "
            f"Maximum is {_format_mib(MAX_INPUT_SIZE_BYTES):.0f} MiB."
        )


# Output validation


def validate_output_resolution(
    width: int,
    height: int,
) -> None:
    """Reject output resolutions that exceed the pixel budget."""

    if width < 1 or height < 1:
        raise ResourceLimitError("Output dimensions must be positive.")

    pixels = width * height

    if pixels > MAX_OUTPUT_PIXELS:
        raise ResourceLimitError(
            f"Output resolution is too large: "
            f"{width}x{height} "
            f"({_format_mp(pixels):.2f} MP). "
            f"Maximum is {_format_mp(MAX_OUTPUT_PIXELS):.2f} MP."
        )


def validate_output_size(size_bytes: int) -> None:
    """Reject output files that exceed the storage limit."""

    if size_bytes < 0:
        raise ValueError("Output file size cannot be negative.")

    if size_bytes > MAX_OUTPUT_SIZE_BYTES:
        raise ResourceLimitError(
            f"Estimated output size is too large: "
            f"{_format_mib(size_bytes):.2f} MiB. "
            f"Maximum is {_format_mib(MAX_OUTPUT_SIZE_BYTES):.0f} MiB."
        )


# Video validation


def validate_video_duration(
    duration_seconds: float,
) -> None:
    """Reject videos that are too long."""

    if duration_seconds <= 0:
        raise ResourceLimitError("Video duration must be positive.")

    if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
        raise ResourceLimitError(
            f"Video is too long: "
            f"{duration_seconds:.2f} seconds. "
            f"Maximum is {MAX_VIDEO_DURATION_SECONDS:.0f} seconds."
        )


def validate_video_fps(fps: float) -> None:
    """Reject unsupported video frame rates."""

    if fps <= 0:
        raise ResourceLimitError("Video FPS must be positive.")

    if fps > MAX_VIDEO_FPS:
        raise ResourceLimitError(
            f"Video FPS is too high: "
            f"{fps:.2f}. "
            f"Maximum is {MAX_VIDEO_FPS:.0f} FPS."
        )


def validate_bitrate(bitrate_bps: int) -> None:
    """Reject unsafe video bitrate values."""

    if bitrate_bps < MIN_VIDEO_BITRATE_BPS:
        raise ResourceLimitError(
            f"Video bitrate is too low: "
            f"{bitrate_bps / 1_000_000:.2f} Mbps. "
            f"Minimum is "
            f"{MIN_VIDEO_BITRATE_BPS / 1_000_000:.2f} Mbps."
        )

    if bitrate_bps > MAX_VIDEO_BITRATE_BPS:
        raise ResourceLimitError(
            f"Video bitrate is too high: "
            f"{bitrate_bps / 1_000_000:.2f} Mbps. "
            f"Maximum is "
            f"{MAX_VIDEO_BITRATE_BPS / 1_000_000:.2f} Mbps."
        )


# GIF validation


def validate_gif_duration(
    duration_seconds: float,
) -> None:
    """Reject GIFs that are too long."""

    if duration_seconds <= 0:
        raise ResourceLimitError("GIF duration must be positive.")

    if duration_seconds > MAX_GIF_DURATION_SECONDS:
        raise ResourceLimitError(
            f"GIF is too long: "
            f"{duration_seconds:.2f} seconds. "
            f"Maximum is {MAX_GIF_DURATION_SECONDS:.0f} seconds."
        )


def validate_gif_frames(
    frame_count: int,
) -> None:
    """Reject GIFs containing too many frames."""

    if frame_count < 1:
        raise ResourceLimitError("GIF must contain at least one frame.")

    if frame_count > MAX_GIF_FRAMES:
        raise ResourceLimitError(
            f"GIF contains too many frames: "
            f"{frame_count}. "
            f"Maximum is {MAX_GIF_FRAMES}."
        )


# Processing validation


def validate_processing_units(
    processing_units: int,
) -> None:
    """Reject jobs with excessive estimated processing work."""

    if processing_units < 0:
        raise ValueError("processing_units cannot be negative.")

    if processing_units > MAX_PROCESSING_UNITS:
        raise ResourceLimitError(
            f"Estimated processing workload is too large: "
            f"{processing_units:,} units. "
            f"Maximum is {MAX_PROCESSING_UNITS:,} units."
        )


def validate_workers(workers: int) -> None:
    """Reject excessive worker counts."""

    if workers < 1:
        raise ResourceLimitError("workers must be positive.")

    if workers > MAX_WORKERS:
        raise ResourceLimitError(f"workers must not exceed {MAX_WORKERS}.")


def validate_buffer_size(buffer_size: int) -> None:
    """Reject excessive queue buffer sizes."""

    if buffer_size < 1:
        raise ResourceLimitError("buffer_size must be positive.")

    if buffer_size > MAX_BUFFER_SIZE:
        raise ResourceLimitError(f"buffer_size must not exceed {MAX_BUFFER_SIZE}.")


# Helpers


def _format_mib(size_bytes: int) -> float:
    """Convert bytes to mebibytes."""

    return size_bytes / (1024 * 1024)


def _format_mp(pixel_count: int) -> float:
    """Convert pixels to megapixels."""

    return pixel_count / 1_000_000
