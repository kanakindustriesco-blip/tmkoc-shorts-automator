import os
import re
import json
import math
import subprocess
import threading
import time
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import (
    CLIPS_DIR,
    INPUTS_DIR,
    RAW_VIDEOS_DIR,
    PROCESSED_RAW_DIR,
    THUMBNAILS_DIR,
    DAILY_THUMBNAIL_PATH,
    TARGET_WIDTH,
    TARGET_HEIGHT,
    VIDEO_WINDOW_Y_START,
    VIDEO_WINDOW_HEIGHT,
    DEFAULT_CLIP_DURATION,
    DEFAULT_INTERVAL_MINUTES
)
from app.template_engine import generate_part_overlay, generate_part_thumbnail

# Global registry
JOBS: Dict[str, Dict[str, Any]] = {}
WATCHER_ENABLED = True
PROCESSED_WATCHER_FILES: set = set()

# Number of parallel video rendering threads (uses 3-4 workers for 8 CPU cores)
MAX_PARALLEL_WORKERS = 3

def resolve_video_path(path_str: str) -> str:
    p = Path(path_str)
    if p.exists():
        return str(p)
    # Check in processed
    in_proc = PROCESSED_RAW_DIR / p.name
    if in_proc.exists():
        return str(in_proc)
    # Check in raw
    in_raw = RAW_VIDEOS_DIR / p.name
    if in_raw.exists():
        return str(in_raw)
    return str(p)

def get_video_info(video_path: str) -> Dict[str, Any]:
    video_path = resolve_video_path(video_path)
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(result.stdout)
        
        duration = float(data.get("format", {}).get("duration", 0))
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

        width = int(video_stream.get("width", 1920)) if video_stream else 1920
        height = int(video_stream.get("height", 1080)) if video_stream else 1080
        
        return {
            "duration": duration,
            "width": width,
            "height": height,
            "has_audio": audio_stream is not None,
            "format_name": data.get("format", {}).get("format_name", "")
        }
    except Exception as e:
        print(f"[ffprobe error] {e}")
        return {"duration": 0, "width": 1920, "height": 1080, "has_audio": True}

def extract_sample_frame(video_path: str, timestamp: float = 15.0, output_path: str = None) -> str:
    video_path = resolve_video_path(video_path)
    if not output_path:
        output_path = str(Path(video_path).parent / "sample_frame.jpg")
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_path
    except Exception as e:
        print(f"[extract frame error] {e}")
        return None

def build_ffmpeg_filter(
    use_blurred_bg: bool = True,
    anti_copyright: bool = True,
    logo_removal: str = "top-left"
) -> str:
    """
    Turbo-charged filter complex:
    - Ultra-light background blur (90x160 bilinear) or black padding, video centered between y=623 and 1241.
    - Anti-Copyright Shield: 1.02x scale/crop to break pixel grid matching, contrast/saturation shift,
      and corner delogo to obscure broadcaster watermarks (Sony SAB / Sony LIV).
    """
    delogo_filters = []
    if logo_removal in ("top-left", "both"):
        delogo_filters.append("delogo=x=18:y=12:w=115:h=55")
    if logo_removal in ("top-right", "both"):
        delogo_filters.append("delogo=x=945:y=12:w=115:h=55")
    
    delogo_str = (",".join(delogo_filters) + ",") if delogo_filters else ""

    if anti_copyright:
        fg_pipeline = (
            f"scale=1102:630:force_original_aspect_ratio=decrease,"
            f"crop={TARGET_WIDTH}:{VIDEO_WINDOW_HEIGHT},"
            f"{delogo_str}"
            f"eq=contrast=1.03:saturation=1.04:brightness=0.01[fg];"
        )
    else:
        if delogo_str:
            d_clean = delogo_str.rstrip(",")
            fg_pipeline = f"scale={TARGET_WIDTH}:{VIDEO_WINDOW_HEIGHT}:force_original_aspect_ratio=decrease,{d_clean}[fg];"
        else:
            fg_pipeline = f"scale={TARGET_WIDTH}:{VIDEO_WINDOW_HEIGHT}:force_original_aspect_ratio=decrease[fg];"

    if use_blurred_bg:
        filter_str = (
            f"[0:v]split=2[v_bg][v_src];"
            f"[v_bg]scale=90:160:force_original_aspect_ratio=increase,crop=90:160,boxblur=3:1,scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=bilinear[blurred];"
            f"[v_src]{fg_pipeline}"
            f"[blurred][fg]overlay=(W-w)/2:{VIDEO_WINDOW_Y_START}[composed];"
            f"[composed][1:v]overlay=0:0[outv]"
        )
    else:
        filter_str = (
            f"[0:v]{fg_pipeline}"
            f"[fg]pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:{VIDEO_WINDOW_Y_START}:color=black[padded];"
            f"[padded][1:v]overlay=0:0[outv]"
        )
    return filter_str

