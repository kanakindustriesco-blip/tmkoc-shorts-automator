import os
import shutil
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

from app.config import READY_DIR

def publish_to_local_folder(clip_path: str, episode_num: str, part_num: int) -> Dict[str, Any]:
    """
    Publishes clip to the local 'ready_to_publish' folder with ready-to-copy social media title, tags, and description.
    """
    src = Path(clip_path)
    if not src.exists():
        return {"success": False, "error": f"File not found: {clip_path}"}

    dest_video = READY_DIR / src.name
    shutil.copy2(src, dest_video)

    # Generate metadata with viral tags for TMKOC
    title = f"TMKOC Episode {episode_num} | Part {part_num} 😂 #tmkoc #shorts #comedy"
    description = (
        f"Taarak Mehta Ka Ooltah Chashmah - Episode {episode_num} (Part {part_num})\n"
        f"Follow & Subscribe for Part {part_num + 1}!\n\n"
        f"#tmkoc #taarakmehta #jethalal #babitaji #dayabhabhi #comedy #shorts #reels #viral"
    )
    tags = ["tmkoc", "taarak mehta", "jethalal", "babita", "daya", "comedy", "shorts", "reels", "funny"]

    meta_file = READY_DIR / f"{src.stem}_info.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({
            "episode": episode_num,
            "part": part_num,
            "video_file": str(dest_video),
            "title": title,
            "description": description,
            "tags": tags,
            "published_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }, f, indent=2)

    return {
        "success": True,
        "destination": str(dest_video),
        "title": title,
        "description": description
    }

def publish_to_youtube_shorts(clip_path: str, title: str, description: str, tags: list) -> Dict[str, Any]:
    """
    Stub for YouTube Shorts Data API v3 upload.
    If client_secrets.json exists, uploads directly; otherwise returns instructions.
    """
    return {
        "success": False,
        "message": "YouTube OAuth not configured. Clip placed in ready_to_publish folder for 1-click upload."
    }

def publish_to_instagram(clip_path: str, caption: str) -> Dict[str, Any]:
    """
    Stub for Instagram Reels upload.
    """
    return {
        "success": False,
        "message": "Instagram credentials not configured. Clip placed in ready_to_publish folder."
    }
