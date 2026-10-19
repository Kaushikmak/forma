from dataclasses import dataclass
from enum import Enum

from resource_limits import MAX_BUFFER_SIZE, MAX_WORKERS


class Palette(str, Enum):
    CLASSIC = "classic"
    EXTENDED = "extended"


class Quality(str, Enum):
    STANDARD = "standard"
    HIGH = "high"
    MAXIMUM = "maximum"


class FPS(str, Enum):
    ORIGINAL = "original"
    FPS_24 = "24"
    FPS_30 = "30"
    FPS_60 = "60"


@dataclass(frozen=True)
class MosaicConfig:
    grid_width: int = 64
    tile_size: int = 16
    palette: Palette = Palette.CLASSIC
    fps: FPS = FPS.ORIGINAL
    quality: Quality = Quality.HIGH
    workers: int = 4
    buffer_size: int = 8
    bitrate_mbps: float | None = None
    bypass_limits: bool = False

    def __post_init__(self) -> None:
        if not self.bypass_limits:
            if self.grid_width < 16:
                raise ValueError("grid_width must be at least 16")
            if self.grid_width > 256:
                raise ValueError("grid_width must not exceed 256")
            if self.tile_size < 8:
                raise ValueError("tile_size must be at least 8")
            if self.tile_size > 32:
                raise ValueError("tile_size must not exceed 32")
            if self.workers < 1:
                raise ValueError("workers must be positive")
            if self.workers > MAX_WORKERS:
                raise ValueError(f"workers must not exceed {MAX_WORKERS}")
            if self.buffer_size < 1:
                raise ValueError("buffer_size must be positive")
            if self.buffer_size > MAX_BUFFER_SIZE:
                raise ValueError(f"buffer_size must not exceed {MAX_BUFFER_SIZE}")
        else:
            if self.grid_width < 1:
                raise ValueError("grid_width must be positive")
            if self.tile_size < 4:
                raise ValueError("tile_size must be at least 4 pixels.")
            if self.workers < 1:
                raise ValueError("workers must be positive")
            if self.buffer_size < 1:
                raise ValueError("buffer_size must be positive")

        if self.bitrate_mbps is not None and self.bitrate_mbps <= 0:
            raise ValueError("bitrate_mbps must be positive when provided")

