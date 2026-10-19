from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
import os
import shutil
import subprocess

import cv2
import numpy as np

from common import (
    calculate_grid_dimensions,
    calculate_output_dimensions,
    downscale_frame,
    resolve_output_fps,
)
from config import MosaicConfig
from cost_estimator import estimate_video_cost, select_bitrate_bps
from quantizer import prewarm_quantizer, quantize_rgb
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
from tile_renderer import get_atlas, render_indices


def process_small_frame(
    small_bgr: np.ndarray,
    config: MosaicConfig,
    atlas_bgr: np.ndarray,
) -> np.ndarray:
    """Convert a downscaled BGR frame into a rendered LEGO mosaic frame."""
    indices = quantize_rgb(
        small_bgr[..., ::-1],
        config.palette,
        config.quality,
    )
    return render_indices(
        indices,
        atlas_bgr,
    )


def _put_while_running(
    target: Queue,
    item: object,
    stop_event: Event,
) -> bool:
    """Put an item into a bounded queue unless processing has stopped."""
    while not stop_event.is_set():
        try:
            target.put(
                item,
                timeout=0.1,
            )
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
    bypass_limits: bool = False,
) -> None:
    """
    Decode and downscale source frames, assigning each to output frame slots.
    Downscales to the small grid in the reader thread to dramatically reduce memory.
    """
    frame_index = 0
    output_index = 0
    max_frames = int(MAX_VIDEO_DURATION_SECONDS * source_fps * 1.05)

    try:
        current_frame = first_frame
        while not stop_event.is_set():
            if not bypass_limits and frame_index > max_frames:
                raise ResourceLimitError(
                    f"Video exceeds maximum allowed duration "
                    f"({MAX_VIDEO_DURATION_SECONDS:.0f} seconds)."
                )

            #float precision epsilon prevents frame dropping/duplication drift
            next_output_index = int(((frame_index + 1) * output_fps) / source_fps + 1e-9)
            repeat_count = max(0, next_output_index - output_index)

            if repeat_count > 0:
                # Downscale to small grid inside reader to keep queue memory minimal
                small_bgr = downscale_frame(current_frame, grid_size)
                if not _put_while_running(
                    frame_queue,
                    (frame_index, small_bgr, repeat_count),
                    stop_event,
                ):
                    return
                output_index += repeat_count

            frame_index += 1
            success, next_frame = capture.read()
            if not success or next_frame is None:
                break
            current_frame = next_frame

    except BaseException as exc:
        errors.append(exc)
        stop_event.set()

    finally:
        _put_while_running(
            frame_queue,
            None,
            stop_event,
        )


def _writer(
    output_queue: Queue,
    tmp_path: Path,
    fps: float,
    stop_event: Event,
    state: dict[str, int],
    errors: list[BaseException],
    bitrate_bps: int,
) -> None:
    """Encode processed frames with FFmpeg in queue order."""
    process: subprocess.Popen[bytes] | None = None

    try:
        while not stop_event.is_set():
            try:
                item = output_queue.get(timeout=0.1)
            except Empty:
                continue

            if item is None:
                break

            _, frame, repeat_count = item

            if process is None:
                height, width = frame.shape[:2]
                if width % 2:
                    width += 1
                if height % 2:
                    height += 1

                command = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "bgr24",
                    "-s",
                    f"{width}x{height}",
                    "-r",
                    str(fps),
                    "-i",
                    "-",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-tune",
                    "animation",
                    "-b:v",
                    str(bitrate_bps),
                    "-maxrate",
                    str(bitrate_bps),
                    "-bufsize",
                    str(bitrate_bps * 2),
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(tmp_path),
                ]

                try:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.PIPE,
                    )
                except FileNotFoundError as exc:
                    raise RuntimeError(
                        "FFmpeg is required for video encoding but was not found."
                    ) from exc

                state["width"] = width
                state["height"] = height

            if frame.shape[1] != state["width"] or frame.shape[0] != state["height"]:
                frame = cv2.copyMakeBorder(
                    frame,
                    0,
                    state["height"] - frame.shape[0],
                    0,
                    state["width"] - frame.shape[1],
                    cv2.BORDER_CONSTANT,
                    value=(255, 255, 255),
                )

            raw_frame = frame.tobytes()

            for _ in range(repeat_count):
                if process.stdin is None:
                    raise RuntimeError("FFmpeg encoder stdin is unavailable.")
                process.stdin.write(raw_frame)
                state["frames_written"] += 1

    except BaseException as exc:
        errors.append(exc)
        stop_event.set()

    finally:
        if process is not None:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass

            return_code = process.wait()
            if return_code != 0 and not errors:
                errors.append(
                    RuntimeError(
                        f"FFmpeg video encoder exited with code {return_code}."
                    )
                )
            stop_event.set()


