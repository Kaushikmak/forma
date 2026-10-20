from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from config import FPS, MosaicConfig, Palette, Quality
from gif_pipeline import gif_to_mosaic_file
from image_pipeline import image_to_mosaic_file
from resource_limits import (
    MAX_GIF_DURATION_SECONDS,
    MAX_GIF_FRAMES,
    MAX_INPUT_SIZE_BYTES,
    MAX_OUTPUT_PIXELS,
    MAX_OUTPUT_SIZE_BYTES,
    MAX_VIDEO_DURATION_SECONDS,
    MAX_VIDEO_FPS,
    ResourceLimitError,
)
from video_pipeline import video_to_mosaic_file

try:
    from dotenv import load_dotenv
    load_dotenv()
    _backend_env = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if _backend_env.is_file():
        load_dotenv(_backend_env)
    _root_env = Path(__file__).resolve().parent.parent / ".env"
    if _root_env.is_file():
        load_dotenv(_root_env)
except ImportError:
    pass


def download_from_supabase_if_needed(input_path: Path, bucket: str, key: str) -> bool:
    """Download input file from Supabase Storage if not present locally."""
    if input_path.is_file():
        return True

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        return False

    b_lower = bucket.lower()
    clean_key = key
    if clean_key.lower().startswith(f"{b_lower}/"):
        clean_key = clean_key[len(b_lower) + 1:]
    if (b_lower in ("upload", "uploads")) and clean_key.startswith("uploads/"):
        clean_key = clean_key[len("uploads/"):]
    if (b_lower in ("results", "outputs")) and clean_key.startswith("outputs/"):
        clean_key = clean_key[len("outputs/"):]
    clean_key = clean_key.lstrip("/")

    resolved_bucket = "upload" if b_lower in ("upload", "uploads") else ("Results" if b_lower in ("results", "outputs") else bucket)

    import urllib.request
    import urllib.error

    url = f"{supabase_url.rstrip('/')}/storage/v1/object/authenticated/{resolved_bucket}/{clean_key}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        method="GET",
    )

    try:
        input_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(input_path, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        return input_path.is_file() and input_path.stat().st_size > 0
    except Exception as exc:
        sys.stderr.write(f"[Worker] Failed to download {resolved_bucket}/{clean_key} from Supabase: {exc}\n")
        if input_path.exists():
            input_path.unlink(missing_ok=True)
        return False


def upload_to_supabase_if_configured(output_path: Path, bucket: str, key: str, content_type: str) -> bool:
    """Upload result file to Supabase Storage if remote credentials exist."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key or not output_path.is_file():
        return False

    b_lower = bucket.lower()
    clean_key = key
    if clean_key.lower().startswith(f"{b_lower}/"):
        clean_key = clean_key[len(b_lower) + 1:]
    if (b_lower in ("results", "outputs")) and clean_key.startswith("outputs/"):
        clean_key = clean_key[len("outputs/"):]
    clean_key = clean_key.lstrip("/")

    resolved_bucket = "Results" if b_lower in ("results", "outputs") else bucket

    import urllib.request
    import urllib.error

    url = f"{supabase_url.rstrip('/')}/storage/v1/object/{resolved_bucket}/{clean_key}"
    try:
        with open(output_path, "rb") as f:
            file_bytes = f.read()

        req = urllib.request.Request(
            url,
            data=file_bytes,
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": content_type or "application/octet-stream",
                "x-upsert": "true",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status in (200, 201)
    except Exception as exc:
        sys.stderr.write(f"[Worker] Failed to upload {resolved_bucket}/{clean_key} to Supabase: {exc}\n")
        return False


def detect_media_kind(file_path: Path) -> str:
    """Detect media kind ('image', 'gif', 'video') from file magic bytes."""
    with open(file_path, "rb") as f:
        header = f.read(32)

    if len(header) < 4:
        raise ValueError("File is empty or too small.")

    # GIF
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"

    # PNG
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"

    # JPEG
    if header.startswith(b"\xff\xd8\xff"):
        return "image"

    # WebP: RIFF....WEBP
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP":
        return "image"

    # BMP
    if header.startswith(b"BM"):
        return "image"

    # TIFF: II*\0 or MM\0*
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "image"

    # MP4 / MOV / M4V (ISO Base Media file with ftyp box)
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video"

    # QuickTime / MOV (moov atom or skip)
    if len(header) >= 8 and header[4:8] in (b"moov", b"free", b"skip", b"wide"):
        return "video"

    # WebM / MKV (EBML ID \x1a\x45\xdf\xa3)
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "video"

    # AVI: RIFF....AVI
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"AVI ":
        return "video"

    # Fallback to extension check if ambiguous
    suffix = file_path.suffix.lower()
    if suffix in (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"):
        return "video"
    if suffix == ".gif":
        return "gif"
    if suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"):
        return "image"

    raise ValueError(f"Unsupported media format (unknown magic bytes and suffix: {suffix})")


def validate_job_envelope(envelope: dict[str, Any]) -> None:
    """Validate Contract v1 envelope structure and parameter types."""
    if envelope.get("v") != 1:
        raise ValueError("UNSUPPORTED_VERSION: Worker contract version must be 1.")

    required_fields = ["jobId", "style", "params", "input", "output", "createdAt", "expiresAt"]
    for field in required_fields:
        if field not in envelope:
            raise ValueError(f"INVALID_PARAMS: Missing required field '{field}'.")

    if envelope["style"] != "lego":
        raise ValueError(f"UNKNOWN_STYLE: Style '{envelope['style']}' is not supported.")

    params = envelope["params"]
    if not isinstance(params, dict):
        raise ValueError("INVALID_PARAMS: 'params' must be an object.")

    # Validate Lego params
    width = params.get("width", 64)
    if not isinstance(width, int) or width < 16 or width > 256:
        raise ValueError("INVALID_PARAMS: 'width' must be an integer between 16 and 256.")

    palette = params.get("palette", "classic")
    if palette not in ("classic", "extended"):
        raise ValueError(f"INVALID_PARAMS: Unsupported palette '{palette}'.")

    tile_size = params.get("tileSize", 16)
    if tile_size not in (8, 12, 16, 24, 32):
        raise ValueError(f"INVALID_PARAMS: 'tileSize' must be one of [8, 12, 16, 24, 32], got {tile_size}.")

    quality = params.get("quality", "high")
    if quality not in ("standard", "high", "maximum"):
        raise ValueError(f"INVALID_PARAMS: Unsupported quality '{quality}'.")

    fps = params.get("fps", "original")
    if fps not in ("original", "24", "30", "60"):
        raise ValueError(f"INVALID_PARAMS: Unsupported fps '{fps}'.")

    bitrate_mbps = params.get("bitrateMbps")
    if bitrate_mbps is not None:
        if not isinstance(bitrate_mbps, (int, float)) or bitrate_mbps <= 0:
            raise ValueError("INVALID_PARAMS: 'bitrateMbps' must be a positive number.")


def process_worker_job(
    job_envelope: dict[str, Any],
    storage_root: Path,
    on_event: Callable[[dict[str, Any]], None],
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Process a single job following Worker Contract v1 specifications.
    Emits state transitions: probing (1-8), processing (8-90), encoding (95), done (100).
    """
    start_time = time.monotonic()
    job_id = job_envelope.get("jobId", "unknown")


    now_ms = int(time.time() * 1000)
    if job_envelope.get("expiresAt", float("inf")) < now_ms:
        err_res = {
            "jobId": job_id,
            "status": "expired",
            "errorCode": "EXPIRED",
            "errorMessage": "Job expired before processing started.",
            "refundable": 0,
        }
        on_event(err_res)
        return err_res


    try:
        validate_job_envelope(job_envelope)
    except ValueError as exc:
        msg = str(exc)
        code = msg.split(":")[0] if ":" in msg else "INVALID_PARAMS"
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": code,
            "errorMessage": msg,
            "refundable": 0,
        }
        on_event(err_res)
        return err_res

    input_spec = job_envelope["input"]
    input_key = input_spec.get("key", "")
    input_path = (storage_root / input_key).resolve()

    if not input_path.is_file():
        input_bucket = input_spec.get("bucket", "upload")
        downloaded = download_from_supabase_if_needed(input_path, input_bucket, input_key)
        if not downloaded or not input_path.is_file():
            err_res = {
                "jobId": job_id,
                "status": "rejected",
                "errorCode": "INPUT_MISSING",
                "errorMessage": f"Input object not found in storage: {input_key}",
                "refundable": 0,
            }
            on_event(err_res)
            return err_res

    limits = job_envelope.get("limits") or {}
    max_bytes = min(limits.get("maxBytes", MAX_INPUT_SIZE_BYTES), MAX_INPUT_SIZE_BYTES)
    file_size = input_path.stat().st_size

    if file_size > max_bytes:
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": "TOO_LARGE",
            "errorMessage": f"Input file size ({file_size / (1024*1024):.1f} MB) exceeds limit ({max_bytes / (1024*1024):.0f} MB).",
            "refundable": 0,
        }
        on_event(err_res)
        return err_res


    on_event({"jobId": job_id, "status": "probing", "progress": 2})

    try:
        media_kind = detect_media_kind(input_path)
    except ValueError as exc:
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": "UNSUPPORTED_TYPE",
            "errorMessage": str(exc),
            "refundable": 0,
        }
        on_event(err_res)
        return err_res

    input_width = 0
    input_height = 0
    duration_sec = 0.0
    frames_count = 1

    try:
        if media_kind == "image":
            with Image.open(input_path) as img:
                input_width, input_height = img.size
                if input_width * input_height > limits.get("maxPixels", MAX_OUTPUT_PIXELS):
                    raise ResourceLimitError("Input resolution exceeds maximum pixel budget.")
        elif media_kind == "gif":
            with Image.open(input_path) as img:
                input_width, input_height = img.size
                frames_count = getattr(img, "n_frames", 1)
                max_frames = limits.get("maxFrames", MAX_GIF_FRAMES)
                if frames_count > max_frames:
                    raise ResourceLimitError(f"GIF contains {frames_count} frames; maximum allowed is {max_frames}.")
                # probe duration
                tot_ms = 0
                for i in range(frames_count):
                    img.seek(i)
                    tot_ms += max(20, int(img.info.get("duration", 100)))
                duration_sec = tot_ms / 1000.0
                max_dur = limits.get("maxDurationSec", MAX_GIF_DURATION_SECONDS)
                if duration_sec > max_dur:
                    raise ResourceLimitError(f"GIF duration ({duration_sec:.1f}s) exceeds limit ({max_dur:.0f}s).")
        else:  # video
            import cv2
            cap = cv2.VideoCapture(str(input_path))
            if not cap.isOpened():
                raise RuntimeError("Could not open video file for probing.")
            source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            max_fps = limits.get("maxFps", MAX_VIDEO_FPS)
            if source_fps > max_fps:
                cap.release()
                raise ResourceLimitError(f"Video frame rate ({source_fps:.1f}) exceeds maximum allowed ({max_fps:.0f}).")
            frames_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
            duration_sec = frames_count / max(1.0, source_fps)
            max_dur = limits.get("maxDurationSec", MAX_VIDEO_DURATION_SECONDS)
            if duration_sec > max_dur:
                cap.release()
                raise ResourceLimitError(f"Video duration ({duration_sec:.1f}s) exceeds limit ({max_dur:.0f}s).")
            ret, first_frame = cap.read()
            cap.release()
            if not ret or first_frame is None:
                raise RuntimeError("Could not decode first video frame.")
            input_height, input_width = first_frame.shape[:2]

    except ResourceLimitError as exc:
        err_msg = str(exc)
        code = "TOO_LONG" if "duration" in err_msg.lower() else "TOO_MANY_FRAMES" if "frames" in err_msg.lower() else "TOO_LARGE_PIXELS"
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": code,
            "errorMessage": err_msg,
            "refundable": 0,
        }
        on_event(err_res)
        return err_res
    except Exception as exc:
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": "DECODE_FAILED",
            "errorMessage": f"Failed to decode or inspect media: {exc}",
            "refundable": 0,
        }
        on_event(err_res)
        return err_res

    on_event({
        "jobId": job_id,
        "status": "probing",
        "progress": 8,
        "mediaKind": media_kind,
        "inputWidth": input_width,
        "inputHeight": input_height,
    })

    if cancel_check and cancel_check():
        err_res = {"jobId": job_id, "status": "cancelled", "errorCode": "CANCELLED", "errorMessage": "Job was cancelled."}
        on_event(err_res)
        return err_res

    params = job_envelope["params"]
    config = MosaicConfig(
        grid_width=params.get("width", 64),
        tile_size=params.get("tileSize", 16),
        palette=Palette(params.get("palette", "classic")),
        fps=FPS(params.get("fps", "original")),
        quality=Quality(params.get("quality", "high")),
        workers=params.get("workers", 4),
        bitrate_mbps=params.get("bitrateMbps"),
    )


    output_spec = job_envelope["output"]
    output_prefix = output_spec.get("prefix", f"outputs/{job_id}/")
    output_dir = (storage_root / output_prefix).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if media_kind == "video":
        out_filename = "result.mp4"
        content_type = "video/mp4"
    elif media_kind == "gif":
        out_filename = "result.gif"
        content_type = "image/gif"
    else:
        out_filename = "result.png"
        content_type = "image/png"

    output_path = output_dir / out_filename
    result_key = f"{output_prefix.rstrip('/')}/{out_filename}"


    on_event({"jobId": job_id, "status": "processing", "progress": 15})

    try:
        if media_kind == "image":
            on_event({"jobId": job_id, "status": "processing", "progress": 50})
            image_to_mosaic_file(input_path, output_path, config)
        elif media_kind == "gif":
            on_event({"jobId": job_id, "status": "processing", "progress": 50})
            gif_to_mosaic_file(input_path, output_path, config)
        else:  # video
            on_event({"jobId": job_id, "status": "processing", "progress": 50})
            video_to_mosaic_file(input_path, output_path, config)

    except ResourceLimitError as exc:
        output_path.unlink(missing_ok=True)
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": "OUTPUT_TOO_LARGE" if "output size" in str(exc).lower() else "TOO_LARGE",
            "errorMessage": str(exc),
            "refundable": 0,
        }
        on_event(err_res)
        return err_res
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        err_res = {
            "jobId": job_id,
            "status": "failed",
            "errorCode": "INTERNAL",
            "errorMessage": f"Mosaic generation failed: {exc}",
            "refundable": 1,
        }
        on_event(err_res)
        return err_res

    # Encoding
    on_event({"jobId": job_id, "status": "encoding", "progress": 95})

    out_bytes = output_path.stat().st_size
    if out_bytes > MAX_OUTPUT_SIZE_BYTES:
        output_path.unlink(missing_ok=True)
        err_res = {
            "jobId": job_id,
            "status": "rejected",
            "errorCode": "OUTPUT_TOO_LARGE",
            "errorMessage": f"Rendered mosaic size ({out_bytes / (1024*1024):.2f} MB) exceeds 50 MB limit.",
            "refundable": 0,
        }
        on_event(err_res)
        return err_res

    # Extract final result dimensions
    final_w = config.grid_width * config.tile_size
    final_h = final_w
    if media_kind in ("image", "gif"):
        with Image.open(output_path) as out_img:
            final_w, final_h = out_img.size
            if media_kind == "gif":
                frames_count = getattr(out_img, "n_frames", frames_count)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    output_bucket = output_spec.get("bucket", "Results")
    upload_to_supabase_if_configured(output_path, output_bucket, result_key, content_type)

    done_res = {
        "jobId": job_id,
        "status": "done",
        "progress": 100,
        "resultBucket": output_bucket,
        "resultKey": result_key,
        "contentType": content_type,
        "width": final_w,
        "height": final_h,
        "frames": frames_count,
        "durationSec": duration_sec,
        "bytes": out_bytes,
        "cacheHit": 0,
        "processingMs": elapsed_ms,
    }
    on_event(done_res)
    return done_res


