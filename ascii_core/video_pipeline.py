from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageEnhance

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_frame,
    make_active,
    resolve_output_fps,
)
from config import RAMPS, AsciiConfig
from cost_estimator import estimate_video_cost, select_bitrate_bps
from quantizer import quantize_ascii, sample_video_levels
from resource_limits import (
    MAX_VIDEO_DURATION_SECONDS,
    ResourceLimitError,
    validate_buffer_size,
    validate_input_size,
    validate_output_resolution,
    validate_output_size,
    validate_processing_units,
    validate_video_duration,
    validate_video_fps,
    validate_workers,
)
from tile_renderer import get_glyphs, render_ascii_tiles


def _put_while_running(
    target: Queue,
    item: object,
    stop_event: Event,
) -> bool:
    """Put an item into a bounded queue unless processing has stopped."""
    while not stop_event.is_set():
        try:
            target.put(item, timeout=0.1)
            return True
        except Full:
            continue
    return False


def _reader(
    capture: cv2.VideoCapture,
    first_frame: np.ndarray,
    grid_size: tuple[int, int],
    frame_queue: Queue,
    stop_event: Event,
    errors: list[BaseException],
    source_fps: float,
    output_fps: float,
    start_frame: int = 0,
    end_frame: int = 10**9,
    bypass_limits: bool = False,
) -> None:
    """
    Decode and downscale source frames, skipping frames as necessary to match output_fps.
    Downscales to the small grid in the reader thread to keep memory usage minimal.
    """
    frame_index = 0
    output_index = 0
    max_frames = int(MAX_VIDEO_DURATION_SECONDS * source_fps * 1.05)

    step = 1.0 / output_fps
    next_t = 0.0

    try:
        current_frame = first_frame
        while not stop_event.is_set():
            if not bypass_limits and frame_index > max_frames:
                raise ResourceLimitError(
                    f"Video exceeds maximum allowed duration ({MAX_VIDEO_DURATION_SECONDS:.0f}s)."
                )

            if frame_index >= start_frame and frame_index < end_frame:
                t = (frame_index - start_frame) / source_fps
                if t + 1e-6 >= next_t:
                    next_t += step
                    # Downscale to grid size
                    small_bgr = downscale_frame(current_frame, grid_size)
                    if not _put_while_running(
                        frame_queue, (output_index, small_bgr), stop_event
                    ):
                        break
                    output_index += 1

            frame_index += 1
            if frame_index >= end_frame:
                break

            ok, frame = capture.read()
            if not ok or frame is None:
                break
            current_frame = frame

    except BaseException as exc:
        errors.append(exc)
        stop_event.set()
    finally:
        _put_while_running(frame_queue, None, stop_event)


def _process_frame_payload(
    small_bgr: np.ndarray,
    config: AsciiConfig,
    ramp_str: str,
    glyphs: np.ndarray,
    levels: tuple[float, float] | None,
) -> np.ndarray:
    """Process a single downscaled BGR frame into a rendered ASCII mosaic frame."""
    # Convert BGR to RGB float32
    rgb = small_bgr[..., ::-1].astype(np.float32)

    # Optional enhancements
    if config.contrast != 1.0 or config.saturation != 1.0:
        pil_img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
        if config.contrast != 1.0:
            pil_img = ImageEnhance.Contrast(pil_img).enhance(config.contrast)
        if config.saturation != 1.0:
            pil_img = ImageEnhance.Color(pil_img).enhance(config.saturation)
        rgb = np.asarray(pil_img, dtype=np.float32)

    if config.gamma != 1.0:
        rgb = 255.0 * (rgb / 255.0) ** (1.0 / config.gamma)

    alpha = np.ones((rgb.shape[0], rgb.shape[1]), dtype=np.float32)
    active = make_active(alpha, rgb, config.skip_white)

    _, idx, _ = quantize_ascii(
        rgb,
        len(ramp_str),
        invert=config.invert,
        auto_levels=False,
        levels=levels,
        quality=config.quality,
    )

    return render_ascii_tiles(
        rgb=rgb,
        idx=idx,
        active=active,
        glyphs=glyphs,
        config=config,
        even=True,
    )


