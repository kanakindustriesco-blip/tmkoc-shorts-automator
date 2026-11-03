# 🎬 TMKOC Shorts Automator (16:9 to 9:16) & 5-Minute Auto-Scheduler

An automated system to convert full downloaded 16:9 TMKOC episodes into 9:16 vertical shorts (1080x1920), dynamically overlay custom frames with Episode & Part numbers, slice them into 30-second clips, and queue them for release at 5-minute intervals.

---

## 🌟 Features

- **16:9 to 9:16 Vertical Converter:** Centers the horizontal episode video on a vertical canvas with an optimized fast blurred background.
- **Custom Template Overlay:** Bundles the official Gokuldham / TMKOC frame with dynamic font rendering:
  - `EPISODE NO.` rendered inside the left pill box.
  - `PART NO.` rendered inside the right pill box.
- **30-Second Auto-Slicer:** High-speed FFmpeg slicing preserving synchronized audio and crisp 1080x1920 video.
- **Master Drop & Watch Folder:** Drop raw episode videos directly onto the web interface or inside `storage/raw_videos` to auto-trigger the full pipeline.
- **5-Minute Auto-Publisher Queue:** Automatically spaces clip releases 5 minutes apart with ready-to-copy viral titles, descriptions, and hashtags.
- **Modern Web Dashboard:** Real-time progress bar, live 9:16 smartphone mockup preview, in-browser video player, and one-click ZIP download.

---

## 🚀 Quick Start (Windows)

1. Clone the repository:
   ```bash
   git clone https://github.com/kanakindustriesco-blip/tmkoc-shorts-automator.git
   cd tmkoc-shorts-automator
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the dashboard:
   - Double click **`run.bat`**, or run:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

4. Open `http://localhost:8000` in your browser.

---

## 📁 Project Structure

```
tmkoc_shorts_automator/
│
├── app/
│   ├── config.py              # Application settings & template geometry
│   ├── processor.py           # Slicing, fast blur, & background folder watcher
│   ├── template_engine.py     # Pillow overlay & pill box text rendering
│   ├── scheduler.py           # APScheduler 5-minute interval queue
│   ├── uploader.py            # Local ready folder & API connectors
│   └── main.py                # FastAPI server & REST API
│
├── static/
│   ├── js/app.js              # Client application & drag-drop logic
│   └── templates/             # Official TMKOC templates
│
├── templates_html/
│   └── index.html             # Sleek Tailwind web dashboard
│
├── storage/
│   ├── raw_videos/            # Auto-watch drop folder
│   ├── clips/                 # Generated 30s vertical clips
│   └── ready_to_publish/      # Scheduled release folder
│
├── run.bat                    # One-click Windows launcher
└── requirements.txt           # Python dependencies
```
