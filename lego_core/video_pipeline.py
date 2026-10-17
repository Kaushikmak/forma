from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
import os

import cv2
import numpy as np

from config import MosaicConfig
from quantizer import quantize_rgb
from tile_renderer import get_atlas, render_indices


def process_frame(
    frame_bgr: np.ndarray,
    config: MosaicConfig,
    atlas_bgr: np.ndarray,
) -> np.ndarray:
    """Convert one OpenCV BGR frame into a LEGO mosaic frame."""
    frame_height, frame_width = frame_bgr.shape[:2]
    grid_height = max(
        1,
        round(config.grid_width * frame_height / frame_width),
    )

    small_bgr = cv2.resize(
        frame_bgr,
        (config.grid_width, grid_height),
        interpolation=cv2.INTER_AREA,
    )
    indices = quantize_rgb(small_bgr[..., ::-1], config.palette)
    return render_indices(indices, atlas_bgr)


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
    frame_queue: Queue,
    stop_event: Event,
    errors: list[BaseException],
) -> None:
    """Decode frames in a background thread."""
    frame_index = 0
    try:
        while not stop_event.is_set():
            success, frame = capture.read()
            if not success:
                break
            if not _put_while_running(
                frame_queue,
                (frame_index, frame),
                stop_event,
            ):
                return
            frame_index += 1
    except BaseException as exc:
        errors.append(exc)
    finally:
        _put_while_running(frame_queue, None, stop_event)


def _writer(
    output_queue: Queue,
    output_path: Path,
    fps: float,
    stop_event: Event,
    state: dict[str, int],
    errors: list[BaseException],
) -> None:
    """Encode processed frames in queue order."""
    video_writer = None
    try:
        while not stop_event.is_set():
            try:
                item = output_queue.get(timeout=0.1)
            except Empty:
                continue

            if item is None:
                break

            _, frame = item
            if video_writer is None:
                height, width = frame.shape[:2]
                video_writer = cv2.VideoWriter(
                    str(output_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    fps,
                    (width, height),
                )
                if not video_writer.isOpened():
                    raise RuntimeError(
                        f"Could not create output video: {output_path} "
                        f"({width}x{height})"
                    )
                state["width"] = width
                state["height"] = height

            video_writer.write(frame)
            state["frames_written"] += 1
    except BaseException as exc:
        errors.append(exc)
        stop_event.set()
    finally:
        if video_writer is not None:
            video_writer.release()


def video_to_mosaic_file(
    input_path: str | Path,
    output_path: str | Path,
    config: MosaicConfig,
    workers: int | None = None,
    buffer_size: int | None = None,
) -> None:
    """Convert a video file into a LEGO mosaic video."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.is_file():
        raise FileNotFoundError(f"Input video does not exist: {input_path}")
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output paths must be different.")

    if workers is None:
        workers = min(4, os.cpu_count() or 1)
    if workers < 1:
        raise ValueError("workers must be positive.")

    if buffer_size is None:
        buffer_size = max(2, workers * 2)
    if buffer_size < 1:
        raise ValueError("buffer_size must be positive.")

    atlas = get_atlas(
        palette=config.palette,
        tile_size=config.tile_size,
    )

    atlas_bgr = atlas[..., ::-1].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Could not open video: {input_path}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(fps) or fps <= 0:
        capture.release()
        raise RuntimeError("Could not determine video frame rate.")

    frame_queue: Queue = Queue(maxsize=buffer_size)
    output_queue: Queue = Queue(maxsize=buffer_size)
    stop_event = Event()
    reader_errors: list[BaseException] = []
    writer_errors: list[BaseException] = []
    writer_state = {"width": 0, "height": 0, "frames_written": 0}

    reader_thread = Thread(
        target=_reader,
        args=(capture, frame_queue, stop_event, reader_errors),
        name="video-reader",
        daemon=True,
    )
    writer_thread = Thread(
        target=_writer,
        args=(
            output_queue,
            output_path,
            float(fps),
            stop_event,
            writer_state,
            writer_errors,
        ),
        name="video-writer",
        daemon=True,
    )

    reader_thread.start()
    writer_thread.start()

    pending: deque[tuple[int, Future[np.ndarray]]] = deque()
    frames_read = 0
    failed = False

    try:
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="mosaic-worker",
        ) as pool:
            input_finished = False
            while not input_finished:
                if stop_event.is_set():
                    if writer_errors:
                        raise RuntimeError(
                            "Video writer thread failed."
                        ) from writer_errors[0]
                    if reader_errors:
                        raise RuntimeError(
                            "Video reader thread failed."
                        ) from reader_errors[0]
                    raise RuntimeError("Video processing was stopped unexpectedly.")

                try:
                    item = frame_queue.get(timeout=0.1)
                except Empty:
                    continue

                if item is None:
                    input_finished = True
                else:
                    frame_index, frame = item
                    frames_read += 1
                    pending.append(
                        (
                            frame_index,
                            pool.submit(
                                process_frame,
                                frame,
                                config,
                                atlas_bgr,
                            ),
                        )
                    )

                # Consume futures in submission order to preserve video timing.
                while pending and (input_finished or len(pending) >= buffer_size):
                    frame_index, future = pending.popleft()
                    mosaic_frame = future.result()
                    if not _put_while_running(
                        output_queue,
                        (frame_index, mosaic_frame),
                        stop_event,
                    ):
                        if writer_errors:
                            raise RuntimeError(
                                "Video writer thread failed."
                            ) from writer_errors[0]
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
        if reader_thread.is_alive():
            capture.release()
            reader_thread.join(timeout=2)
        else:
            capture.release()
        writer_thread.join(timeout=30)

        if reader_thread.is_alive():
            stop_event.set()
        if writer_thread.is_alive():
            stop_event.set()

    if reader_errors:
        raise RuntimeError(
            "An error occurred while reading the video."
        ) from reader_errors[0]
    if writer_errors:
        raise RuntimeError(
            "An error occurred while writing the video."
        ) from writer_errors[0]
    if reader_thread.is_alive():
        raise RuntimeError("Video reader thread did not finish in time.")
    if writer_thread.is_alive():
        raise RuntimeError("Video writer thread did not finish in time.")
    if writer_state["frames_written"] == 0:
        raise RuntimeError("No frames were written to the output video.")
    if writer_state["frames_written"] != frames_read:
        raise RuntimeError(
            f"Frame count mismatch: read {frames_read}, "
            f"wrote {writer_state['frames_written']}."
        )

    print(f"Grid width: {config.grid_width} tiles")
    print(f"Tile size: {config.tile_size} pixels")
    print(
        f"Output resolution: {writer_state['width']} x "
        f"{writer_state['height']} pixels"
    )
    print(f"Frames read: {frames_read}")
    print(f"Frames written: {writer_state['frames_written']}")
    print(f"Frame rate: {fps:.2f} FPS")
    print(f"Processing worker threads: {workers}")
