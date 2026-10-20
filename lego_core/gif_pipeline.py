from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_image,
    load_rgb,
    normalize_gif_delay,
)
from config import FPS, MosaicConfig
from cost_estimator import estimate_gif_cost
from quantizer import quantize_rgb
from resource_limits import (
    ResourceLimitError,
    validate_gif_duration,
    validate_gif_frames,
    validate_input_size,
    validate_output_resolution,
    validate_output_size,
    validate_processing_units,
)
from tile_renderer import get_atlas, render_indices


def gif_to_mosaic_file(
    input_path: str | Path,
    output_path: str | Path,
    config: MosaicConfig,
) -> None:
    """Convert an animated GIF into a LEGO-style animated GIF."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input GIF does not exist: {input_path}")

    validate_input_size(input_path.stat().st_size, bypass=config.bypass_limits)

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    if input_path.suffix and input_path.suffix.lower() != ".gif":
        raise ValueError("Input file must have a .gif extension.")

    if output_path.suffix.lower() != ".gif":
        raise ValueError("Output file must have a .gif extension.")

    if config.fps == FPS.FPS_60:
        raise ValueError(
            "60 FPS is not supported for GIF output (GIF timing resolution cannot "
            "represent 60 FPS accurately; browser timing clamps to 100ms or 50ms)."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        if source.format != "GIF":
            raise ValueError(f"Input file is not a valid GIF: {input_path}")

        loop = source.info.get("loop", 0)
        n_frames = getattr(source, "n_frames", 1)

        # Enforce frame count limit upfront before decoding frames
        validate_gif_frames(n_frames, bypass=config.bypass_limits)

        # Probe durations by seeking without decoding pixel buffers
        source_durations: list[int] = []
        total_duration_ms = 0

        for frame_idx in range(n_frames):
            source.seek(frame_idx)
            delay = normalize_gif_delay(source.info.get("duration"))
            source_durations.append(delay)
            total_duration_ms += delay
            # Fail early if accumulated duration exceeds limit
            validate_gif_duration(total_duration_ms / 1000.0, bypass=config.bypass_limits)

        source.seek(0)
        total_duration_sec = total_duration_ms / 1000.0
        validate_gif_duration(total_duration_sec, bypass=config.bypass_limits)

        orig_w, orig_h = source.size
        output_w, output_h = calculate_output_dimensions(
            config.grid_width, config.tile_size, orig_w, orig_h
        )
        validate_output_resolution(output_w, output_h, bypass=config.bypass_limits)

        estimate = estimate_gif_cost(
            config, orig_w, orig_h, n_frames, total_duration_sec
        )
        validate_processing_units(estimate.processing_units, bypass=config.bypass_limits)

        # Frame mapping & timing accumulator
        target_fps = None if config.fps == FPS.ORIGINAL else float(config.fps.val)
        if target_fps is None:
            selected_source_indices = list(range(n_frames))
            selected_durations = source_durations
        else:
            # Resample frames using accumulated timestamps in centisecond steps
            target_frame_count = max(1, int(round(total_duration_sec * target_fps)))
            validate_gif_frames(target_frame_count, bypass=config.bypass_limits)

            selected_source_indices = []
            selected_durations = []
            curr_target_time = 0.0

            for out_idx in range(target_frame_count):
                target_ms = out_idx * (1000.0 / target_fps)
                next_target_ms = (out_idx + 1) * (1000.0 / target_fps)

                # Find matching source frame
                elapsed = 0
                chosen_idx = 0
                for s_idx, d_ms in enumerate(source_durations):
                    if target_ms < elapsed + d_ms:
                        chosen_idx = s_idx
                        break
                    elapsed += d_ms
                selected_source_indices.append(chosen_idx)

                # Quantize frame delay to 10ms multiples using error accumulator
                step_ms = max(20, int(round((next_target_ms - target_ms) / 10.0)) * 10)
                selected_durations.append(step_ms)

        # Rendering mosaic frames with caching per source index
        grid_w, grid_h = calculate_grid_dimensions(config.grid_width, orig_w, orig_h)
        atlas = get_atlas(config.palette, config.tile_size)

        mosaic_cache: dict[int, Image.Image] = {}
        used_indices: set[int] = set()
        rendered_mosaics: list[Image.Image] = []

        for src_idx in selected_source_indices:
            if src_idx not in mosaic_cache:
                source.seek(src_idx)
                rgb_frame = load_rgb(source)
                small_img = downscale_image(rgb_frame, (grid_w, grid_h))
                small_rgb = np.asarray(small_img, dtype=np.uint8)

                idx_grid = quantize_rgb(small_rgb, config.palette, config.quality)
                used_indices.update(np.unique(idx_grid).tolist())

                mosaic_rgb = render_indices(idx_grid, atlas)
                mosaic_cache[src_idx] = Image.fromarray(mosaic_rgb)

            rendered_mosaics.append(mosaic_cache[src_idx])

        # Global palette across all frames
        sorted_indices = sorted(used_indices) if used_indices else [0]
        tiles_strip = np.concatenate([atlas[i] for i in sorted_indices], axis=0)
        global_palette_img = Image.fromarray(tiles_strip).quantize(
            colors=256, method=Image.Quantize.MEDIANCUT
        )

        final_frames: list[Image.Image] = [
            mosaic.quantize(palette=global_palette_img, dither=Image.Dither.NONE)
            for mosaic in rendered_mosaics
        ]

    # Save output GIF
    save_options = {
        "format": "GIF",
        "save_all": True,
        "append_images": final_frames[1:],
        "duration": selected_durations,
        "disposal": 2,
        "optimize": False,
    }
    if loop is not None:
        save_options["loop"] = loop

    final_frames[0].save(output_path, **save_options)

    # Validate output size and delete if oversized
    try:
        validate_output_size(output_path.stat().st_size, bypass=config.bypass_limits)
    except ResourceLimitError:
        output_path.unlink(missing_ok=True)
        raise
