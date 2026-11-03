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
    generate_part_overlay
)
from app.scheduler import scheduler_instance

app = FastAPI(title="TMKOC Shorts Automator")

# Mount static and storage folders
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/clips_media", StaticFiles(directory=str(CLIPS_DIR)), name="clips_media")
app.mount("/ready_media", StaticFiles(directory=str(READY_DIR)), name="ready_media")

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

@app.get("/api/clips")
async def list_clips():
    clips = []
    for file in sorted(CLIPS_DIR.glob("*.mp4")):
        clips.append({
            "filename": file.name,
            "url": f"/clips_media/{file.name}",
            "size_mb": round(file.stat().st_size / (1024 * 1024), 2),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file.stat().st_ctime))
        })
    return clips

@app.get("/api/download-all-zip")
async def download_all_zip():
    zip_path = STORAGE_DIR / "tmkoc_shorts_pack.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in CLIPS_DIR.glob("*.mp4"):
            zipf.write(file, arcname=file.name)

    return FileResponse(
        path=str(zip_path),
        filename="tmkoc_shorts_pack.zip",
        media_type="application/zip"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
