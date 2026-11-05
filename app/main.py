import os
import shutil
import time
import zipfile
import subprocess
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    BASE_DIR,
    STORAGE_DIR,
    INPUTS_DIR,
    RAW_VIDEOS_DIR,
    PROCESSED_RAW_DIR,
    CLIPS_DIR,
    READY_DIR,
    THUMBNAILS_DIR,
    DAILY_THUMBNAIL_PATH,
    STATIC_DIR,
    TEMPLATES_DIR,
    HTML_TEMPLATES_DIR,
    DEFAULT_CLIP_DURATION,
    DEFAULT_INTERVAL_MINUTES,
    SERVER_HOST,
    SERVER_PORT
)
from app.processor import (
    JOBS,
    get_video_info,
    extract_sample_frame,
    start_processing_job,
    start_folder_watcher,
    parse_episode_number
)
from app.template_engine import (
    generate_preview_mockup,
    generate_part_overlay,
    process_daily_thumbnail,
    generate_part_thumbnail
)
from app.uploader import (
    get_social_settings,
    save_social_settings,
    configure_instagram,
    disconnect_instagram,
    configure_youtube_secrets,
    authenticate_youtube,
    disconnect_youtube,
    publish_to_instagram,
    publish_to_youtube_shorts,
    get_clip_metadata,
    get_upload_history
)
from app.scheduler import scheduler_instance

app = FastAPI(title="TMKOC Shorts Automator")

# Mount static and storage folders
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/clips_media", StaticFiles(directory=str(CLIPS_DIR)), name="clips_media")
app.mount("/ready_media", StaticFiles(directory=str(READY_DIR)), name="ready_media")
app.mount("/thumbnails_media", StaticFiles(directory=str(THUMBNAILS_DIR)), name="thumbnails_media")

# Start background folder watcher on app startup
@app.on_event("startup")
def startup_event():
    start_folder_watcher()

# --- HTML Web App ---
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = HTML_TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h3>Dashboard loading... Please wait.</h3>")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# --- API Models ---
class PreviewRequest(BaseModel):
    episode_num: str = "542"
    part_num: int = 1
    template_path: Optional[str] = None
    sample_frame_path: Optional[str] = None

class LocalFileRequest(BaseModel):
    file_path: str

class ProcessRequest(BaseModel):
    video_path: str
    episode_num: str
    template_path: Optional[str] = None
    clip_duration: int = DEFAULT_CLIP_DURATION
    start_part: int = 1
    max_parts: Optional[int] = None
    use_blurred_bg: bool = True
    auto_schedule: bool = True

class ScheduleRequest(BaseModel):
    episode_num: str
    clips: List[dict]
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES
    start_delay_seconds: int = 0

class InstagramConnectRequest(BaseModel):
    username: str
    password: Optional[str] = None
    auto_upload: Optional[bool] = None

class SocialToggleRequest(BaseModel):
    platform: str  # "instagram" or "youtube"
    auto_upload: Optional[bool] = None
    privacy_status: Optional[str] = None

class SingleUploadRequest(BaseModel):
    filename: str
    platform: str  # "instagram", "youtube", or "both"
    custom_caption: Optional[str] = None
    privacy_status: Optional[str] = None

# --- Endpoints ---
@app.post("/api/preview")
async def generate_preview(req: PreviewRequest):
    try:
        preview_output = STATIC_DIR / "preview_cache.jpg"
        generate_preview_mockup(
            episode_num=req.episode_num,
            part_num=req.part_num,
            custom_template_path=req.template_path,
            sample_frame_path=req.sample_frame_path,
            output_path=str(preview_output)
        )
        return {
            "success": True,
            "preview_url": f"/static/preview_cache.jpg?t={int(time.time() * 1000)}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/select-local-video")
