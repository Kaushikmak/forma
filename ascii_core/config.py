from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from resource_limits import MAX_BUFFER_SIZE, MAX_WORKERS

# Default paper background matching the original forma warm paper aesthetic
PAPER: Final[tuple[int, int, int]] = (250, 247, 241)

# ordered dense (dark) -> sparse (light)
RAMPS: Final[dict[str, str]] = {
    "default": "@#%&8*+=~-:. ",
    "classic": "@%#*+=-:. ",
    "dense": "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/|()1{}[]?-_+~<>i!lI;:,\"^`'. ",
    "blocks": "█▓▒░ ",
    "simple": "#*+:. ",
}


class Palette(str, Enum):
    MILD = "mild"
    CLASSIC = "classic"  # Alias to mild
    VIBRANT = "vibrant"
    DARK = "dark"
    MATRIX = "matrix"
    AMBER = "amber"
    CYBERPUNK = "cyberpunk"
    MONOCHROME = "monochrome"
    RETRO = "retro"
    PASTEL = "pastel"
    NORD = "nord"
    GAMEBOY = "gameboy"
    EXTENDED = "extended"
    CRAYON = "crayon"
    EARTH = "earth"
    COOL = "cool"
    WARM = "warm"


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
class AsciiConfig:
    grid_width: int = 64
    grid_height: int | None = None
    tile_size: int = 16
    gap: int | None = None
    palette: Palette = Palette.MILD
    ramp: str = "default"
    quality: Quality = Quality.HIGH
    fps: FPS = FPS.ORIGINAL
    strength: float = 0.5
    ink_darkness: float = 0.30
    contrast: float = 1.15
    saturation: float = 1.15
    gamma: float = 1.0
    skip_white: int = 0
    auto_levels: bool = True
    invert: bool = False
    smooth: float = 0.4
    audio: bool = True
    start: float = 0.0
    duration: float | None = None
    write_txt: bool = False
    workers: int = 4
    buffer_size: int = 8
    bitrate_mbps: float | None = None
    bypass_limits: bool = False
    paper: tuple[int, int, int] | None = None
    font_scale: float = 0.88

    @property
    def cell_size(self) -> int:
        return self.tile_size

    def __post_init__(self) -> None:
        if isinstance(self.palette, str):
            try:
                object.__setattr__(self, "palette", Palette(self.palette.lower()))
            except ValueError:
                valid = [p.value for p in Palette]
                raise ValueError(f"Invalid palette '{self.palette}'. Must be one of: {valid}")

        if isinstance(self.quality, str):
            try:
                object.__setattr__(self, "quality", Quality(self.quality.lower()))
            except ValueError:
                valid = [q.value for q in Quality]
                raise ValueError(f"Invalid quality '{self.quality}'. Must be one of: {valid}")

        if isinstance(self.fps, str):
            try:
                object.__setattr__(self, "fps", FPS(self.fps))
            except ValueError:
                valid = [f.value for f in FPS]
                raise ValueError(f"Invalid fps '{self.fps}'. Must be one of: {valid}")

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

        if self.strength < 0.0 or self.strength > 1.0:
            raise ValueError("strength must be between 0.0 and 1.0")

        if self.gap is not None and self.gap < 0:
            raise ValueError("gap cannot be negative")

        if self.bitrate_mbps is not None and self.bitrate_mbps <= 0:
            raise ValueError("bitrate_mbps must be positive when provided")
