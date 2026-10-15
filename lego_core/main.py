import argparse
import os
from pathlib import Path

from config import MosaicConfig
from gif_pipeline import gif_to_mosaic_file
from image_pipeline import image_to_mosaic_file
from tile_renderer import build_atlas
from video_pipeline import video_to_mosaic_file

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm"}
GIF_EXTENSIONS = {".gif"}


def default_output_path(input_path: Path) -> Path:
    """Build the default output path inside the project's output directory."""
    output_dir = Path(__file__).resolve().parent / "output"
    return output_dir / f"{input_path.stem}_lego{input_path.suffix}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert images, videos, and GIFs into LEGO mosaics."
    )
    parser.add_argument(
        "media_type",
        choices=("image", "video", "gif"),
        help="Input media type.",
    )
    parser.add_argument("input", type=Path, help="Input media path.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path; defaults to output/<input>_lego.<extension>.",
    )
    parser.add_argument(
        "--grid-width",
        type=int,
        default=64,
        help="Number of LEGO tiles across the output (default: 64).",
    )
    parser.add_argument(
        "--tile-size",
        type=int,
        default=16,
        help="Rendered pixels per LEGO tile (default: 16).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(4, os.cpu_count() or 1),
        help="Parallel video-processing workers (default: up to 4).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_path: Path = args.input
    if not input_path.is_file():
        parser.error(f"input file does not exist: {input_path}")

    output_path: Path = args.output or default_output_path(input_path)
    if not output_path.suffix:
        parser.error("output path must include a file extension")
    if input_path.resolve() == output_path.resolve():
        parser.error("input and output paths must be different")

    supported_by_type = {
        "image": IMAGE_EXTENSIONS,
        "video": VIDEO_EXTENSIONS,
        "gif": GIF_EXTENSIONS,
    }
    supported_extensions = supported_by_type[args.media_type]

    if input_path.suffix.lower() not in supported_extensions:
        parser.error(
            f"'{input_path.suffix}' is not a supported {args.media_type} extension"
        )
    if output_path.suffix.lower() not in supported_extensions:
        parser.error(f"output extension must be supported for {args.media_type} files")
    if args.media_type == "video" and args.workers < 1:
        parser.error("--workers must be positive")

    try:
        config = MosaicConfig(
            grid_width=args.grid_width,
            tile_size=args.tile_size,
        )
    except ValueError as exc:
        parser.error(str(exc))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    atlas = build_atlas(config.tile_size)

    try:
        if args.media_type == "image":
            image_to_mosaic_file(input_path, output_path, config, atlas)
        elif args.media_type == "video":
            video_to_mosaic_file(
                input_path,
                output_path,
                config,
                atlas,
                workers=args.workers,
            )
        else:
            gif_to_mosaic_file(input_path, output_path, config, atlas)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(f"Saved LEGO mosaic: {output_path}")


if __name__ == "__main__":
    main()