def render_single_clip(
    video_path: str,
    overlay_path: str,
    start_time: float,
    duration: float,
    output_path: str,
    use_blurred_bg: bool = True,
    anti_copyright: bool = True,
    logo_removal: str = "top-left"
) -> bool:
    """
    Turbo render with ultrafast x264 preset, multi-threading, and Anti-Copyright Audio/Video Shield.
    """
    video_path = resolve_video_path(video_path)
    filter_complex = build_ffmpeg_filter(
        use_blurred_bg=use_blurred_bg,
        anti_copyright=anti_copyright,
        logo_removal=logo_removal
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start_time:.2f}",
        "-t", f"{duration:.2f}",
        "-i", video_path,
        "-loop", "1",
        "-t", f"{duration:.2f}",
        "-i", overlay_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]"
    ]

    if anti_copyright:
        # Alter audio acoustic fingerprint without altering duration or tempo (+2.5% pitch shift + EQ)
        audio_filter = "asetrate=48000*1.025,aresample=48000,atempo=1/1.025,equalizer=f=1200:width_type=h:width=250:g=1.2"
        cmd.extend([
            "-map", "0:a?",
            "-filter:a", audio_filter,
            "-c:a", "aac",
            "-b:a", "128k"
        ])
    else:
        cmd.extend([
            "-map", "0:a?",
            "-c:a", "aac",
            "-b:a", "128k"
        ])

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-tune", "fastdecode",
        "-threads", "0",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ])

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg error] {e.stderr}")
        return False