async def select_local_video(req: LocalFileRequest):
    clean_path = req.file_path.strip().strip('"').strip("'")
    path_obj = Path(clean_path)
    if not path_obj.exists() or not path_obj.is_file():
        raise HTTPException(status_code=400, detail="File nahi mili. Kripya valid local file path enter karein.")

    info = get_video_info(clean_path)
    sample_frame = STATIC_DIR / "current_sample_frame.jpg"
    extract_sample_frame(clean_path, timestamp=15.0, output_path=str(sample_frame))

    est_parts = int(info["duration"] // DEFAULT_CLIP_DURATION) + (1 if info["duration"] % DEFAULT_CLIP_DURATION > 2 else 0)
    detected_ep = parse_episode_number(path_obj.name)

    return {
        "success": True,
        "video_path": clean_path,
        "filename": path_obj.name,
        "detected_episode": detected_ep,
        "duration": round(info["duration"], 1),
        "duration_str": time.strftime("%H:%M:%S", time.gmtime(info["duration"])),
        "width": info["width"],
        "height": info["height"],
        "estimated_parts": est_parts,
        "sample_frame_url": f"/static/current_sample_frame.jpg?t={int(time.time())}" if sample_frame.exists() else None
    }

@app.post("/api/upload-raw")
async def upload_raw_video(file: UploadFile = File(...)):
    """
    Dedicated Raw Video Drop: Saves file and immediately triggers the full automated pipeline!
    """
    dest = RAW_VIDEOS_DIR / file.filename
    with open(dest, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ep_num = parse_episode_number(file.filename)
    info = get_video_info(str(dest))

    # Trigger job
    job_id = start_processing_job(
        video_path=str(dest),
        episode_num=ep_num,
        clip_duration=DEFAULT_CLIP_DURATION,
        start_part=1,
        use_blurred_bg=True,
        auto_schedule=True
    )

    return {
        "success": True,
        "message": f"Raw episode uploaded! Processing Episode #{ep_num} started automatically.",
        "job_id": job_id,
        "episode_num": ep_num,
        "filename": file.filename,
        "duration_str": time.strftime("%H:%M:%S", time.gmtime(info["duration"]))
    }

@app.post("/api/open-raw-folder")
async def open_raw_folder():
    """
    Opens the raw videos folder in Windows File Explorer.
    """
    folder_str = str(RAW_VIDEOS_DIR.resolve())
    try:
        subprocess.Popen(["explorer.exe", folder_str])
        return {"success": True, "path": folder_str}
    except Exception as e:
        return {"success": False, "error": str(e), "path": folder_str}

@app.get("/api/folder-paths")
async def get_folder_paths():
    return {
        "raw_videos_folder": str(RAW_VIDEOS_DIR.resolve()),
        "clips_folder": str(CLIPS_DIR.resolve()),
        "ready_folder": str(READY_DIR.resolve())
    }

@app.post("/api/start-process")
async def start_process(req: ProcessRequest):
    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=400, detail="Video file not found.")

    job_id = start_processing_job(
        video_path=req.video_path,
        episode_num=req.episode_num,
        template_path=req.template_path,
        clip_duration=req.clip_duration,
        start_part=req.start_part,
        max_parts=req.max_parts,
        use_blurred_bg=req.use_blurred_bg,
        auto_schedule=req.auto_schedule
    )

    return {
        "success": True,
        "job_id": job_id
    }

@app.get("/api/job-status/{job_id}")
async def get_job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/schedule")
async def schedule_clips_endpoint(req: ScheduleRequest):
    scheduled_items = scheduler_instance.schedule_clips(
        clips=req.clips,
        episode_num=req.episode_num,
        interval_minutes=req.interval_minutes,
        start_delay_seconds=req.start_delay_seconds
    )
    return {
        "success": True,
        "count": len(scheduled_items),
        "items": scheduled_items
    }

@app.get("/api/scheduler-status")
async def get_scheduler_status():
    return scheduler_instance.get_queue_status()

@app.post("/api/scheduler-clear")
async def clear_scheduler():
    scheduler_instance.clear_queue()
    return {"success": True, "message": "Queue cleared."}

# --- Daily Thumbnail Endpoints (Instagram & YouTube) ---
@app.post("/api/upload-daily-thumbnail")
async def upload_daily_thumbnail(file: UploadFile = File(...)):
    """
    Uploads today's thumbnail, auto-fits to 1080x1920 (9:16 vertical),
    and saves as the active daily thumbnail for Instagram & YouTube.
    """
    temp_upload = THUMBNAILS_DIR / f"temp_{int(time.time())}_{file.filename}"
    with open(temp_upload, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        final_thumb = process_daily_thumbnail(str(temp_upload), str(DAILY_THUMBNAIL_PATH))
        if temp_upload.exists():
            temp_upload.unlink()
        return {
            "success": True,
            "message": "Daily thumbnail updated successfully for Instagram & YouTube!",
            "thumbnail_url": f"/thumbnails_media/daily_thumbnail.jpg?t={int(time.time() * 1000)}"
        }
    except Exception as e:
        if temp_upload.exists():
            temp_upload.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to process thumbnail: {str(e)}")

@app.get("/api/daily-thumbnail")
async def get_daily_thumbnail():
    """
    Returns current active daily thumbnail status.
    """
    if DAILY_THUMBNAIL_PATH.exists():
        return {
            "has_thumbnail": True,
            "thumbnail_url": f"/thumbnails_media/daily_thumbnail.jpg?t={int(DAILY_THUMBNAIL_PATH.stat().st_mtime)}",
            "updated_at": time.strftime("%Y-%m-%d %I:%M %p", time.localtime(DAILY_THUMBNAIL_PATH.stat().st_mtime))
        }
    return {"has_thumbnail": False, "thumbnail_url": None}

@app.post("/api/apply-thumbnail-to-all")
async def apply_thumbnail_to_all_clips():
    """
    Applies the active daily thumbnail to all existing clips without needing to re-render videos!
    """
    if not DAILY_THUMBNAIL_PATH.exists():
        raise HTTPException(status_code=400, detail="Pehle daily thumbnail upload karein!")

    count = 0
    import re
    for mp4_file in CLIPS_DIR.glob("*.mp4"):
        if mp4_file.name.startswith(".tmp_"):
            continue
        part_match = re.search(r'part(\d+)', mp4_file.name, re.IGNORECASE)
        part_num = int(part_match.group(1)) if part_match else 1
        thumb_file = CLIPS_DIR / f"{mp4_file.stem}_thumb.jpg"
        generate_part_thumbnail(part_num, str(thumb_file), add_part_badge=False)
        count += 1

    return {"success": True, "message": f"Thumbnail applied to {count} clips successfully!", "count": count}

# --- Social Media Integration Endpoints ---

@app.get("/api/social/settings")
async def get_social_media_settings():
    return get_social_settings()

@app.post("/api/social/instagram/connect")
async def connect_instagram_account(req: InstagramConnectRequest):
    res = configure_instagram(username=req.username, password=req.password, auto_upload=req.auto_upload)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to connect Instagram."))
    return res

@app.post("/api/social/instagram/disconnect")
async def disconnect_instagram_account():
    return disconnect_instagram()

@app.post("/api/social/youtube/upload-secrets")
async def upload_youtube_secrets(file: UploadFile = File(...)):
    content = await file.read()
    try:
        content_str = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid file encoding. Must be a JSON file.")
    
    res = configure_youtube_secrets(content_str)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Invalid client_secrets.json"))
    return res

@app.post("/api/social/youtube/connect")
async def connect_youtube_account():
    res = authenticate_youtube()
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "YouTube OAuth failed."))
    return res

