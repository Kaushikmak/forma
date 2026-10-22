from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

import numpy as np

from config import PAPER, Palette


@dataclass(frozen=True)
class AsciiPaletteData:
    name: str
    paper: tuple[int, int, int]
    default_strength: float
    default_ink_darkness: float
    is_dark: bool
    description: str
    color_transformer: Callable[
        [np.ndarray, np.ndarray, float, float, tuple[int, int, int]],
        tuple[np.ndarray, np.ndarray],
    ]

    def render_colors(
        self,
        rgb: np.ndarray,
        lum: np.ndarray,
        strength: float | None = None,
        ink_darkness: float | None = None,
        paper: tuple[int, int, int] | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Compute (bg, ink) color matrices for each tile.
        rgb: (H, W, 3) float32
        lum: (H, W) float32
        Returns:
            bg: (H, W, 3) float32
            ink: (H, W, 3) float32
        """
        s = self.default_strength if strength is None else strength
        i = self.default_ink_darkness if ink_darkness is None else ink_darkness
        p = self.paper if paper is None else paper
        return self.color_transformer(rgb, lum, s, i, p)


# Transformers for different palette styles


def _mild_transformer(
    rgb: np.ndarray,
    _lum: np.ndarray,
    strength: float,
    ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Warm paper canvas with gentle pastel background tint and dark hue-matched ink."""
    paper_a = np.array(paper, dtype=np.float32)
    bg = np.clip(paper_a + (rgb - paper_a) * strength, 0, 255)
    ink = np.clip(rgb * ink_darkness, 0, 255)
    return bg, ink


def _vibrant_transformer(
    rgb: np.ndarray,
    _lum: np.ndarray,
    strength: float,
    ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Crisp high-key canvas with rich, punchy saturation and vivid tile contrast."""
    paper_a = np.array(paper, dtype=np.float32)
    bg = np.clip(paper_a + (rgb - paper_a) * strength, 0, 255)
    # Boost ink contrast
    ink = np.clip(rgb * (ink_darkness * 0.9), 0, 255)
    return bg, ink


def _dark_transformer(
    rgb: np.ndarray,
    _lum: np.ndarray,
    strength: float,
    ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Modern dark mode with charcoal canvas, deep tinted cells, and luminous glyphs."""
    paper_a = np.array(paper, dtype=np.float32)
    # Background has dark tint
    bg = np.clip(paper_a + (rgb - paper_a) * (strength * 0.35), 0, 255)
    # Glyphs are bright and illuminated against the dark slate
    boost = 1.0 / max(0.1, ink_darkness * 2.0)
    ink = np.clip(rgb * (0.9 + 0.3 * boost) + 25.0, 0, 255)
    return bg, ink


def _matrix_transformer(
    rgb: np.ndarray,
    lum: np.ndarray,
    strength: float,
    _ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Hacker terminal aesthetic with phosphor digital green glyphs cascading on black."""
    paper_a = np.array(paper, dtype=np.float32)
    bg = np.clip(paper_a + (rgb - paper_a) * (strength * 0.15), 0, 255)
    norm = np.clip(lum[..., None] / 255.0, 0, 1)
    green_phosphor = np.array([25.0, 255.0, 85.0], dtype=np.float32)
    ink = np.clip(green_phosphor * (0.3 + 0.7 * norm), 0, 255)
    return bg, ink


def _amber_transformer(
    rgb: np.ndarray,
    lum: np.ndarray,
    strength: float,
    _ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Vintage 1980s CRT monochrome amber phosphor terminal with warm glow."""
    paper_a = np.array(paper, dtype=np.float32)
    bg = np.clip(paper_a + (rgb - paper_a) * (strength * 0.15), 0, 255)
    norm = np.clip(lum[..., None] / 255.0, 0, 1)
    amber_phosphor = np.array([255.0, 176.0, 0.0], dtype=np.float32)
    ink = np.clip(amber_phosphor * (0.3 + 0.7 * norm), 0, 255)
    return bg, ink


def _cyberpunk_transformer(
    rgb: np.ndarray,
    lum: np.ndarray,
    strength: float,
    _ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Synthwave neon palette with electric cyan, hot magenta, and deep violet."""
    paper_a = np.array(paper, dtype=np.float32)
    bg = np.clip(paper_a + (rgb - paper_a) * (strength * 0.3), 0, 255)
    t = np.clip(lum[..., None] / 255.0, 0, 1)
    cyan = np.array([0.0, 240.0, 255.0], dtype=np.float32)
    magenta = np.array([255.0, 20.0, 147.0], dtype=np.float32)
    neon = magenta * (1.0 - t) + cyan * t
    ink = np.clip(neon * 0.8 + rgb * 0.3, 0, 255)
    return bg, ink


def _monochrome_transformer(
    _rgb: np.ndarray,
    lum: np.ndarray,
    strength: float,
    ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Pure minimalist black-and-white printmaker / typewriter aesthetic."""
    paper_a = np.array(paper, dtype=np.float32)
    if strength > 0:
        gray = lum[..., None]
        bg = np.clip(paper_a + (gray - paper_a) * strength, 0, 255)
    else:
        bg = np.broadcast_to(paper_a, (*lum.shape, 3)).copy()
    ink_1ch = np.clip(lum[..., None] * ink_darkness, 0, 255)
    ink = np.repeat(ink_1ch, 3, axis=-1)
    return bg, ink


def _retro_transformer(
    rgb: np.ndarray,
    _lum: np.ndarray,
    strength: float,
    ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Aged sepia parchment with warm sepia tones and vintage typewriter ink."""
    paper_a = np.array(paper, dtype=np.float32)
    sepia_matrix = np.array(
        [
            [0.393, 0.769, 0.189],
            [0.349, 0.686, 0.168],
            [0.272, 0.534, 0.131],
        ],
        dtype=np.float32,
    )
    sepia_rgb = np.clip(rgb @ sepia_matrix.T, 0, 255)
    bg = np.clip(paper_a + (sepia_rgb - paper_a) * strength, 0, 255)
    ink = np.clip(sepia_rgb * ink_darkness, 0, 255)
    return bg, ink


def _pastel_transformer(
    rgb: np.ndarray,
    _lum: np.ndarray,
    strength: float,
    ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Soft dreamy pastel tones with gentle, washed candy tints and low contrast."""
    paper_a = np.array(paper, dtype=np.float32)
    pastel_rgb = np.clip(rgb * 0.7 + 255.0 * 0.3, 0, 255)
    bg = np.clip(paper_a + (pastel_rgb - paper_a) * strength, 0, 255)
    ink = np.clip(pastel_rgb * ink_darkness, 0, 255)
    return bg, ink


def _nord_transformer(
    rgb: np.ndarray,
    lum: np.ndarray,
    strength: float,
    _ink_darkness: float,
    paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Nordic polar night slate with frost blues and aurora accents."""
    paper_a = np.array(paper, dtype=np.float32)
    bg = np.clip(paper_a + (rgb - paper_a) * (strength * 0.35), 0, 255)
    frost_blue = np.array([136.0, 192.0, 208.0], dtype=np.float32)
    t = np.clip(lum[..., None] / 255.0, 0, 1)
    ink = np.clip(paper_a + (frost_blue - paper_a) * (0.35 + 0.65 * t) + rgb * 0.2, 0, 255)
    return bg, ink


def _gameboy_transformer(
    _rgb: np.ndarray,
    lum: np.ndarray,
    _strength: float,
    _ink_darkness: float,
    _paper: tuple[int, int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Iconic 1989 handheld 4-shade monochrome green LCD palette."""
    gb_shades = np.array(
        [
            [15.0, 56.0, 15.0],    # Darkest olive green
            [48.0, 98.0, 48.0],    # Dark olive
            [139.0, 172.0, 15.0],  # Light olive green
            [155.0, 188.0, 15.0],  # Lightest LCD lime
        ],
        dtype=np.float32,
    )
    # Quantize lum to 4 bins
    shade_idx = np.clip((lum / 64.0).astype(int), 0, 3)
    bg = gb_shades[shade_idx]
    # Ink is one step darker than background for contrast
    ink_idx = np.clip(shade_idx - 1, 0, 3)
    ink = gb_shades[ink_idx]
    return bg, ink


PALETTES: Final[dict[Palette, AsciiPaletteData]] = {
    Palette.MILD: AsciiPaletteData(
        name="mild",
        paper=PAPER,
        default_strength=0.50,
        default_ink_darkness=0.30,
        is_dark=False,
        description="Warm archival paper with soft pastel cell tints and dark hue-matched ink.",
        color_transformer=_mild_transformer,
    ),
    Palette.VIBRANT: AsciiPaletteData(
        name="vibrant",
        paper=(255, 255, 255),
        default_strength=0.70,
        default_ink_darkness=0.20,
        is_dark=False,
        description="Pure white canvas with punchy, high-saturation cell tints and vivid contrast.",
        color_transformer=_vibrant_transformer,
    ),
    Palette.DARK: AsciiPaletteData(
        name="dark",
        paper=(20, 22, 28),
        default_strength=0.25,
        default_ink_darkness=0.50,
        is_dark=True,
        description="Modern dark mode with charcoal canvas, deep tinted cells, and bright luminous glyphs.",
        color_transformer=_dark_transformer,
    ),
    Palette.MATRIX: AsciiPaletteData(
        name="matrix",
        paper=(10, 16, 12),
        default_strength=0.20,
        default_ink_darkness=0.50,
        is_dark=True,
        description="Classic hacker terminal with digital phosphor green glyphs cascading on black.",
        color_transformer=_matrix_transformer,
    ),
    Palette.AMBER: AsciiPaletteData(
        name="amber",
        paper=(20, 14, 8),
        default_strength=0.20,
        default_ink_darkness=0.50,
        is_dark=True,
        description="Vintage 1980s monochrome CRT amber phosphor terminal with warm golden glow.",
        color_transformer=_amber_transformer,
    ),
    Palette.CYBERPUNK: AsciiPaletteData(
        name="cyberpunk",
        paper=(16, 12, 28),
        default_strength=0.30,
        default_ink_darkness=0.50,
        is_dark=True,
        description="Synthwave neon palette with electric cyan, hot magenta, and deep violet.",
        color_transformer=_cyberpunk_transformer,
    ),
    Palette.MONOCHROME: AsciiPaletteData(
        name="monochrome",
        paper=(255, 255, 255),
        default_strength=0.0,
        default_ink_darkness=0.30,
        is_dark=False,
        description="Pure minimalist black-and-white printmaker / typewriter aesthetic.",
        color_transformer=_monochrome_transformer,
    ),
    Palette.RETRO: AsciiPaletteData(
        name="retro",
        paper=(244, 235, 215),
        default_strength=0.40,
        default_ink_darkness=0.28,
        is_dark=False,
        description="Aged sepia parchment with warm sepia tones and vintage typewriter ink.",
        color_transformer=_retro_transformer,
    ),
    Palette.PASTEL: AsciiPaletteData(
        name="pastel",
        paper=(252, 250, 248),
        default_strength=0.35,
        default_ink_darkness=0.45,
        is_dark=False,
        description="Soft dreamy pastel tones with gentle washed candy tints and low contrast.",
        color_transformer=_pastel_transformer,
    ),
    Palette.NORD: AsciiPaletteData(
        name="nord",
        paper=(46, 52, 64),
        default_strength=0.30,
        default_ink_darkness=0.50,
        is_dark=True,
        description="Nordic polar night slate with frost blues and aurora accents.",
        color_transformer=_nord_transformer,
    ),
    Palette.GAMEBOY: AsciiPaletteData(
        name="gameboy",
        paper=(15, 56, 15),
        default_strength=0.50,
        default_ink_darkness=0.50,
        is_dark=True,
        description="Iconic 1989 handheld 4-shade monochrome green LCD palette.",
        color_transformer=_gameboy_transformer,
    ),
}

# Aliases
PALETTES[Palette.CLASSIC] = PALETTES[Palette.MILD]
PALETTES[Palette.EXTENDED] = PALETTES[Palette.VIBRANT]
PALETTES[Palette.CRAYON] = PALETTES[Palette.VIBRANT]
PALETTES[Palette.EARTH] = PALETTES[Palette.RETRO]
PALETTES[Palette.COOL] = PALETTES[Palette.NORD]
PALETTES[Palette.WARM] = PALETTES[Palette.MILD]


def get_palette(palette: Palette | str) -> AsciiPaletteData:
    """Retrieve palette definition by enum or case-insensitive string."""
    if isinstance(palette, str):
        try:
            palette = Palette(palette.lower())
        except ValueError:
            raise ValueError(
                f"Unsupported palette '{palette}'. Supported: {[p.value for p in Palette]}"
            )
    try:
        return PALETTES[palette]
    except KeyError:
        raise ValueError(f"Palette data not registered for: {palette}")


def list_palettes() -> list[str]:
    """Return all available palette names."""
    return [p.value for p in Palette]