def parse_episode_number(filename: str) -> str:
    match = re.search(r'(?:ep|episode)[^\d]*(\d+)', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    digits = re.findall(r'\d+', filename)
    if digits:
        return digits[0]
    return "1"

def _render_part_task(task_data: dict) -> Optional[dict]:
    """
    Worker task executed in parallel thread pool.
    """
    video_path = resolve_video_path(task_data["video_path"])
    overlay_path = task_data["overlay_path"]
    start_time = task_data["start_time"]
    duration = task_data["duration"]
    output_path = task_data["output_path"]
    clip_name = task_data["clip_name"]
    part_num = task_data["part_num"]
    use_blurred_bg = task_data["use_blurred_bg"]
    anti_copyright = task_data.get("anti_copyright", True)
    logo_removal = task_data.get("logo_removal", "top-left")

    success = render_single_clip(
        video_path=video_path,
        overlay_path=overlay_path,
        start_time=start_time,
        duration=duration,
        output_path=output_path,
        use_blurred_bg=use_blurred_bg,
        anti_copyright=anti_copyright,
        logo_removal=logo_removal
    )

    # Cleanup temporary overlay
    if os.path.exists(overlay_path):
        try:
            os.remove(overlay_path)
        except Exception:
            pass

    out_file = Path(output_path)
    final_file = Path(task_data.get("final_path", output_path))

    if success and out_file.exists():
        try:
            # Atomic rename from .tmp to final filename
            if out_file != final_file:
                shutil.move(str(out_file), str(final_file))
        except Exception as e:
            print(f"[Rename error] {e}")

        if final_file.exists():
            thumb_name = f"{final_file.stem}_thumb.jpg"
            thumb_path = CLIPS_DIR / thumb_name
            thumb_url = None

            # Attach Daily Thumbnail for Instagram & YouTube if present
            if DAILY_THUMBNAIL_PATH.exists():
                try:
                    generate_part_thumbnail(part_num, str(thumb_path), add_part_badge=False)
                    if thumb_path.exists():
                        thumb_url = f"/clips_media/{thumb_name}"
                except Exception as te:
                    print(f"[Thumbnail Error] {te}")

            return {
                "part": part_num,
                "filename": clip_name,
                "path": str(final_file),
                "thumbnail_url": thumb_url,
                "duration": round(duration, 1),
                "size_mb": round(final_file.stat().st_size / (1024 * 1024), 2)
            }
    return None

def process_episode_into_shorts(
    job_id: str,
    video_path: str,
    episode_num: str,
    template_path: Optional[str] = None,
    clip_duration: int = DEFAULT_CLIP_DURATION,
    start_part: int = 1,
    max_parts: Optional[int] = None,
    use_blurred_bg: bool = True,
    auto_schedule: bool = True,
    anti_copyright: bool = True,
    skip_intro_seconds: int = 75,
    skip_outro_seconds: int = 45,
    logo_removal: str = "top-left"
):
    """
    Parallel multi-threaded worker that slices episode into 30s clips at blazing speed,
    with built-in Anti-Copyright Shield (skips title song, removes watermarks, alters audio fingerprint).
    """
    video_path = resolve_video_path(video_path)
    job = JOBS[job_id]
    job["status"] = "processing"
    job["start_time"] = time.time()

    try:
        info = get_video_info(video_path)
        total_duration = info["duration"]
        if total_duration <= 0:
            job["status"] = "error"
            job["error"] = "Could not read video duration."
            return

        # Anti-Copyright: Skip intro title song & outro credits if requested
        intro_offset = max(0, skip_intro_seconds) if anti_copyright else 0
        outro_offset = max(0, skip_outro_seconds) if anti_copyright else 0

        usable_duration = total_duration - intro_offset - outro_offset
        if usable_duration <= clip_duration:
            usable_duration = total_duration
            intro_offset = 0
            outro_offset = 0

        total_possible_parts = math.ceil(usable_duration / clip_duration)
        if max_parts and max_parts > 0:
            parts_to_generate = min(total_possible_parts, max_parts)
        else:
            parts_to_generate = total_possible_parts

        job["total_parts"] = parts_to_generate
        job["clips"] = []

        temp_dir = INPUTS_DIR / f"temp_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        for idx in range(parts_to_generate):
            current_part_num = start_part + idx
            start_time_offset = intro_offset + (idx * clip_duration)
            actual_duration = min(clip_duration, (total_duration - outro_offset) - start_time_offset)

            if actual_duration <= 2.0:
                continue

            # Generate overlay from RAM cache
            overlay_img = generate_part_overlay(
                episode_num=episode_num,
                part_num=current_part_num,
                custom_template_path=template_path
            )
            overlay_file = temp_dir / f"overlay_part_{current_part_num}.png"
            overlay_img.save(str(overlay_file), "PNG")

            clip_name = f"tmkoc_ep{episode_num}_part{current_part_num}.mp4"
            final_output_file = CLIPS_DIR / clip_name
            tmp_output_file = CLIPS_DIR / f".tmp_{clip_name}"

            tasks.append({
                "video_path": video_path,
                "overlay_path": str(overlay_file),
                "start_time": start_time_offset,
                "duration": actual_duration,
                "output_path": str(tmp_output_file),
                "final_path": str(final_output_file),
                "clip_name": clip_name,
                "part_num": current_part_num,
                "use_blurred_bg": use_blurred_bg,
                "anti_copyright": anti_copyright,
                "logo_removal": logo_removal
            })

        # Execute tasks in parallel across CPU cores
        completed_count = 0
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            futures = [executor.submit(_render_part_task, t) for t in tasks]
            for future in as_completed(futures):
                if job.get("cancel_requested"):
                    job["status"] = "cancelled"
                    return

                res = future.result()
                if res:
                    job["clips"].append(res)
                    # Keep sorted by part
                    job["clips"].sort(key=lambda x: x["part"])

                completed_count += 1
                job["current_part"] = res["part"] if res else completed_count
                job["progress"] = round((completed_count / len(tasks)) * 100, 1)

        try:
            temp_dir.rmdir()
        except Exception:
            pass

        job["progress"] = 100.0
        job["status"] = "completed"
        job["end_time"] = time.time()
        job["elapsed_sec"] = round(job["end_time"] - job["start_time"], 1)

        print(f"[TURBO RENDER] Finished {len(job['clips'])} parts in {job['elapsed_sec']}s!")

        # Auto-schedule in 5-minute queue
        if auto_schedule and job["clips"]:
            from app.scheduler import scheduler_instance
            scheduler_instance.schedule_clips(
                clips=job["clips"],
                episode_num=episode_num,
                interval_minutes=DEFAULT_INTERVAL_MINUTES
            )

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        print(f"[Processor Exception] {e}")

def start_processing_job(
    video_path: str,
    episode_num: str,
    template_path: Optional[str] = None,
    clip_duration: int = DEFAULT_CLIP_DURATION,
    start_part: int = 1,
    max_parts: Optional[int] = None,
    use_blurred_bg: bool = True,
    auto_schedule: bool = True,
    anti_copyright: bool = True,
    skip_intro_seconds: int = 75,
    skip_outro_seconds: int = 45,
    logo_removal: str = "top-left"
) -> str:
    job_id = f"job_{int(time.time())}_{episode_num}"
    JOBS[job_id] = {
        "job_id": job_id,
        "episode_num": episode_num,
        "video_path": video_path,
        "status": "queued",
        "progress": 0.0,
        "current_part": start_part,
        "total_parts": 0,
        "clips": [],
        "created_at": time.time(),
        "error": None,
        "anti_copyright": anti_copyright,
        "skip_intro_seconds": skip_intro_seconds,
        "skip_outro_seconds": skip_outro_seconds,
        "logo_removal": logo_removal
    }

    thread = threading.Thread(
        target=process_episode_into_shorts,
        kwargs={
            "job_id": job_id,
            "video_path": video_path,
            "episode_num": episode_num,
            "template_path": template_path,
            "clip_duration": clip_duration,
            "start_part": start_part,
            "max_parts": max_parts,
            "use_blurred_bg": use_blurred_bg,
            "auto_schedule": auto_schedule,
            "anti_copyright": anti_copyright,
            "skip_intro_seconds": skip_intro_seconds,
            "skip_outro_seconds": skip_outro_seconds,
            "logo_removal": logo_removal
        },
        daemon=True
    )
    thread.start()
    return job_id

def get_current_active_job() -> Optional[Dict[str, Any]]:
    """
    Returns the currently active slicing job (processing or queued),
    or the most recently completed job if within 15 minutes.
    """
    for j in reversed(list(JOBS.values())):
        if j.get("status") in ("processing", "queued"):
            return j
    if JOBS:
        latest = list(JOBS.values())[-1]
        if time.time() - latest.get("created_at", 0) < 900:
            return latest
    return None

# --- High-Frequency Watch Folder Worker ---
def watch_folder_worker():
    global PROCESSED_WATCHER_FILES
    while WATCHER_ENABLED:
        try:
            for ext in ["*.mp4", "*.mkv", "*.mov", "*.avi"]:
                for file_path in RAW_VIDEOS_DIR.glob(ext):
                    if file_path.name.startswith("processed_"):
                        continue
                    if file_path.name in PROCESSED_WATCHER_FILES:
                        continue

                    # Instant size stability check (0.6s)
                    size1 = file_path.stat().st_size
                    time.sleep(0.6)
                    size2 = file_path.stat().st_size
                    if size1 != size2 or size1 < 100000:
                        continue

                    print(f"[Watch Folder] Instant trigger: {file_path.name}")
                    PROCESSED_WATCHER_FILES.add(file_path.name)

                    ep_num = parse_episode_number(file_path.name)
                    print(f"[Watch Folder] Blazing fast render started for Episode #{ep_num}...")

                    dest = PROCESSED_RAW_DIR / file_path.name
                    try:
                        shutil.move(str(file_path), str(dest))
                        actual_video_path = str(dest)
                    except Exception:
                        actual_video_path = str(file_path)

                    start_processing_job(
                        video_path=actual_video_path,
                        episode_num=ep_num,
                        clip_duration=DEFAULT_CLIP_DURATION,
                        start_part=1,
                        use_blurred_bg=True,
                        auto_schedule=True,
                        anti_copyright=True,
                        skip_intro_seconds=75,
                        skip_outro_seconds=45,
                        logo_removal="top-left"
                    )

        except Exception as e:
            print(f"[Watcher Error] {e}")

        time.sleep(0.8)

def start_folder_watcher():
    watcher_thread = threading.Thread(target=watch_folder_worker, daemon=True)
    watcher_thread.start()
    print("[Watch Folder] High-frequency watcher active (0.8s check).")
