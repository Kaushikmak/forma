from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
import os
import cv2
import numpy as np

from rgbTOlab import quantize_rgb
from tile_renderer import build_atlas, render_indices

INPUT_PATH = Path("samples/videoSamples/sample1.mp4")
OUTPUT_PATH = Path("output/lego_mosaic.mp4")
GRID_WIDTH = 64
TILE_SIZE = 16
WORKERS = min(4, os.cpu_count() or 1)
BUFFER_SIZE = max(2, WORKERS * 2)


def process_frame(frame_bgr: np.ndarray, atlas_bgr: np.ndarray) -> np.ndarray:
    """Convert one OpenCV BGR frame to a BGR LEGO mosaic frame"""
    frame_height, frame_width = frame_bgr.shape[:2]
    grid_height = max(1, round(GRID_WIDTH * frame_height / frame_width))

    small_bgr = cv2.resize(
        frame_bgr,
        (GRID_WIDTH, grid_height),
        interpolation=cv2.INTER_AREA,
    )

    indices = quantize_rgb(small_bgr[..., ::-1])
    return render_indices(indices, atlas_bgr)


def _put_while_running(
    target: Queue,
    item: object,
    stop_event: Event,
) -> bool:
    """Put into a bounded queue unless a pipeline stage has failed"""
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
    """Decode frames in the background and apply backpressure to the reader"""
    frame_index = 0
    try:
        while not stop_event.is_set():
            ok, frame = capture.read()
            if not ok:
                break
            if not _put_while_running(frame_queue, (frame_index, frame), stop_event):
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
    """Encode frames in queue order on a dedicated writer thread"""
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
                        f"Could not create output video: {output_path} ({width}x{height})"
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


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(INPUT_PATH))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {INPUT_PATH}")

    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        capture.release()
        raise RuntimeError("Could not determine video frame rate.")

    atlas_rgb = build_atlas(TILE_SIZE)
    atlas_bgr = atlas_rgb[..., ::-1].copy()

    frame_queue: Queue = Queue(maxsize=BUFFER_SIZE)
    output_queue: Queue = Queue(maxsize=BUFFER_SIZE)
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
        args=(output_queue, OUTPUT_PATH, fps, stop_event, writer_state, writer_errors),
        name="video-writer",
        daemon=True,
    )
    reader_thread.start()
    writer_thread.start()

    pending: deque[tuple[int, Future[np.ndarray]]] = deque()
    max_in_flight = BUFFER_SIZE
    frames_read = 0
    failed = False

    try:
        with ThreadPoolExecutor(
            max_workers=WORKERS, thread_name_prefix="mosaic-worker"
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
                    raise RuntimeError("Video processing was stopped unexpectedly")

                try:
                    item = frame_queue.get(timeout=0.1)
                except Empty:
                    continue

                if item is None:
                    input_finished = True
                else:
                    index, frame = item
                    frames_read += 1
                    pending.append(
                        (index, pool.submit(process_frame, frame, atlas_bgr))
                    )

                # Consume futures in original frame order
                # thread can encode previous frames while workers process newer ones
                while pending and (input_finished or len(pending) >= max_in_flight):
                    index, future = pending.popleft()
                    mosaic_frame = future.result()
                    if not _put_while_running(
                        output_queue, (index, mosaic_frame), stop_event
                    ):
                        if writer_errors:
                            raise RuntimeError(
                                "Video writer thread failed."
                            ) from writer_errors[0]
                        raise RuntimeError("Could not enqueue a processed video frame")

    except BaseException:
        failed = True
        stop_event.set()
        raise
    finally:
        if not failed and not stop_event.is_set():
            # All frames have been enqueued in order tell the writer to finish
            _put_while_running(output_queue, None, stop_event)
        else:
            stop_event.set()

        reader_thread.join(timeout=5)
        writer_thread.join(timeout=30)
        capture.release()

        if reader_thread.is_alive():
            stop_event.set()
        if writer_thread.is_alive():
            stop_event.set()

    if reader_errors:
        raise RuntimeError(
            "An error occurred while reading the video"
        ) from reader_errors[0]
    if writer_errors:
        raise RuntimeError(
            "An error occurred while writing the video"
        ) from writer_errors[0]
    if writer_thread.is_alive():
        raise RuntimeError("Video writer thread did not finish in time")
    if writer_state["frames_written"] == 0:
        raise RuntimeError("No frames were written to the output video")

    print(f"Grid width: {GRID_WIDTH} tiles")
    print(
        f"Output resolution: {writer_state['width']} x {writer_state['height']} pixels"
    )
    print(f"Frames read: {frames_read}")
    print(f"Frames written: {writer_state['frames_written']}")
    print(f"Frame rate: {fps:.2f} FPS")
    print(f"Processing worker threads: {WORKERS}")
    print(f"Saved video: {OUTPUT_PATH}")


main()
