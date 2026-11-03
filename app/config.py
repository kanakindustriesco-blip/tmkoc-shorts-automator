import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
INPUTS_DIR = STORAGE_DIR / "inputs"
RAW_VIDEOS_DIR = STORAGE_DIR / "raw_videos"
PROCESSED_RAW_DIR = RAW_VIDEOS_DIR / "processed"
CLIPS_DIR = STORAGE_DIR / "clips"
READY_DIR = STORAGE_DIR / "ready_to_publish"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = STATIC_DIR / "templates"
HTML_TEMPLATES_DIR = BASE_DIR / "templates_html"

# Default template path (User's ===.png template)
DEFAULT_TEMPLATE_PATH = TEMPLATES_DIR / "tmkoc_official_template.png"

# Ensure directories exist
for directory in [INPUTS_DIR, RAW_VIDEOS_DIR, PROCESSED_RAW_DIR, CLIPS_DIR, READY_DIR, TEMPLATES_DIR, HTML_TEMPLATES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Video Defaults
DEFAULT_CLIP_DURATION = 30  # seconds
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# TMKOC Template Specific Coordinates (for 1080x1920 canvas)
# Video window between top yellow bar and bottom yellow bar
VIDEO_WINDOW_Y_START = 623
VIDEO_WINDOW_Y_END = 1241
VIDEO_WINDOW_HEIGHT = VIDEO_WINDOW_Y_END - VIDEO_WINDOW_Y_START  # 618 px

# Exact Centers of Pill Boxes in the Yellow Badge
EPISODE_PILL_CENTER = (469, 519)
PART_PILL_CENTER = (855, 519)

# Scheduler Defaults
DEFAULT_INTERVAL_MINUTES = 5

# Host Configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
