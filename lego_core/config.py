from dataclasses import dataclass
from enum import Enum


class Palette(str, Enum):
    CLASSIC = "classic"


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

    def __post_init__(self) -> None:
        if self.grid_width < 16:
            raise ValueError("grid_width must be atleast 16")
        if self.grid_width > 256:
            raise ValueError("grid_width must not exceed 256")
        if self.tile_size < 4:
            raise ValueError("tile_size must be at least 4")
        if self.tile_size > 32:
            raise ValueError("tile_size must not exceed 32")
        if self.workers < 1:
            raise ValueError("workers must be positive")
        if self.buffer_size < 1:
            raise ValueError("buffer_size must be positive")
