#!/usr/bin/env python3
"""
Image / Video / GIF -> ASCII tile mosaic.

Every cell is a square 1x1 tile:
  * one ASCII character (chosen by the tile's brightness)
  * a colored background and ink rendered according to the chosen color palette
    (mild, vibrant, dark, matrix, amber, cyberpunk, monochrome, retro, pastel, nord, gameboy)

Usage (Lego-core style):
    python main.py image photo.jpg -o out.png --palette mild --grid-width 80
    python main.py video clip.mp4 -o out.mp4 --palette matrix --fps 30
    python main.py gif anim.gif -o out.gif --palette cyberpunk

Usage (Original direct style):
    python main.py photo.jpg
    python main.py photo.jpg -o out.png --width 100 --cell 14 --palette mild
    python main.py logo.png --skip-white 20 --strength 0.6
    python main.py photo.jpg --txt
    python main.py clip.mp4 -o out.mp4 --width 120 --fps 15
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from common import (
    VIDEO_EXTS,
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_image,
    grid_from_pil,
    is_video,
    load_grid,
    load_rgb,
    make_active,
)
from config import (
    PAPER,
    RAMPS,
    FPS,
    AsciiConfig,
    Palette,
    Quality,
)
from gif_pipeline import gif_to_ascii_file
from image_pipeline import image_to_ascii, image_to_ascii_file
from palette import PALETTES, get_palette, list_palettes
from quantizer import compute_levels, luminance, pick_indices, quantize_ascii
from resource_limits import (
    MAX_BUFFER_SIZE,
    MAX_WORKERS,
    set_bypass_resource_limits,
)
from tile_renderer import FONT_PATHS, build_glyphs, get_glyphs, load_font, render
from video_pipeline import video_to_ascii_file

# Supported extensions matching lego_core standards
IMAGE_INPUT_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
IMAGE_OUTPUT_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
VIDEO_INPUT_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}
VIDEO_OUTPUT_EXTENSIONS = {
    ".mp4",
}
GIF_INPUT_EXTENSIONS = {
    ".gif",
}
GIF_OUTPUT_EXTENSIONS = {
    ".gif",
}


def default_output_path(
    input_path: Path,
    media_type: str,
) -> Path:
    """Build default output path."""
    output_dir = Path(__file__).resolve().parent / "output"
    suffix = ".mp4" if media_type == "video" else input_path.suffix.lower()
    return output_dir / f"{input_path.stem}_ascii{suffix}"


# ------------------------------------------------------------
# Backwards-compatible conversion API (from original main.py)
# ------------------------------------------------------------


def convert_image(
    path: str | Path,
    out_path: str | Path | None = None,
    width: int = 80,
    height: int | None = None,
    cell: int = 14,
    gap: int = 1,
    strength: float = 0.5,
    ramp: str = "default",
    invert: bool = False,
    contrast: float = 1.15,
    saturation: float = 1.15,
    gamma: float = 1.0,
    skip_white: int = 0,
    auto_levels: bool = True,
    write_txt: bool = False,
    palette: str = "mild",
) -> Path:
    """Convert an image file to an ASCII mosaic (backwards-compatible)."""
    p_in = Path(path)
    p_out = (
        Path(out_path)
        if out_path
        else p_in.with_name(p_in.stem + "_ascii.png")
    )

    config = AsciiConfig(
        grid_width=width,
        grid_height=height,
        tile_size=cell,
        gap=gap,
        palette=Palette(palette.lower()),
        ramp=ramp,
        strength=strength,
        invert=invert,
        contrast=contrast,
        saturation=saturation,
        gamma=gamma,
        skip_white=skip_white,
        auto_levels=auto_levels,
        write_txt=write_txt,
        bypass_limits=True,
    )
    image_to_ascii_file(p_in, p_out, config)
    return p_out


def convert_video(
    path: str | Path,
    out_path: str | Path | None = None,
    width: int = 80,
    height: int | None = None,
    cell: int = 14,
    gap: int = 0,
    strength: float = 0.5,
    ramp: str = "default",
    invert: bool = False,
    contrast: float = 1.15,
    saturation: float = 1.15,
    gamma: float = 1.0,
    skip_white: int = 0,
    auto_levels: bool = True,
    fps: float | None = None,
    start: float = 0.0,
    duration: float | None = None,
    audio: bool = True,
    smooth: float = 0.4,
    quiet: bool = False,
    palette: str = "mild",
    workers: int = 4,
) -> Path:
    """Convert a video file to an ASCII mosaic video (backwards-compatible)."""
    p_in = Path(path)
    p_out = (
        Path(out_path)
        if out_path
        else p_in.with_name(p_in.stem + "_ascii.mp4")
    )

    fps_val = FPS.ORIGINAL
    if fps:
        for f in FPS:
            if f.value == str(int(fps)):
                fps_val = f
                break

    config = AsciiConfig(
        grid_width=width,
        grid_height=height,
        tile_size=cell,
        gap=gap,
        palette=Palette(palette.lower()),
        ramp=ramp,
        strength=strength,
        invert=invert,
        contrast=contrast,
        saturation=saturation,
        gamma=gamma,
        skip_white=skip_white,
        auto_levels=auto_levels,
        fps=fps_val,
        start=start,
        duration=duration,
        audio=audio,
        smooth=smooth,
        workers=workers,
        bypass_limits=True,
    )
    video_to_ascii_file(p_in, p_out, config)
    return p_out


def convert(
    path: str | Path,
    out_path: str | Path | None = None,
    width: int = 80,
    height: int | None = None,
    cell: int = 14,
    gap: int | None = None,
    strength: float = 0.5,
    ramp: str = "default",
    invert: bool = False,
    contrast: float = 1.15,
    saturation: float = 1.15,
    gamma: float = 1.0,
    skip_white: int = 0,
    auto_levels: bool = True,
    write_txt: bool = False,
    fps: float | None = None,
    start: float = 0.0,
    duration: float | None = None,
    audio: bool = True,
    smooth: float = 0.4,
    palette: str = "mild",
) -> Path:
    """Convert an image or video to an ASCII mosaic based on file type."""
    if is_video(path):
        return convert_video(
            path=path,
            out_path=out_path,
            width=width,
            height=height,
            cell=cell,
            gap=0 if gap is None else gap,
            strength=strength,
            ramp=ramp,
            invert=invert,
            contrast=contrast,
            saturation=saturation,
            gamma=gamma,
            skip_white=skip_white,
            auto_levels=auto_levels,
            fps=fps,
            start=start,
            duration=duration,
            audio=audio,
            smooth=smooth,
            palette=palette,
        )
    return convert_image(
        path=path,
        out_path=out_path,
        width=width,
        height=height,
        cell=cell,
        gap=1 if gap is None else gap,
        strength=strength,
        ramp=ramp,
        invert=invert,
        contrast=contrast,
        saturation=saturation,
        gamma=gamma,
        skip_white=skip_white,
        auto_levels=auto_levels,
        write_txt=write_txt,
        palette=palette,
    )


# ------------------------------------------------------------
# CLI Parser: supports both lego_core subcommand and original arguments
# ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert images, videos, and GIFs into color ASCII tile mosaics."
    )

    # First positional argument: either media_type ("image", "video", "gif") or input file path
    parser.add_argument(
        "first_arg",
        metavar="INPUT_OR_MEDIA_TYPE",
        help="Input media type ('image', 'video', 'gif') OR input file path.",
    )

    # Optional second positional: input file path if first_arg was media_type
    parser.add_argument(
        "second_arg",
        nargs="?",
        metavar="INPUT_PATH",
        help="Input media file path (when first argument is media_type).",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path; defaults to output/<input>_ascii.<ext>.",
    )

    parser.add_argument(
        "-w",
        "--width",
        "--grid-width",
        dest="grid_width",
        type=int,
        default=80,
        help="Number of ASCII tiles across output (16-256, default: 80).",
    )

    parser.add_argument(
        "--height",
        "--grid-height",
        dest="grid_height",
        type=int,
        help="Number of ASCII tiles down (default: keep aspect ratio).",
    )

    parser.add_argument(
        "--cell",
        "--tile-size",
        dest="tile_size",
        type=int,
        default=14,
        help="Tile / cell size in pixels (8-32, default: 14).",
    )

    parser.add_argument(
        "--gap",
        type=int,
        default=None,
        help="Gutter between tiles in px (default: 1 for images, 0 for video).",
    )

    parser.add_argument(
        "--palette",
        default=Palette.MILD.value,
        choices=[p.value for p in Palette],
        help=f"Color palette preset ({', '.join(p.value for p in Palette)}). Default: mild.",
    )

    parser.add_argument(
        "--ramp",
        default="default",
        help=f"Character ramp preset ({', '.join(RAMPS)}) or custom dark->light string.",
    )

    parser.add_argument(
        "--quality",
        choices=[q.value for q in Quality],
        default=Quality.HIGH.value,
        help="Quantization quality: standard (fast), high (accurate), maximum (exact).",
    )

    parser.add_argument(
        "--fps",
        choices=[f.value for f in FPS],
        default=FPS.ORIGINAL.value,
        help="Output FPS for video/GIF (default: original).",
    )

    parser.add_argument(
        "--strength",
        type=float,
        default=0.5,
        help="Background color strength 0..1 (0 = plain paper, 1 = full saturation).",
    )

    parser.add_argument(
        "--invert",
        action="store_true",
        help="Invert dark/light character mapping.",
    )

    parser.add_argument("--contrast", type=float, default=1.15)
    parser.add_argument("--saturation", type=float, default=1.15)
    parser.add_argument("--gamma", type=float, default=1.0, help=">1 brightens midtones.")
    parser.add_argument(
        "--skip-white",
        type=int,
        default=0,
        metavar="TOL",
        help="Leave near-white background empty (try 12-30).",
    )
    parser.add_argument(
        "--no-auto-levels",
        action="store_true",
        help="Disable automatic percentile contrast stretching.",
    )
    parser.add_argument(
        "--txt",
        dest="write_txt",
        action="store_true",
        help="Also write a plain-text .txt version (images only).",
    )

    # Video options
    v = parser.add_argument_group("video options")
    v.add_argument("--start", type=float, default=0.0, help="Start time in seconds.")
    v.add_argument("--duration", type=float, help="Seconds to convert (default: entire video).")
    v.add_argument(
        "--smooth",
        type=float,
        default=0.4,
        help="Temporal smoothing 0..0.9 to reduce shimmer (default: 0.4).",
    )
    v.add_argument("--no-audio", action="store_true", help="Do not copy audio from source.")
    v.add_argument(
        "--workers",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help=f"Parallel video-processing workers (1-{MAX_WORKERS}, default: 4).",
    )
    v.add_argument(
        "--buffer-size",
        type=int,
        default=8,
        help=f"Video frame queue buffer size (1-{MAX_BUFFER_SIZE}, default: 8).",
    )
    v.add_argument(
        "--bitrate-mbps",
        type=float,
        help="Target video bitrate in Mbps (default: auto).",
    )

    # Force / bypass limits
    parser.add_argument(
        "-f",
        "--force",
        "--bypass",
        "--bypass-limits",
        dest="force",
        action="store_true",
        help="Bypass resource limits and execute anyway.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Determine whether first_arg was media_type or input file
    first = args.first_arg
    second = args.second_arg

    if first.lower() in ("image", "video", "gif"):
        if not second:
            parser.error(f"Input file path required after media type '{first}'")
        media_type = first.lower()
        input_path = Path(second)
    else:
        input_path = Path(first)
        # Auto-detect media type
        suffix = input_path.suffix.lower()
        if suffix in VIDEO_INPUT_EXTENSIONS:
            media_type = "video"
        elif suffix in GIF_INPUT_EXTENSIONS:
            media_type = "gif"
        else:
            media_type = "image"

    if args.force:
        set_bypass_resource_limits(True)
        Image.MAX_IMAGE_PIXELS = None

    if not input_path.is_file():
        parser.error(f"Input file does not exist: {input_path}")

    output_path = args.output or default_output_path(input_path, media_type)

    if not output_path.suffix:
        parser.error("Output path must include a file extension.")

    if input_path.resolve() == output_path.resolve():
        parser.error("Input and output paths must be different.")

    try:
        config = AsciiConfig(
            grid_width=args.grid_width,
            grid_height=args.grid_height,
            tile_size=args.tile_size,
            gap=args.gap,
            palette=Palette(args.palette.lower()),
            ramp=args.ramp,
            quality=Quality(args.quality.lower()),
            fps=FPS(args.fps),
            strength=args.strength,
            contrast=args.contrast,
            saturation=args.saturation,
            gamma=args.gamma,
            skip_white=args.skip_white,
            auto_levels=not args.no_auto_levels,
            invert=args.invert,
            smooth=args.smooth,
            audio=not args.no_audio,
            start=args.start,
            duration=args.duration,
            write_txt=args.write_txt,
            workers=args.workers,
            buffer_size=args.buffer_size,
            bitrate_mbps=args.bitrate_mbps,
            bypass_limits=args.force,
        )
    except ValueError as exc:
        parser.error(str(exc))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if media_type == "image":
            image_to_ascii_file(input_path, output_path, config)
        elif media_type == "video":
            video_to_ascii_file(input_path, output_path, config)
        else:
            gif_to_ascii_file(input_path, output_path, config)
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(f"Saved ASCII mosaic: {output_path}")


if __name__ == "__main__":
    main()
