import os
import shutil
import json
import time
import pickle
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.config import (
    READY_DIR,
    DAILY_THUMBNAIL_PATH,
    SOCIAL_SETTINGS_PATH,
    IG_SESSION_PATH,
    YT_SECRETS_PATH,
    YT_TOKEN_PATH,
    UPLOAD_HISTORY_PATH
)

# ----------------- Settings & History Helpers -----------------

def load_raw_social_settings() -> Dict[str, Any]:
    default_settings = {
        "instagram": {
            "username": "tmkoc.925781",
            "password": "",
            "is_connected": True,
            "auto_upload": False,
            "last_login": time.strftime("%Y-%m-%d %I:%M %p"),
            "last_upload": None
        },
        "youtube": {
            "has_secrets": False,
            "is_connected": False,
            "auto_upload": False,
            "privacy_status": "public",
            "last_upload": None
        }
    }
    if not SOCIAL_SETTINGS_PATH.exists():
        save_social_settings(default_settings)
        return default_settings

    try:
        with open(SOCIAL_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_settings["instagram"].update(data.get("instagram", {}))
            default_settings["youtube"].update(data.get("youtube", {}))
            default_settings["instagram"]["is_connected"] = bool(default_settings["instagram"].get("username"))
            default_settings["youtube"]["has_secrets"] = YT_SECRETS_PATH.exists()
            default_settings["youtube"]["is_connected"] = YT_TOKEN_PATH.exists()
            return default_settings
    except Exception:
        return default_settings

def get_social_settings() -> Dict[str, Any]:
    raw = load_raw_social_settings()
    clean = json.loads(json.dumps(raw))
    if "instagram" in clean and "password" in clean["instagram"]:
        del clean["instagram"]["password"]
    return clean

def save_social_settings(settings: Dict[str, Any]):
    with open(SOCIAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

def get_upload_history() -> List[Dict[str, Any]]:
    if not UPLOAD_HISTORY_PATH.exists():
        return []
    try:
        with open(UPLOAD_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def record_upload(platform: str, filename: str, status: str, url: Optional[str] = None, error: Optional[str] = None):
    history = get_upload_history()
    entry = {
        "id": f"up_{int(time.time())}_{platform.lower()}",
        "platform": platform,
        "filename": filename,
        "status": status,
        "url": url,
        "error": error,
        "timestamp": time.strftime("%Y-%m-%d %I:%M:%S %p")
    }
    history.insert(0, entry)
    # Keep last 100 entries
    history = history[:100]
    with open(UPLOAD_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

# ----------------- Instagram Integration -----------------

def _patch_instagrapi_publickeys():
    """
    Patches instagrapi's password_publickeys to fetch keys from accounts/login instead
    of deprecated qe/sync, fixing 'int() argument must be a string... not NoneType'.
    """
    try:
        from instagrapi import Client

        def patched_password_publickeys(self):
            try:
                resp = self.public.get("https://i.instagram.com/api/v1/accounts/login/")
                key_id = resp.headers.get("ig-set-password-encryption-key-id")
                pub_key = resp.headers.get("ig-set-password-encryption-pub-key")
                if key_id and pub_key:
                    return int(key_id), pub_key
            except Exception:
                pass

            resp = self.public.get("https://i.instagram.com/api/v1/qe/sync/")
            key_id = resp.headers.get("ig-set-password-encryption-key-id")
            pub_key = resp.headers.get("ig-set-password-encryption-pub-key")
            if not key_id or not pub_key:
                raise RuntimeError("Instagram public encryption keys unavailable. Please use Session ID login.")
            return int(key_id), pub_key

        Client.password_publickeys = patched_password_publickeys
    except Exception as e:
        print(f"[Instagram] Warning applying patch: {e}")

_patch_instagrapi_publickeys()

def get_instagram_client():
    from instagrapi import Client
    cl = Client()
    cl.delay_range = [1, 3]
    if IG_SESSION_PATH.exists():
        try:
            cl.load_settings(str(IG_SESSION_PATH))
        except Exception as e:
            print(f"[Instagram] Warning loading session: {e}")
    return cl

def configure_instagram(
    username: Optional[str] = None,
    password: Optional[str] = None,
    session_id: Optional[str] = None,
    auto_upload: Optional[bool] = None
) -> Dict[str, Any]:
    settings = get_social_settings()
    
    if auto_upload is not None:
        settings["instagram"]["auto_upload"] = bool(auto_upload)

    from instagrapi import Client
    cl = Client()
    cl.delay_range = [1, 3]

    # Mode 1: Connect via Instagram Session ID (Fastest, zero blocks, bypasses 2FA/app version issues)
    if session_id and session_id.strip():
        sid = session_id.strip()
        try:
            cl.login_by_sessionid(sid)
            cl.dump_settings(str(IG_SESSION_PATH))
            detected_user = cl.username or username or "instagram_user"
            settings["instagram"]["username"] = detected_user
            settings["instagram"]["is_connected"] = True
            settings["instagram"]["last_login"] = time.strftime("%Y-%m-%d %I:%M:%S %p")
            save_social_settings(settings)
            return {
                "success": True,
                "message": f"Successfully connected Instagram @{detected_user} via Session ID!",
                "username": detected_user
            }
        except Exception as e:
            return {"success": False, "error": f"Session ID invalid or expired: {str(e)}"}

    # Mode 2: Username & Password
    if not username:
        return {"success": False, "error": "Username or Session ID is required."}

    username = username.strip().lstrip("@")

    if not password and IG_SESSION_PATH.exists() and settings["instagram"].get("username") == username:
        # Just updating auto_upload or checking existing session
        save_social_settings(settings)
        return {"success": True, "message": f"Instagram session active for @{username}", "username": username}

    if not password:
        return {"success": False, "error": "Password or Session ID required to authenticate with Instagram."}

    try:
        # Attempt login
        logged_in = False
        try:
            logged_in = cl.login(username, password)
        except Exception as e_caa:
            print(f"[Instagram] CAA login fallback: {e_caa}")
            try:
                logged_in = cl.login_legacy(username, password)
            except Exception:
                raise e_caa

        if logged_in:
            cl.dump_settings(str(IG_SESSION_PATH))
            settings["instagram"]["username"] = username
            settings["instagram"]["is_connected"] = True
            settings["instagram"]["last_login"] = time.strftime("%Y-%m-%d %I:%M:%S %p")
            save_social_settings(settings)
            return {"success": True, "message": f"Successfully connected Instagram @{username}!", "username": username}
        else:
            return {"success": False, "error": "Login failed. Please check your username and password or use Session ID."}
    except Exception as e:
        err_msg = str(e)
        if "challenge_required" in err_msg.lower():
            err_msg = "Instagram checkpoint triggered. Please open the Instagram app on your phone to approve the login, or use the Session ID option."
        elif "bad_password" in err_msg.lower():
            err_msg = "Incorrect Instagram password."
        elif "out of date" in err_msg.lower():
            err_msg = "Instagram blocked mobile password login ('App out of date'). Please use the 'Session ID' tab — it connects in 10 seconds without password blocks!"
        return {"success": False, "error": err_msg}

def disconnect_instagram() -> Dict[str, Any]:
    if IG_SESSION_PATH.exists():
        try:
            os.remove(IG_SESSION_PATH)
        except Exception:
            pass
    settings = get_social_settings()
    settings["instagram"]["is_connected"] = False
    settings["instagram"]["auto_upload"] = False
    save_social_settings(settings)
    return {"success": True, "message": "Instagram disconnected."}

def publish_to_instagram(clip_path: str, caption: str, thumb_path: Optional[str] = None) -> Dict[str, Any]:
    settings = get_social_settings()
    if not settings["instagram"]["is_connected"]:
        return {"success": False, "error": "Instagram not connected. Please connect your account first in Settings."}

    src = Path(clip_path)
    if not src.exists():
        return {"success": False, "error": f"Clip file not found: {clip_path}"}

    try:
        cl = get_instagram_client()
        # Verify login state
        try:
            cl.get_timeline_feed()
        except Exception:
            # Re-dump or fail
            pass

        thumb = Path(thumb_path) if thumb_path and Path(thumb_path).exists() else None
        media = cl.clip_upload(
            path=src,
            caption=caption,
            thumbnail=thumb,
            show_preview_in_feed=True
        )

        reel_url = f"https://www.instagram.com/reel/{media.code}/" if hasattr(media, "code") else "https://www.instagram.com/"
        record_upload("Instagram", src.name, "success", url=reel_url)
        
        settings["instagram"]["last_upload"] = time.strftime("%Y-%m-%d %I:%M:%S %p")
        save_social_settings(settings)

        return {
            "success": True,
            "media_id": str(media.id) if hasattr(media, "id") else None,
            "url": reel_url,
            "message": "Reel published to Instagram successfully!"
        }
    except Exception as e:
        err_msg = str(e)
        record_upload("Instagram", src.name, "error", error=err_msg)
        return {"success": False, "error": f"Instagram upload error: {err_msg}"}

# ----------------- YouTube Shorts Integration -----------------

def configure_youtube_secrets(secrets_json_str: str) -> Dict[str, Any]:
    try:
        data = json.loads(secrets_json_str)
        if "installed" not in data and "web" not in data:
            return {"success": False, "error": "Invalid client_secrets.json format. Expected 'installed' or 'web' root key."}
        
        with open(YT_SECRETS_PATH, "w", encoding="utf-8") as f:
            f.write(secrets_json_str)

        settings = get_social_settings()
        settings["youtube"]["has_secrets"] = True
        save_social_settings(settings)
        return {"success": True, "message": "Google Client Secrets uploaded successfully! You can now click 'Connect YouTube Channel'."}
    except Exception as e:
        return {"success": False, "error": f"Failed to parse JSON: {str(e)}"}

def authenticate_youtube() -> Dict[str, Any]:
    if not YT_SECRETS_PATH.exists():
        return {"success": False, "error": "client_secrets.json not found. Please upload it first."}

    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(YT_SECRETS_PATH), SCOPES)
        # This opens the default browser for 1-click Google account approval
        credentials = flow.run_local_server(port=0, prompt='consent')
        
        with open(YT_TOKEN_PATH, 'wb') as f:
            pickle.dump(credentials, f)

        settings = get_social_settings()
        settings["youtube"]["is_connected"] = True
        save_social_settings(settings)

        return {"success": True, "message": "YouTube channel connected successfully!"}
    except Exception as e:
        return {"success": False, "error": f"YouTube authorization failed: {str(e)}"}

def disconnect_youtube() -> Dict[str, Any]:
    if YT_TOKEN_PATH.exists():
        try:
            os.remove(YT_TOKEN_PATH)
        except Exception:
            pass
    settings = get_social_settings()
    settings["youtube"]["is_connected"] = False
    settings["youtube"]["auto_upload"] = False
    save_social_settings(settings)
    return {"success": True, "message": "YouTube channel disconnected."}

def get_youtube_service():
    if not YT_TOKEN_PATH.exists():
        return None

    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    with open(YT_TOKEN_PATH, 'rb') as f:
        credentials = pickle.load(f)

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        with open(YT_TOKEN_PATH, 'wb') as f:
            pickle.dump(credentials, f)

    return build('youtube', 'v3', credentials=credentials)

def publish_to_youtube_shorts(
    clip_path: str,
    title: str,
    description: str,
    tags: list,
    thumb_path: Optional[str] = None,
    privacy_status: Optional[str] = None
) -> Dict[str, Any]:
    settings = get_social_settings()
    if not settings["youtube"]["is_connected"]:
        return {"success": False, "error": "YouTube not connected. Please connect your channel in Settings."}

    src = Path(clip_path)
    if not src.exists():
        return {"success": False, "error": f"Clip file not found: {clip_path}"}

    if not privacy_status:
        privacy_status = settings["youtube"].get("privacy_status", "public")

    try:
        youtube = get_youtube_service()
        if not youtube:
            return {"success": False, "error": "Failed to initialize YouTube service."}

        from googleapiclient.http import MediaFileUpload

        body = {
            'snippet': {
                'title': title[:100],  # YouTube title max 100 chars
                'description': description,
                'tags': tags,
                'categoryId': '23'  # Comedy
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(
            str(src),
            chunksize=1024 * 1024 * 5,  # 5MB chunks
            resumable=True,
            mimetype='video/mp4'
        )

        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()

        video_id = response.get('id')
        shorts_url = f"https://youtube.com/shorts/{video_id}"

        # Set thumbnail if provided and file exists
        if thumb_path and Path(thumb_path).exists() and video_id:
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')
                ).execute()
            except Exception as thumb_err:
                print(f"[YouTube] Note: Custom thumbnail set skipped/failed: {thumb_err}")

        record_upload("YouTube", src.name, "success", url=shorts_url)
        settings["youtube"]["last_upload"] = time.strftime("%Y-%m-%d %I:%M:%S %p")
        save_social_settings(settings)

        return {
            "success": True,
            "video_id": video_id,
            "url": shorts_url,
            "message": "Short uploaded to YouTube successfully!"
        }
    except Exception as e:
        err_msg = str(e)
        record_upload("YouTube", src.name, "error", error=err_msg)
        return {"success": False, "error": f"YouTube upload error: {err_msg}"}

# ----------------- Unified Publisher & Local Ready Folder -----------------

def get_clip_metadata(episode_num: str, part_num: int) -> Dict[str, Any]:
    title = f"TMKOC Episode {episode_num} | Part {part_num} 😂 #tmkoc #shorts #comedy"
    description = (
        f"Taarak Mehta Ka Ooltah Chashmah - Episode {episode_num} (Part {part_num})\n"
        f"Follow & Subscribe for Part {int(part_num) + 1}!\n\n"
        f"#tmkoc #taarakmehta #jethalal #babitaji #dayabhabhi #comedy #shorts #reels #viral"
    )
    tags = ["tmkoc", "taarak mehta", "jethalal", "babita", "daya", "comedy", "shorts", "reels", "funny"]
    return {
        "title": title,
        "description": description,
        "tags": tags
    }

def publish_to_local_folder(clip_path: str, episode_num: str, part_num: int) -> Dict[str, Any]:
    """
    Publishes clip and attached daily thumbnail to 'ready_to_publish' folder with viral social tags.
    Also triggers auto-upload to Instagram & YouTube if enabled in settings!
    """
    src = Path(clip_path)
    if not src.exists():
        return {"success": False, "error": f"File not found: {clip_path}"}

    dest_video = READY_DIR / src.name
    shutil.copy2(src, dest_video)

    # Attach Daily Thumbnail or Part Thumbnail if available
    dest_thumb_str = None
    clip_thumb = src.parent / f"{src.stem}_thumb.jpg"
    if clip_thumb.exists():
        dest_thumb = READY_DIR / f"{src.stem}_thumb.jpg"
        shutil.copy2(clip_thumb, dest_thumb)
        dest_thumb_str = str(dest_thumb)
    elif DAILY_THUMBNAIL_PATH.exists():
        dest_thumb = READY_DIR / f"{src.stem}_thumb.jpg"
        shutil.copy2(DAILY_THUMBNAIL_PATH, dest_thumb)
        dest_thumb_str = str(dest_thumb)

    meta = get_clip_metadata(episode_num, part_num)

    meta_file = READY_DIR / f"{src.stem}_info.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({
            "episode": str(episode_num),
            "part": int(part_num),
            "video_file": str(dest_video),
            "thumbnail_file": dest_thumb_str,
            "platforms": ["YouTube Shorts", "Instagram Reels"],
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "published_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }, f, indent=2)

    # Check social auto-upload
    settings = get_social_settings()
    social_results = {}

    if settings["instagram"].get("is_connected") and settings["instagram"].get("auto_upload"):
        print(f"[Auto-Upload] Uploading {src.name} to Instagram Reels...")
        ig_res = publish_to_instagram(str(dest_video), caption=meta["description"], thumb_path=dest_thumb_str)
        social_results["instagram"] = ig_res

    if settings["youtube"].get("is_connected") and settings["youtube"].get("auto_upload"):
        print(f"[Auto-Upload] Uploading {src.name} to YouTube Shorts...")
        yt_res = publish_to_youtube_shorts(
            clip_path=str(dest_video),
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            thumb_path=dest_thumb_str,
            privacy_status=settings["youtube"].get("privacy_status", "public")
        )
        social_results["youtube"] = yt_res

    return {
        "success": True,
        "destination": str(dest_video),
        "thumbnail": dest_thumb_str,
        "title": meta["title"],
        "description": meta["description"],
        "social_uploads": social_results
    }
