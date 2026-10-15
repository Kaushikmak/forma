from dataclasses import dataclass


@dataclass(frozen=True)
class MosaicConfig:
    grid_width: int = 64
    tile_size: int = 16

    def __post_init__(self) -> None:
        if self.grid_width < 1:
            raise ValueError("grid_width must be positive")
        if self.tile_size < 4:
            raise ValueError("tile_size must be at least 4")
