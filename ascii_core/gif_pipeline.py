from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_image,
    make_active,
    normalize_gif_delay,
)
from config import FPS, RAMPS, AsciiConfig
from cost_estimator import estimate_gif_cost
from quantizer import quantize_ascii
from resource_limits import (
    ResourceLimitError,
    validate_gif_duration,
    validate_gif_frames,
    validate_input_size,
    validate_output_resolution,
    validate_output_size,
    validate_processing_units,
)
from tile_renderer import get_glyphs, render_ascii_tiles


def gif_to_ascii_file(
    input_path: str | Path,
    output_path: str | Path,
    config: AsciiConfig,
) -> None:
    """Convert an animated GIF into an ASCII mosaic animated GIF."""
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
        raise ValueError("60 FPS is not supported for GIF output.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(input_path) as source:
        if source.format != "GIF":
            raise ValueError(f"Input file is not a valid GIF: {input_path}")

        loop = source.info.get("loop", 0)
        n_frames = getattr(source, "n_frames", 1)

        validate_gif_frames(n_frames, bypass=config.bypass_limits)

        # Probe durations by seeking
        source_durations: list[int] = []
        total_duration_ms = 0
        for frame_idx in range(n_frames):
            source.seek(frame_idx)
            delay = normalize_gif_delay(source.info.get("duration"))
            source_durations.append(delay)
            total_duration_ms += delay
            validate_gif_duration(total_duration_ms / 1000.0, bypass=config.bypass_limits)

        source_w, source_h = source.size
        output_w, output_h = calculate_output_dimensions(
            config.grid_width, config.tile_size, source_w, source_h
        )
        validate_output_resolution(output_w, output_h, bypass=config.bypass_limits)

        estimate = estimate_gif_cost(
            config, source_w, source_h, n_frames, total_duration_ms / 1000.0
        )
        validate_processing_units(estimate.processing_units, bypass=config.bypass_limits)

        grid_w, grid_h = calculate_grid_dimensions(
            config.grid_width, source_w, source_h
        )
        if config.grid_height is not None:
            grid_h = config.grid_height

        ramp_str = RAMPS.get(config.ramp, config.ramp)
        gap = 0 if config.gap is None else config.gap
        glyphs = get_glyphs(ramp_str, config.tile_size, gap, config.font_scale)

        # Pre-sample brightness across frames to avoid luminance flicker
        lums: list[np.ndarray] = []
        sample_indices = np.unique(np.linspace(0, n_frames - 1, min(24, n_frames)).astype(int))
        for s_idx in sample_indices:
            source.seek(int(s_idx))
            f_frame = source.convert("RGBA")
            s_small = downscale_image(f_frame, (grid_w, grid_h)).convert("RGB")
            s_rgb = np.asarray(s_small, dtype=np.float32)
            lums.append(s_rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32).ravel())

        from quantizer import compute_levels
        levels = compute_levels(np.concatenate(lums)) if (config.auto_levels and lums) else None

        rendered_frames: list[Image.Image] = []
        prev_rgb: np.ndarray | None = None

        for frame_idx in range(n_frames):
            source.seek(frame_idx)
            frame_rgba = source.convert("RGBA")
            small = downscale_image(frame_rgba, (grid_w, grid_h))
            rgb_img = small.convert("RGB")
            alpha = np.asarray(small.getchannel("A"), dtype=np.float32) / 255.0

            if config.contrast != 1.0:
                rgb_img = ImageEnhance.Contrast(rgb_img).enhance(config.contrast)
            if config.saturation != 1.0:
                rgb_img = ImageEnhance.Color(rgb_img).enhance(config.saturation)

            rgb = np.asarray(rgb_img, dtype=np.float32)
            if config.gamma != 1.0:
                rgb = 255.0 * (rgb / 255.0) ** (1.0 / config.gamma)

            if config.smooth > 0 and prev_rgb is not None:
                rgb = prev_rgb * config.smooth + rgb * (1.0 - config.smooth)
            prev_rgb = rgb

            _, idx, _ = quantize_ascii(
                rgb,
                len(ramp_str),
                invert=config.invert,
                auto_levels=False,
                levels=levels,
                quality=config.quality,
            )
            active = make_active(alpha, rgb, config.skip_white)

            mosaic_arr = render_ascii_tiles(
                rgb=rgb,
                idx=idx,
                active=active,
                glyphs=glyphs,
                config=config,
                even=False,
            )
            frame_out = Image.fromarray(mosaic_arr).convert("P", palette=Image.Palette.ADAPTIVE)
            rendered_frames.append(frame_out)

    if not rendered_frames:
        raise ValueError("No frames were extracted from GIF.")

    # Save output GIF
    first = rendered_frames[0]
    rest = rendered_frames[1:]
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        duration=source_durations,
        loop=loop,
        disposal=2,
    )

    try:
        validate_output_size(output_path.stat().st_size, bypass=config.bypass_limits)
    except ResourceLimitError:
        output_path.unlink(missing_ok=True)
        raise