def video_to_mosaic_file(
    input_path: str | Path,
    output_path: str | Path,
    config: MosaicConfig,
) -> None:
    """Convert a video file into a LEGO mosaic video."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    # Upfront FFmpeg presence check
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is required for video encoding but was not found.")

    if not input_path.is_file():
        raise FileNotFoundError(f"Input video does not exist: {input_path}")

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    if output_path.suffix.lower() != ".mp4":
        raise ValueError("Video output must use the .mp4 extension.")

    validate_input_size(input_path.stat().st_size, bypass=config.bypass_limits)
    validate_workers(config.workers, bypass=config.bypass_limits)
    validate_buffer_size(config.buffer_size, bypass=config.bypass_limits)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Temporary file for atomic writing (Fix H6)
    tmp_path = output_path.parent / f".tmp_{output_path.name}"

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Could not open video: {input_path}")

    try:
        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not np.isfinite(source_fps) or source_fps <= 0:
            raise RuntimeError("Could not determine video frame rate.")

        validate_video_fps(source_fps, bypass=config.bypass_limits)

        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count < 1:
            raise RuntimeError("Could not determine video frame count.")

        # Probe first frame to determine true orientation and dimensions
        success, first_frame = capture.read()
        if not success or first_frame is None:
            raise RuntimeError(f"Could not read first frame from: {input_path}")

        source_height, source_width = first_frame.shape[:2]
        if source_width < 1 or source_height < 1:
            raise RuntimeError("Could not determine video dimensions.")

        output_fps = resolve_output_fps(config.fps, source_fps)
        validate_video_fps(output_fps, bypass=config.bypass_limits)

        est_duration = frame_count / source_fps
        validate_video_duration(est_duration, bypass=config.bypass_limits)

        grid_width, grid_height = calculate_grid_dimensions(
            config.grid_width, source_width, source_height
        )
        output_width, output_height = calculate_output_dimensions(
            config.grid_width, config.tile_size, source_width, source_height
        )
        validate_output_resolution(output_width, output_height, bypass=config.bypass_limits)

        # Estimate cost, bitrate, and units with size capping
        estimate = estimate_video_cost(
            config=config,
            source_width=source_width,
            source_height=source_height,
            source_fps=source_fps,
            frame_count=frame_count,
        )
        validate_processing_units(estimate.processing_units, bypass=config.bypass_limits)
        validate_output_size(estimate.estimated_size_bytes, bypass=config.bypass_limits)

        # Pre-warm atlas and quantizer LUT before launching worker threads
        atlas = get_atlas(
            palette=config.palette,
            tile_size=config.tile_size,
        )
        atlas_bgr = np.ascontiguousarray(atlas[..., ::-1])
        atlas_bgr.flags.writeable = False
        prewarm_quantizer(config.palette, config.quality)

        frame_queue: Queue = Queue(maxsize=config.buffer_size)
        output_queue: Queue = Queue(maxsize=config.buffer_size)
        stop_event = Event()

        reader_errors: list[BaseException] = []
        writer_errors: list[BaseException] = []

        writer_state = {
            "width": 0,
            "height": 0,
            "frames_written": 0,
        }

        reader_thread = Thread(
            target=_reader,
            args=(
                capture,
                first_frame,
                (grid_width, grid_height),
                frame_queue,
                stop_event,
                reader_errors,
                source_fps,
                output_fps,
                config.bypass_limits,
            ),
            name="video-reader",
            daemon=True,
        )

        writer_thread = Thread(
            target=_writer,
            args=(
                output_queue,
                tmp_path,
                output_fps,
                stop_event,
                writer_state,
                writer_errors,
                estimate.estimated_bitrate_bps,
            ),
            name="video-writer",
            daemon=True,
        )

        reader_thread.start()
        writer_thread.start()

        pending: deque[tuple[int, Future[np.ndarray], int]] = deque()
        frames_submitted = 0
        failed = False

        try:
            with ThreadPoolExecutor(
                max_workers=config.workers,
                thread_name_prefix="mosaic-worker",
            ) as pool:
                input_finished = False

                while not input_finished:
                    if stop_event.is_set():
                        if writer_errors:
                            raise RuntimeError("Video writer thread failed.") from writer_errors[0]
                        if reader_errors:
                            raise RuntimeError("Video reader thread failed.") from reader_errors[0]
                        raise RuntimeError("Video processing was stopped unexpectedly.")

                    try:
                        item = frame_queue.get(timeout=0.1)
                    except Empty:
                        continue

                    if item is None:
                        input_finished = True
                    else:
                        frame_index, small_bgr, repeat_count = item
                        pending.append(
                            (
                                frame_index,
                                pool.submit(
                                    process_small_frame,
                                    small_bgr,
                                    config,
                                    atlas_bgr,
                                ),
                                repeat_count,
                            )
                        )
                        frames_submitted += 1

                    while pending and (input_finished or len(pending) >= config.buffer_size):
                        frame_index, future, repeat_count = pending.popleft()
                        mosaic_frame = future.result()

                        if not _put_while_running(
                            output_queue,
                            (frame_index, mosaic_frame, repeat_count),
                            stop_event,
                        ):
                            if writer_errors:
                                raise RuntimeError("Video writer thread failed.") from writer_errors[0]
                            raise RuntimeError("Could not enqueue a processed video frame.")

        except BaseException:
            failed = True
            stop_event.set()
            raise

        finally:
            if not failed and not stop_event.is_set():
                _put_while_running(output_queue, None, stop_event)
            else:
                stop_event.set()

            reader_thread.join(timeout=5)
            capture.release()
            writer_thread.join(timeout=30)

            if reader_thread.is_alive():
                stop_event.set()
            if writer_thread.is_alive():
                stop_event.set()

        if reader_errors:
            raise RuntimeError("An error occurred while reading the video.") from reader_errors[0]
        if writer_errors:
            raise RuntimeError("An error occurred while writing the video.") from writer_errors[0]
        if reader_thread.is_alive():
            raise RuntimeError("Video reader thread did not finish in time.")
        if writer_thread.is_alive():
            raise RuntimeError("Video writer thread did not finish in time.")
        if writer_state["frames_written"] == 0:
            raise RuntimeError("No frames were written to the output video.")

        output_size = tmp_path.stat().st_size
        validate_output_size(output_size, bypass=config.bypass_limits)

        # Atomic replacement on success
        os.replace(tmp_path, output_path)

        print(f"Grid width: {config.grid_width} tiles")
        print(f"Tile size: {config.tile_size} pixels")
        print(f"Output resolution: {writer_state['width']} x {writer_state['height']} pixels")
        print(f"Source FPS: {source_fps:.2f}")
        print(f"Output FPS: {output_fps:.2f}")
        print(f"Frames submitted: {frames_submitted}")
        print(f"Frames written: {writer_state['frames_written']}")
        print(f"Quality: {config.quality.value}")
        print(f"Target bitrate: {estimate.estimated_bitrate_bps / 1_000_000:.2f} Mbps")
        print(f"Output size: {output_size / (1024 * 1024):.2f} MiB")
        print(f"Estimated job cost: {estimate.processing_units:,} units ({estimate.estimated_credits} credits)")
        print(f"Processing worker threads: {config.workers}")

    finally:
        if capture.isOpened():
            capture.release()
        # Clean up any leftover temporary file on failure
        tmp_path.unlink(missing_ok=True)
