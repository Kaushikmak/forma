from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from PIL import Image

from config import FPS, MosaicConfig, Palette, Quality
from resource_limits import MAX_BUFFER_SIZE, MAX_WORKERS

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
    """Build the default output path."""
    output_dir = Path(__file__).resolve().parent / "output"
    suffix = ".mp4" if media_type == "video" else input_path.suffix.lower()
    return output_dir / f"{input_path.stem}_lego{suffix}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert images, videos, and GIFs into LEGO mosaics."
    )

    parser.add_argument(
        "media_type",
        choices=(
            "image",
            "video",
            "gif",
        ),
        help="Input media type.",
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input media path.",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path; defaults to output/<input>_lego.<extension> (.mp4 for video).",
    )

    parser.add_argument(
        "--grid-width",
        type=int,
        default=64,
        help="Number of LEGO tiles across the output (16-256, default: 64).",
    )

    parser.add_argument(
        "--tile-size",
        type=int,
        default=16,
        help="Rendered pixels per LEGO tile (8-32, default: 16).",
    )

    parser.add_argument(
        "--palette",
        choices=[p.value for p in Palette],
        default=Palette.CLASSIC.value,
        help="LEGO color palette (classic: curated solid colors; extended: all colors).",
    )

    parser.add_argument(
        "--quality",
        choices=[q.value for q in Quality],
        default=Quality.HIGH.value,
        help="Color quantization quality: standard (fast LUT), high (accurate LUT), maximum (exact LAB).",
    )

    parser.add_argument(
        "--fps",
        choices=[f.value for f in FPS],
        default=FPS.ORIGINAL.value,
        help="Output FPS for video/GIF (default: original; 60 is only valid for video).",
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help=f"Parallel video-processing workers (1-{MAX_WORKERS}, default: up to 4).",
    )

    parser.add_argument(
        "--buffer-size",
        type=int,
        default=8,
        help=f"Video frame queue buffer size (1-{MAX_BUFFER_SIZE}, default: 8).",
    )

    parser.add_argument(
        "--bitrate-mbps",
        type=float,
        help=(
            "Target video bitrate in Mbps. If omitted, bitrate is auto-selected "
            "based on resolution/quality and capped to stay within the 50 MiB limit."
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_path: Path = args.input

    if not input_path.is_file():
        parser.error(f"input file does not exist: {input_path}")

    # Pass media_type so default output for video inputs (.mov, .mkv, etc.) is .mp4
    output_path = args.output or default_output_path(input_path, args.media_type)

    if not output_path.suffix:
        parser.error("output path must include a file extension")

    if input_path.resolve() == output_path.resolve():
        parser.error("input and output paths must be different")

    supported_inputs = {
        "image": IMAGE_INPUT_EXTENSIONS,
        "video": VIDEO_INPUT_EXTENSIONS,
        "gif": GIF_INPUT_EXTENSIONS,
    }
    supported_outputs = {
        "image": IMAGE_OUTPUT_EXTENSIONS,
        "video": VIDEO_OUTPUT_EXTENSIONS,
        "gif": GIF_OUTPUT_EXTENSIONS,
    }

    if input_path.suffix.lower() not in supported_inputs[args.media_type]:
        parser.error(
            f"'{input_path.suffix}' is not a supported input extension for {args.media_type}"
        )

    # Strictly validate output extensions (e.g. video only allows .mp4)
    if output_path.suffix.lower() not in supported_outputs[args.media_type]:
        parser.error(
            f"'{output_path.suffix}' is not a valid output extension for {args.media_type} files. "
            f"Supported: {sorted(supported_outputs[args.media_type])}"
        )

    if args.workers < 1 or args.workers > MAX_WORKERS:
        parser.error(f"--workers must be between 1 and {MAX_WORKERS}")

    if args.buffer_size < 1 or args.buffer_size > MAX_BUFFER_SIZE:
        parser.error(f"--buffer-size must be between 1 and {MAX_BUFFER_SIZE}")

    if args.media_type != "video" and args.bitrate_mbps is not None:
        parser.error("--bitrate-mbps is only supported for video files")

    if args.media_type == "image" and args.fps != FPS.ORIGINAL.value:
        parser.error("--fps is only supported for video and GIF files")

    if args.media_type == "gif" and args.fps == FPS.FPS_60.value:
        parser.error("--fps 60 is not supported for GIF files")

    try:
        config = MosaicConfig(
            grid_width=args.grid_width,
            tile_size=args.tile_size,
            palette=Palette(args.palette),
            fps=FPS(args.fps),
            quality=Quality(args.quality),
            workers=args.workers,
            buffer_size=args.buffer_size,
            bitrate_mbps=args.bitrate_mbps,
        )
    except ValueError as exc:
        parser.error(str(exc))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Catch cv2.error if cv2 is available
    cv2_error = ()
    try:
        import cv2
        cv2_error = (cv2.error,)
    except ImportError:
        pass

    try:
        if args.media_type == "image":
            # Lazy import image pipeline
            from image_pipeline import image_to_mosaic_file

            image_to_mosaic_file(
                input_path,
                output_path,
                config,
            )

        elif args.media_type == "video":
            # Lazy import video pipeline
            from video_pipeline import video_to_mosaic_file

            video_to_mosaic_file(
                input_path,
                output_path,
                config,
            )

        else:
            # Lazy import gif pipeline
            from gif_pipeline import gif_to_mosaic_file

            gif_to_mosaic_file(
                input_path,
                output_path,
                config,
            )

    except (
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        Image.DecompressionBombError,
        *cv2_error,
    ) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(f"Saved LEGO mosaic: {output_path}")


if __name__ == "__main__":
    main()