@app.post("/api/social/youtube/disconnect")
async def disconnect_youtube_account():
    return disconnect_youtube()

@app.post("/api/social/toggle")
async def toggle_social_settings(req: SocialToggleRequest):
    settings = get_social_settings()
    if req.platform == "instagram":
        if req.auto_upload is not None:
            settings["instagram"]["auto_upload"] = req.auto_upload
    elif req.platform == "youtube":
        if req.auto_upload is not None:
            settings["youtube"]["auto_upload"] = req.auto_upload
        if req.privacy_status:
            settings["youtube"]["privacy_status"] = req.privacy_status
    save_social_settings(settings)
    return {"success": True, "settings": settings}

@app.get("/api/social/metadata/{filename}")
async def get_metadata_for_clip(filename: str):
    import re
    match = re.search(r'ep(\d+)_part(\d+)', filename, re.IGNORECASE)
    ep_no = match.group(1) if match else "1"
    part_no = int(match.group(2)) if match else 1
    return get_clip_metadata(ep_no, part_no)

@app.post("/api/social/upload-single")
async def upload_single_clip(req: SingleUploadRequest):
    clip_path = CLIPS_DIR / req.filename
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail=f"Clip not found: {req.filename}")

    import re
    match = re.search(r'ep(\d+)_part(\d+)', req.filename, re.IGNORECASE)
    ep_no = match.group(1) if match else "1"
    part_no = int(match.group(2)) if match else 1

    meta = get_clip_metadata(ep_no, part_no)
    caption = req.custom_caption or meta["description"]

    # Thumbnail resolution
    clip_thumb = CLIPS_DIR / f"{clip_path.stem}_thumb.jpg"
    thumb_path = str(clip_thumb) if clip_thumb.exists() else (str(DAILY_THUMBNAIL_PATH) if DAILY_THUMBNAIL_PATH.exists() else None)

    results = {}

    if req.platform in ["instagram", "both"]:
        ig_res = publish_to_instagram(str(clip_path), caption=caption, thumb_path=thumb_path)
        results["instagram"] = ig_res

    if req.platform in ["youtube", "both"]:
        yt_res = publish_to_youtube_shorts(
            clip_path=str(clip_path),
            title=meta["title"],
            description=caption,
            tags=meta["tags"],
            thumb_path=thumb_path,
            privacy_status=req.privacy_status
        )
        results["youtube"] = yt_res

    has_error = any(not r.get("success") for r in results.values())
    return {
        "success": not has_error,
        "results": results,
        "filename": req.filename
    }