def consume_redis_streams(
    redis_url: str = "redis://localhost:6379",
    lanes: list[str] | None = None,
    prefix: str = "mosaic",
    group_name: str = "mosaic-workers",
    consumer_name: str | None = None,
    storage_root: Path | None = None,
    once: bool = False,
    block_ms: int = 2000,
) -> int:
    """
    Consume jobs from Redis Streams according to Worker Contract v1.
    Handles message decoding, expiry/cancellation checks, real-time event updates,
    and acknowledges processed entries.
    """
    try:
        import redis
    except ImportError:
        sys.stderr.write("Error: 'redis' python package is not installed. Install with `pip install redis`.\n")
        return 1

    if lanes is None:
        lanes = ["image", "video"]
    if consumer_name is None:
        consumer_name = f"worker-{os.getpid()}-{int(time.time())}"
    if storage_root is None:
        storage_root = Path(".forma_storage").resolve()
    else:
        storage_root = Path(storage_root).resolve()

    client = redis.from_url(redis_url, decode_responses=True)

    # Setup consumer groups for each stream
    streams_dict: dict[str, str] = {}
    for lane in lanes:
        stream_key = f"{prefix}:jobs:{lane}"
        streams_dict[stream_key] = ">"
        try:
            client.xgroup_create(stream_key, group_name, id="0", mkstream=True)
        except redis.exceptions.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                sys.stderr.write(f"Warning: xgroup_create for {stream_key}: {exc}\n")

    sys.stdout.write(f"[Worker] Listening on {list(streams_dict.keys())} as '{consumer_name}' in group '{group_name}'\n")
    sys.stdout.flush()

    stop_requested = False
    import signal

    def sig_handler(signum: Any, frame: Any) -> None:
        nonlocal stop_requested
        sys.stdout.write("\n[Worker] Shutdown requested. Finishing active job...\n")
        sys.stdout.flush()
        stop_requested = True

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    def handle_message(stream_name: str, msg_id: str, fields: dict[str, Any]) -> None:
        try:
            raw_data = fields.get("data")
            if not raw_data:
                sys.stderr.write(f"[Worker] Skipping invalid message {msg_id}: no 'data' field\n")
                client.xack(stream_name, group_name, msg_id)
                return

            envelope = json.loads(raw_data)
            job_id = envelope.get("jobId", "unknown")
            hash_key = f"{prefix}:job:{job_id}"
            event_channel = f"{prefix}:job:{job_id}:events"

            def publish_event(event_dict: dict[str, Any]) -> None:
                # Update hash in Redis
                hash_updates: dict[str, str] = {}
                for k, v in event_dict.items():
                    if v is not None:
                        hash_updates[k] = str(v)
                hash_updates["updatedAt"] = str(int(time.time() * 1000))
                try:
                    client.hset(hash_key, mapping=hash_updates)
                except Exception as h_err:
                    sys.stderr.write(f"[Worker] Failed to update hash {hash_key}: {h_err}\n")

                # Publish to Redis Pub/Sub
                try:
                    client.publish(event_channel, json.dumps(event_dict))
                except Exception as p_err:
                    sys.stderr.write(f"[Worker] Failed to publish event to {event_channel}: {p_err}\n")

                # If terminal, write to finished events stream
                status = event_dict.get("status")
                if status in ("done", "failed", "rejected", "cancelled", "expired"):
                    finished_entry = {
                        "jobId": job_id,
                        "status": status,
                        "refundable": str(event_dict.get("refundable", 0)),
                    }
                    if "errorCode" in event_dict and event_dict["errorCode"]:
                        finished_entry["errorCode"] = str(event_dict["errorCode"])
                    try:
                        client.xadd(f"{prefix}:events:finished", finished_entry)
                    except Exception as f_err:
                        sys.stderr.write(f"[Worker] Failed to append to finished stream: {f_err}\n")

            # Check cancellation
            try:
                job_hash = client.hgetall(hash_key)
            except Exception:
                job_hash = {}

            if job_hash.get("cancel") == "1":
                publish_event({
                    "jobId": job_id,
                    "status": "cancelled",
                    "errorCode": "CANCELLED",
                    "errorMessage": "Job was cancelled by client.",
                    "refundable": 0,
                })
                client.xack(stream_name, group_name, msg_id)
                return

            # Check expiration
            now_ms = int(time.time() * 1000)
            if envelope.get("expiresAt", float("inf")) < now_ms:
                publish_event({
                    "jobId": job_id,
                    "status": "expired",
                    "errorCode": "EXPIRED",
                    "errorMessage": "Job expired before processing started.",
                    "refundable": 0,
                })
                client.xack(stream_name, group_name, msg_id)
                return

            def check_cancelled() -> bool:
                try:
                    return client.hget(hash_key, "cancel") == "1"
                except Exception:
                    return False

            # Increment attempts
            try:
                client.hincrby(hash_key, "attempts", 1)
            except Exception:
                pass

            # Process the job
            process_worker_job(
                envelope,
                storage_root,
                on_event=publish_event,
                cancel_check=check_cancelled,
            )

        except Exception as exc:
            sys.stderr.write(f"[Worker] Error processing job from message {msg_id}: {exc}\n")
        finally:
            try:
                client.xack(stream_name, group_name, msg_id)
            except Exception:
                pass

    while not stop_requested:
        # Check for idle pending messages from prior crashed workers
        for s_key in streams_dict.keys():
            try:
                claimed = client.xautoclaim(s_key, group_name, consumer_name, min_idle_time=30000, start_id="0-0", count=5)
                if claimed and len(claimed) >= 2 and claimed[1]:
                    for c_msg_id, c_fields in claimed[1]:
                        handle_message(s_key, c_msg_id, c_fields)
            except Exception:
                pass

        try:
            entries = client.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams=streams_dict,
                count=1,
                block=block_ms,
            )
        except redis.exceptions.ConnectionError as exc:
            sys.stderr.write(f"[Worker] Redis connection error: {exc}. Retrying in 2s...\n")
            time.sleep(2)
            continue
        except Exception as exc:
            if stop_requested:
                break
            sys.stderr.write(f"[Worker] Error reading from stream: {exc}\n")
            time.sleep(1)
            continue

        if not entries:
            if once:
                break
            continue

        for stream_name, messages in entries:
            for msg_id, fields in messages:
                handle_message(stream_name, msg_id, fields)
                if once:
                    break
            if once:
                break

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker Contract v1 executor")
    parser.add_argument("--job", type=str, help="JSON-encoded job message envelope")
    parser.add_argument("--storage-root", type=str, default=".forma_storage", help="Storage directory root")
    parser.add_argument("--consume", type=str, help="Consume from Redis stream lanes (e.g. 'image,video')")
    parser.add_argument("--redis-url", type=str, default=os.getenv("REDIS_URL", "redis://localhost:6379"), help="Redis URL")
    parser.add_argument("--prefix", type=str, default=os.getenv("REDIS_PREFIX", "mosaic"), help="Redis prefix")
    parser.add_argument("--group-name", type=str, default="mosaic-workers", help="Consumer group name")
    parser.add_argument("--consumer-name", type=str, help="Consumer instance name")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    args = parser.parse_args()

    storage_root = Path(args.storage_root).resolve()

    if args.consume:
        lanes = [l.strip() for l in args.consume.split(",") if l.strip()]
        sys.exit(consume_redis_streams(
            redis_url=args.redis_url,
            lanes=lanes,
            prefix=args.prefix,
            group_name=args.group_name,
            consumer_name=args.consumer_name,
            storage_root=storage_root,
            once=args.once,
        ))

    if not args.job:
        # Read from stdin
        job_data = sys.stdin.read().strip()
    else:
        job_data = args.job

    if not job_data:
        sys.stderr.write("Error: No job payload provided.\n")
        sys.exit(1)

    envelope = json.loads(job_data)

    def print_event(event: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(event) + "\n")
        sys.stdout.flush()

    result = process_worker_job(envelope, storage_root, on_event=print_event)
    sys.exit(0 if result.get("status") == "done" else 1)


if __name__ == "__main__":
    main()