def video_to_ascii_file(
    input_path: str | Path,
    output_path: str | Path,
    config: AsciiConfig,
) -> None:
    """Convert a video file into an ASCII mosaic MP4 video using multi-threaded execution."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input video does not exist: {input_path}")

    validate_input_size(input_path.stat().st_size, bypass=config.bypass_limits)

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    validate_workers(config.workers, bypass=config.bypass_limits)
    validate_buffer_size(config.buffer_size, bypass=config.bypass_limits)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {input_path}")

    try:
        source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        if source_fps <= 0:
            source_fps = 30.0

        validate_video_fps(source_fps, bypass=config.bypass_limits)

        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        start_frame = max(0, int(round(config.start * source_fps)))
        end_frame = n_frames if n_frames > 0 else 10**9
        if config.duration is not None:
            end_frame = min(end_frame, start_frame + int(round(config.duration * source_fps)))

        dur_sec = (end_frame - start_frame) / source_fps if n_frames > 0 else 10.0
        validate_video_duration(dur_sec, bypass=config.bypass_limits)

        out_fps = resolve_output_fps(config.fps, source_fps)
        if config.fps != config.fps.ORIGINAL and float(config.fps.value) > source_fps:
            out_fps = source_fps

        grid_w, grid_h = calculate_grid_dimensions(config.grid_width, source_w, source_h)
        if config.grid_height is not None:
            grid_h = config.grid_height

        out_w, out_h = calculate_output_dimensions(
            config.grid_width, config.tile_size, source_w, source_h
        )
        # Ensure even output dimensions for video codecs
        out_w += out_w % 2
        out_h += out_h % 2

        validate_output_resolution(out_w, out_h, bypass=config.bypass_limits)

        estimate = estimate_video_cost(
            config, source_w, source_h, source_fps, n_frames, dur_sec
        )
        validate_processing_units(estimate.processing_units, bypass=config.bypass_limits)

        ramp_str = RAMPS.get(config.ramp, config.ramp)
        gap = 0 if config.gap is None else config.gap
        glyphs = get_glyphs(ramp_str, config.tile_size, gap, config.font_scale)

        levels = None
        if config.auto_levels:
            levels = sample_video_levels(
                cv2,
                cap,
                start_frame,
                end_frame,
                grid_w,
                grid_h,
                config.contrast,
                config.saturation,
                config.gamma,
            )

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        ret, first_frame = cap.read()
        if not ret or first_frame is None:
            raise RuntimeError("Could not decode first video frame.")

    except Exception:
        cap.release()
        raise

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = shutil.which("ffmpeg")
    silent_path = output_path.with_name(f"{output_path.stem}_silent.mp4")

    ffmpeg_proc = None
    cv_writer = None

    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{out_w}x{out_h}",
            "-r",
            f"{out_fps:.6f}",
            "-i",
            "-",
        ]
        if config.audio:
            if config.start > 0:
                cmd += ["-ss", f"{config.start:.3f}"]
            if config.duration is not None:
                cmd += ["-t", f"{config.duration:.3f}"]
            cmd += ["-i", str(input_path)]
            cmd += ["-map", "0:v:0", "-map", "1:a:0?", "-c:a", "aac", "-shortest"]
        else:
            cmd += ["-map", "0:v:0"]

        cmd += [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "14",
            "-preset",
            "medium",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        ffmpeg_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    else:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        cv_writer = cv2.VideoWriter(str(silent_path), fourcc, out_fps, (out_w, out_h))
        if not cv_writer.isOpened():
            cap.release()
            raise RuntimeError("Could not open OpenCV VideoWriter (mp4v codec unavailable).")

    frame_queue: Queue = Queue(maxsize=config.buffer_size)
    stop_event = Event()
    errors: list[BaseException] = []

    reader_thread = Thread(
        target=_reader,
        args=(
            cap,
            first_frame,
            (grid_w, grid_h),
            frame_queue,
            stop_event,
            errors,
            source_fps,
            out_fps,
            start_frame,
            end_frame,
            config.bypass_limits,
        ),
        daemon=True,
    )
    reader_thread.start()

    pending_futures: deque[tuple[int, Future]] = deque()
    next_write_idx = 0
    written_frames = 0
    prev_rgb: np.ndarray | None = None

    try:
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            while True:
                # Dispatch tasks from queue
                while len(pending_futures) < config.buffer_size:
                    try:
                        item = frame_queue.get(timeout=0.05)
                    except Empty:
                        break

                    if item is None:
                        frame_queue.put(None)  # Put sentinel back
                        break

                    slot_idx, small_bgr = item
                    # Temporal smoothing on the downscaled frame if requested
                    if config.smooth > 0 and prev_rgb is not None:
                        rgb_f = small_bgr[..., ::-1].astype(np.float32)
                        rgb_f = prev_rgb * config.smooth + rgb_f * (1.0 - config.smooth)
                        small_bgr = rgb_f[..., ::-1].astype(np.uint8)
                    prev_rgb = small_bgr[..., ::-1].astype(np.float32)

                    fut = executor.submit(
                        _process_frame_payload,
                        small_bgr,
                        config,
                        ramp_str,
                        glyphs,
                        levels,
                    )
                    pending_futures.append((slot_idx, fut))

                if errors:
                    raise errors[0]

                # Drain in order
                while pending_futures and pending_futures[0][0] == next_write_idx:
                    _, fut = pending_futures.popleft()
                    rendered_rgb = fut.result()

                    if ffmpeg_proc is not None and ffmpeg_proc.stdin:
                        ffmpeg_proc.stdin.write(np.ascontiguousarray(rendered_rgb).tobytes())
                    elif cv_writer is not None:
                        cv_writer.write(rendered_rgb[:, :, ::-1])

                    written_frames += 1
                    next_write_idx += 1

                # Check if done
                if not reader_thread.is_alive() and not pending_futures and frame_queue.empty():
                    break

    except BaseException:
        stop_event.set()
        if ffmpeg_proc is not None:
            try:
                ffmpeg_proc.kill()
            except Exception:
                pass
        if cv_writer is not None:
            cv_writer.release()
        output_path.unlink(missing_ok=True)
        silent_path.unlink(missing_ok=True)
        raise
    finally:
        cap.release()
        reader_thread.join(timeout=2.0)

    if ffmpeg_proc is not None:
        if ffmpeg_proc.stdin:
            ffmpeg_proc.stdin.close()
        code = ffmpeg_proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg encoding failed with exit code {code}")
    else:
        if cv_writer is not None:
            cv_writer.release()
        silent_path.replace(output_path)

    if written_frames == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("No frames were processed from video.")

    try:
        validate_output_size(output_path.stat().st_size, bypass=config.bypass_limits)
    except ResourceLimitError:
        output_path.unlink(missing_ok=True)
        raise