@app.get("/api/social/history")
async def get_social_history():
    return get_upload_history()

def natural_clip_sort_key(path: Path):
    import re
    # Extract episode and part number
    match = re.search(r'ep(\d+)_part(\d+)', path.name, re.IGNORECASE)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    # Fallback to part number or any number
    part_match = re.search(r'part(\d+)', path.name, re.IGNORECASE)
    if part_match:
        return (0, int(part_match.group(1)))
    digits = re.findall(r'\d+', path.name)
    return (0, int(digits[0]) if digits else 0, path.name)

@app.get("/api/clips")
async def list_clips():
    import re
    clips = []
    # Natural sort by episode and part number
    for file in sorted(CLIPS_DIR.glob("*.mp4"), key=natural_clip_sort_key):
        if file.name.startswith(".tmp_"):
            continue

        match = re.search(r'ep(\d+)_part(\d+)', file.name, re.IGNORECASE)
        ep_no = match.group(1) if match else "1"
        part_no = int(match.group(2)) if match else 1

        # Check if clip-specific thumbnail or daily thumbnail exists
        clip_thumb = CLIPS_DIR / f"{file.stem}_thumb.jpg"
        if clip_thumb.exists():
            thumb_url = f"/clips_media/{clip_thumb.name}?t={int(clip_thumb.stat().st_mtime)}"
        elif DAILY_THUMBNAIL_PATH.exists():
            thumb_url = f"/thumbnails_media/daily_thumbnail.jpg?t={int(DAILY_THUMBNAIL_PATH.stat().st_mtime)}"
        else:
            thumb_url = None

        clips.append({
            "filename": file.name,
            "display_title": f"Episode {ep_no} • Part {part_no}",
            "episode": ep_no,
            "part": part_no,
            "url": f"/clips_media/{file.name}",
            "thumbnail_url": thumb_url,
            "size_mb": round(file.stat().st_size / (1024 * 1024), 2),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file.stat().st_ctime))
        })
    return clips

@app.get("/api/download-all-zip")
async def download_all_zip():
    """
    Creates and downloads a zip of all rendered clips and their thumbnails.
    """
    zip_path = STORAGE_DIR / "tmkoc_shorts_pack.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in CLIPS_DIR.glob("*.mp4"):
            if not file.name.startswith(".tmp_"):
                zipf.write(file, arcname=file.name)
        # Include thumbnails in zip
        for thumb in CLIPS_DIR.glob("*_thumb.jpg"):
            zipf.write(thumb, arcname=f"thumbnails/{thumb.name}")
        if DAILY_THUMBNAIL_PATH.exists():
            zipf.write(DAILY_THUMBNAIL_PATH, arcname="thumbnails/daily_thumbnail.jpg")

    return FileResponse(
        path=str(zip_path),
        filename="tmkoc_shorts_pack.zip",
        media_type="application/zip"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
