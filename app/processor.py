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

from app.config import (
    CLIPS_DIR,
    INPUTS_DIR,
    RAW_VIDEOS_DIR,
    PROCESSED_RAW_DIR,
    TARGET_WIDTH,
    TARGET_HEIGHT,
    VIDEO_WINDOW_Y_START,
    VIDEO_WINDOW_HEIGHT,
    DEFAULT_CLIP_DURATION,
    DEFAULT_INTERVAL_MINUTES
)
from app.template_engine import generate_part_overlay

# Global jobs registry
JOBS: Dict[str, Dict[str, Any]] = {}
WATCHER_ENABLED = True

def get_video_info(video_path: str) -> Dict[str, Any]:
    """
    Extracts duration, dimensions, fps, audio presence using ffprobe.
    """
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
    """
    Extracts a frame from video for preview.
    """
    if not output_path:
        output_path = str(Path(video_path).parent / "sample_frame.jpg")
    
    cmd = [
        "ffmpeg",
        "-y",
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

def build_ffmpeg_filter(use_blurred_bg: bool = True) -> str:
    """
    Lightning-fast filter complex:
    Centers 16:9 video between y=623 and 1241 in the template,
    with an optimized downscaled blurred background underneath.
    """
    if use_blurred_bg:
        # Fast blur by downscaling background to 180x320, light boxblur, then upscaling
        filter_str = (
            f"[0:v]split=2[v_bg][v_fg];"
            f"[v_bg]scale=180:320:force_original_aspect_ratio=increase,crop=180:320,boxblur=5:2,scale={TARGET_WIDTH}:{TARGET_HEIGHT}[blurred];"
            f"[v_fg]scale={TARGET_WIDTH}:{VIDEO_WINDOW_HEIGHT}:force_original_aspect_ratio=decrease[fg];"
            f"[blurred][fg]overlay=(W-w)/2:{VIDEO_WINDOW_Y_START}[composed];"
            f"[composed][1:v]overlay=0:0[outv]"
        )
    else:
        # Black background fill
        filter_str = (
            f"[0:v]scale={TARGET_WIDTH}:{VIDEO_WINDOW_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:{VIDEO_WINDOW_Y_START}:color=black[padded];"
            f"[padded][1:v]overlay=0:0[outv]"
        )
    return filter_str

def render_single_clip(
    video_path: str,
    overlay_path: str,
    start_time: float,
    duration: float,
    output_path: str,
    use_blurred_bg: bool = True
) -> bool:
    """
    Renders one 30-second vertical clip with official TMKOC overlay.
    """
    filter_complex = build_ffmpeg_filter(use_blurred_bg=use_blurred_bg)

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
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FFmpeg render error] {e.stderr}")
        return False

def parse_episode_number(filename: str) -> str:
    """
    Extracts episode number from strings like 'TMKOC_Ep542.mp4', 'ep-1200', 'Episode 400'.
    """
    match = re.search(r'(?:ep|episode)[^\d]*(\d+)', filename, re.IGNORECASE)
    if match:
        return match.group(1)
    digits = re.findall(r'\d+', filename)
    if digits:
        return digits[0]
    return "1"

