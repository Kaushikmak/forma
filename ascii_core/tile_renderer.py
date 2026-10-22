from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Final

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import PAPER
from palette import AsciiPaletteData, get_palette

if TYPE_CHECKING:
    from config import AsciiConfig

FONT_PATHS: Final[list[str]] = [
    "DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "C:/Windows/Fonts/consolab.ttf",
    "DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a clean monospace font for ASCII glyph rendering with fallback to default."""
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_glyphs(
    ramp: str,
    cell: int,
    gap: int,
    font_scale: float = 0.88,
) -> np.ndarray:
    """
    Return float32 array (len(ramp), inner, inner) of antialiased glyph coverage 0..1.
    """
    inner = max(1, cell - gap)
    font = load_font(max(1, int(cell * font_scale)))
    glyphs = np.zeros((len(ramp), inner, inner), dtype=np.float32)
    probe = ImageDraw.Draw(Image.new("L", (inner, inner)))

    for i, ch in enumerate(ramp):
        if ch == " ":
            continue
        bb = probe.textbbox((0, 0), ch, font=font)
        bx, by, bw, bh = bb[0], bb[1], bb[2] - bb[0], bb[3] - bb[1]
        m = Image.new("L", (inner, inner), 0)
        ImageDraw.Draw(m).text(
            (round((inner - bw) / 2 - bx), round((inner - bh) / 2 - by)),
            ch,
            font=font,
            fill=255,
        )
        glyphs[i] = np.asarray(m, dtype=np.float32) / 255.0

    glyphs.flags.writeable = False
    return glyphs


@lru_cache(maxsize=128)
def get_glyphs(
    ramp: str,
    cell: int,
    gap: int,
    font_scale: float = 0.88,
) -> np.ndarray:
    """Cached glyph mask array to avoid repeated font rasterization across frames."""
    return build_glyphs(ramp, cell, gap, font_scale)


def render(
    rgb: np.ndarray,
    idx: np.ndarray,
    active: np.ndarray,
    glyphs: np.ndarray,
    cell: int = 14,
    gap: int = 1,
    strength: float = 0.5,
    ink_darkness: float = 0.30,
    paper: tuple[int, int, int] = PAPER,
    even: bool = False,
    palette_data: AsciiPaletteData | None = None,
) -> np.ndarray:
    """
    Compose the ASCII mosaic using numpy vectorization.
    Returns uint8 array (H, W, 3).
    """
    h, w = idx.shape
    inner = glyphs.shape[1]
    cell = max(inner, cell)

    if palette_data is not None:
        lum = np.clip(
            rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32),
            0,
            255,
        )
        bg, ink = palette_data.render_colors(
            rgb,
            lum,
            strength=strength,
            ink_darkness=ink_darkness,
            paper=paper,
        )
        effective_paper = palette_data.paper if paper is None else paper
    else:
        effective_paper = paper
        paper_a = np.array(effective_paper, dtype=np.float32)
        bg = np.clip(paper_a + (rgb - paper_a) * strength, 0, 255)
        ink = np.clip(rgb * ink_darkness, 0, 255)

    paper_a = np.array(effective_paper, dtype=np.float32)

    m = glyphs[idx][..., None]  # (h, w, inner, inner, 1)
    tile = bg[:, :, None, None, :] * (1.0 - m) + ink[:, :, None, None, :] * m
    tile = np.where(active[:, :, None, None, None], tile, paper_a)
    tile = tile.transpose(0, 2, 1, 3, 4)  # (h, inner, w, inner, 3)

    canvas = np.empty((h, cell, w, cell, 3), dtype=np.float32)
    canvas[:] = paper_a
    canvas[:, :inner, :, :inner] = tile
    out = canvas.reshape(h * cell, w * cell, 3)
    out = np.clip(out + 0.5, 0, 255).astype(np.uint8)

    if even:
        pad_y, pad_x = out.shape[0] % 2, out.shape[1] % 2
        if pad_y or pad_x:
            out = np.pad(out, ((0, pad_y), (0, pad_x), (0, 0)), mode="edge")

    return out


def render_ascii_tiles(
    rgb: np.ndarray,
    idx: np.ndarray,
    active: np.ndarray,
    glyphs: np.ndarray,
    config: AsciiConfig,
    even: bool = False,
) -> np.ndarray:
    """Render ASCII tiles from configuration."""
    gap = 0 if config.gap is None and even else (1 if config.gap is None else config.gap)
    pal_data = get_palette(config.palette)
    return render(
        rgb=rgb,
        idx=idx,
        active=active,
        glyphs=glyphs,
        cell=config.tile_size,
        gap=gap,
        strength=config.strength,
        ink_darkness=config.ink_darkness,
        paper=config.paper or pal_data.paper,
        even=even,
        palette_data=pal_data,
    )
