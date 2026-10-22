from __future__ import annotations

# Hard resource limits matching platform standards

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


_BYPASS_RESOURCE_LIMITS: bool = False


def set_bypass_resource_limits(bypass: bool = True) -> None:
    """Globally enable or disable bypassing of resource limits."""
    global _BYPASS_RESOURCE_LIMITS
    _BYPASS_RESOURCE_LIMITS = bypass


def is_resource_limits_bypassed() -> bool:
    """Return whether resource limits are currently bypassed."""
    return _BYPASS_RESOURCE_LIMITS


# Validation helpers


def validate_input_size(size_bytes: int, bypass: bool | None = None) -> None:
    """Reject input files that exceed the configured input limit."""
    if size_bytes < 0:
        raise ValueError("Input file size cannot be negative.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if size_bytes > MAX_INPUT_SIZE_BYTES:
        raise ResourceLimitError(
            f"Input file is too large: {_format_mib(size_bytes):.2f} MiB. "
            f"Maximum is {_format_mib(MAX_INPUT_SIZE_BYTES):.0f} MiB."
        )


def validate_output_resolution(
    width: int,
    height: int,
    bypass: bool | None = None,
) -> None:
    """Reject output resolutions that exceed the pixel budget."""
    if width < 1 or height < 1:
        raise ResourceLimitError("Output dimensions must be positive.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    pixels = width * height
    if pixels > MAX_OUTPUT_PIXELS:
        raise ResourceLimitError(
            f"Output resolution is too large: {width}x{height} "
            f"({_format_mp(pixels):.2f} MP). "
            f"Maximum is {_format_mp(MAX_OUTPUT_PIXELS):.2f} MP."
        )


def validate_output_size(size_bytes: int, bypass: bool | None = None) -> None:
    """Reject output files that exceed the storage limit."""
    if size_bytes < 0:
        raise ValueError("Output file size cannot be negative.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if size_bytes > MAX_OUTPUT_SIZE_BYTES:
        raise ResourceLimitError(
            f"Output file size is too large: {_format_mib(size_bytes):.2f} MiB. "
            f"Maximum is {_format_mib(MAX_OUTPUT_SIZE_BYTES):.0f} MiB."
        )


def validate_video_duration(duration_seconds: float, bypass: bool | None = None) -> None:
    """Reject videos that exceed the duration limit."""
    if duration_seconds < 0:
        raise ValueError("Video duration cannot be negative.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if duration_seconds > MAX_VIDEO_DURATION_SECONDS:
        raise ResourceLimitError(
            f"Video duration is too long: {duration_seconds:.1f}s. "
            f"Maximum is {MAX_VIDEO_DURATION_SECONDS:.0f}s."
        )


def validate_video_fps(fps: float, bypass: bool | None = None) -> None:
    """Reject video frame rates that exceed the FPS ceiling."""
    if fps <= 0:
        raise ValueError("Video FPS must be positive.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if fps > MAX_VIDEO_FPS:
        raise ResourceLimitError(
            f"Video FPS is too high: {fps:.1f}. "
            f"Maximum is {MAX_VIDEO_FPS:.0f} FPS."
        )


def validate_gif_frames(frames: int, bypass: bool | None = None) -> None:
    """Reject GIFs with too many frames."""
    if frames < 1:
        raise ValueError("Frame count must be at least 1.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if frames > MAX_GIF_FRAMES:
        raise ResourceLimitError(
            f"GIF has too many frames: {frames}. "
            f"Maximum is {MAX_GIF_FRAMES} frames."
        )


def validate_gif_duration(duration_seconds: float, bypass: bool | None = None) -> None:
    """Reject GIFs that exceed the animated duration limit."""
    if duration_seconds < 0:
        raise ValueError("GIF duration cannot be negative.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if duration_seconds > MAX_GIF_DURATION_SECONDS:
        raise ResourceLimitError(
            f"GIF duration is too long: {duration_seconds:.1f}s. "
            f"Maximum is {MAX_GIF_DURATION_SECONDS:.0f}s."
        )


def validate_processing_units(units: int, bypass: bool | None = None) -> None:
    """Reject jobs exceeding processing unit limit."""
    if units < 0:
        raise ValueError("Processing units cannot be negative.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if units > MAX_PROCESSING_UNITS:
        raise ResourceLimitError(
            f"Job exceeds processing unit limit: {units:,} units. "
            f"Maximum is {MAX_PROCESSING_UNITS:,} units."
        )


def validate_workers(workers: int, bypass: bool | None = None) -> None:
    """Validate parallel worker count."""
    if workers < 1:
        raise ValueError("workers must be positive.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if workers > MAX_WORKERS:
        raise ValueError(f"workers must not exceed {MAX_WORKERS}")


def validate_buffer_size(buffer_size: int, bypass: bool | None = None) -> None:
    """Validate frame queue buffer size."""
    if buffer_size < 1:
        raise ValueError("buffer_size must be positive.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if buffer_size > MAX_BUFFER_SIZE:
        raise ValueError(f"buffer_size must not exceed {MAX_BUFFER_SIZE}")


def validate_bitrate(bitrate_bps: int, bypass: bool | None = None) -> None:
    """Validate video bitrate."""
    if bitrate_bps < 1:
        raise ValueError("bitrate must be positive.")

    if bypass is True or (bypass is None and _BYPASS_RESOURCE_LIMITS):
        return

    if bitrate_bps < MIN_VIDEO_BITRATE_BPS:
        raise ResourceLimitError(
            f"Bitrate is too low: {bitrate_bps / 1_000_000:.2f} Mbps. "
            f"Minimum is {MIN_VIDEO_BITRATE_BPS / 1_000_000:.2f} Mbps."
        )

    if bitrate_bps > MAX_VIDEO_BITRATE_BPS:
        raise ResourceLimitError(
            f"Bitrate is too high: {bitrate_bps / 1_000_000:.2f} Mbps. "
            f"Maximum is {MAX_VIDEO_BITRATE_BPS / 1_000_000:.0f} Mbps."
        )


def _format_mib(size_bytes: int) -> float:
    return size_bytes / (1024 * 1024)


def _format_mp(pixels: int) -> float:
    return pixels / 1_000_000