def process_episode_into_shorts(
    job_id: str,
    video_path: str,
    episode_num: str,
    template_path: Optional[str] = None,
    clip_duration: int = DEFAULT_CLIP_DURATION,
    start_part: int = 1,
    max_parts: Optional[int] = None,
    use_blurred_bg: bool = True,
    auto_schedule: bool = True
):
    """
    Background worker that slices episode and renders 30s clips with official TMKOC template.
    """
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

        total_possible_parts = math.ceil(total_duration / clip_duration)
        if max_parts and max_parts > 0:
            parts_to_generate = min(total_possible_parts, max_parts)
        else:
            parts_to_generate = total_possible_parts

        job["total_parts"] = parts_to_generate
        job["clips"] = []

        temp_dir = INPUTS_DIR / f"temp_{job_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        for idx in range(parts_to_generate):
            if job.get("cancel_requested"):
                job["status"] = "cancelled"
                return

            current_part_num = start_part + idx
            start_time_offset = idx * clip_duration
            actual_duration = min(clip_duration, total_duration - start_time_offset)

            if actual_duration <= 2.0:
                continue

            job["current_part"] = current_part_num
            job["current_index"] = idx + 1
            job["progress"] = round(((idx) / parts_to_generate) * 100, 1)

            # Generate overlay for this part with Episode & Part in pill boxes
            overlay_img = generate_part_overlay(
                episode_num=episode_num,
                part_num=current_part_num,
                custom_template_path=template_path
            )
            overlay_file = temp_dir / f"overlay_part_{current_part_num}.png"
            overlay_img.save(str(overlay_file), "PNG")

            # Output filename
            clip_name = f"tmkoc_ep{episode_num}_part{current_part_num}.mp4"
            output_file = CLIPS_DIR / clip_name

            # Render clip
            success = render_single_clip(
                video_path=video_path,
                overlay_path=str(overlay_file),
                start_time=start_time_offset,
                duration=actual_duration,
                output_path=str(output_file),
                use_blurred_bg=use_blurred_bg
            )

            if overlay_file.exists():
                try:
                    overlay_file.unlink()
                except Exception:
                    pass

            if success and output_file.exists():
                job["clips"].append({
                    "part": current_part_num,
                    "filename": clip_name,
                    "path": str(output_file),
                    "duration": round(actual_duration, 1),
                    "size_mb": round(output_file.stat().st_size / (1024 * 1024), 2)
                })

        try:
            temp_dir.rmdir()
        except Exception:
            pass

        job["progress"] = 100.0
        job["status"] = "completed"
        job["end_time"] = time.time()
        job["elapsed_sec"] = round(job["end_time"] - job["start_time"], 1)

        # Auto-schedule if requested
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
    auto_schedule: bool = True
) -> str:
    """
    Spawns background slicing and conversion thread.
    """
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
        "error": None
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
            "auto_schedule": auto_schedule
        },
        daemon=True
    )
    thread.start()
    return job_id

# --- Automatic Watch Folder Background Loop ---
def watch_folder_worker():
    """
    Monitors storage/raw_videos.
    When a raw episode file is dropped, automatically processes it!
    """
    processed_files = set()
    while WATCHER_ENABLED:
        try:
            for ext in ["*.mp4", "*.mkv", "*.mov", "*.avi"]:
                for file_path in RAW_VIDEOS_DIR.glob(ext):
                    if file_path.name.startswith("processed_"):
                        continue
                    if file_path in processed_files:
                        continue

                    # Check if file writing is complete (size stable for 1.5s)
                    size1 = file_path.stat().st_size
                    time.sleep(1.5)
                    size2 = file_path.stat().st_size
                    if size1 != size2 or size1 < 100000:
                        continue

                    print(f"[Watch Folder] New episode detected: {file_path.name}")
                    processed_files.add(file_path)

                    ep_num = parse_episode_number(file_path.name)
                    print(f"[Watch Folder] Auto-processing Episode #{ep_num}...")

                    # Start job
                    start_processing_job(
                        video_path=str(file_path),
                        episode_num=ep_num,
                        clip_duration=DEFAULT_CLIP_DURATION,
                        start_part=1,
                        use_blurred_bg=True,
                        auto_schedule=True
                    )

                    # Move file to processed directory
                    dest = PROCESSED_RAW_DIR / file_path.name
                    try:
                        shutil.move(str(file_path), str(dest))
                    except Exception:
                        pass

        except Exception as e:
            print(f"[Watcher Error] {e}")

        time.sleep(3)

def start_folder_watcher():
    watcher_thread = threading.Thread(target=watch_folder_worker, daemon=True)
    watcher_thread.start()
    print("[Watch Folder] Background folder watcher started.")
