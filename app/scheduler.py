import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from app.uploader import publish_to_local_folder
from app.config import DEFAULT_INTERVAL_MINUTES

class ClipScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.queue: List[Dict[str, Any]] = []
        self.is_running = False
        self.scheduler.add_job(self._check_queue, "interval", seconds=5, id="queue_checker")

    def start(self):
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            print("[Scheduler] Started.")

    def stop(self):
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            print("[Scheduler] Stopped.")

    def schedule_clips(
        self,
        clips: List[Dict[str, Any]],
        episode_num: str,
        interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
        start_delay_seconds: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Takes generated clips and schedules each one spaced interval_minutes (default 5 min) apart.
        """
        now = datetime.now()
        base_time = now + timedelta(seconds=start_delay_seconds)

        new_items = []
        for i, clip in enumerate(clips):
            scheduled_at = base_time + timedelta(minutes=i * interval_minutes)
            item = {
                "id": f"sched_{int(time.time())}_{clip.get('part', i+1)}",
                "episode": episode_num,
                "part": clip.get("part", i + 1),
                "filename": clip.get("filename"),
                "path": clip.get("path"),
                "duration": clip.get("duration", 30),
                "scheduled_timestamp": scheduled_at.timestamp(),
                "scheduled_str": scheduled_at.strftime("%I:%M:%S %p"),
                "status": "scheduled",  # scheduled, published, error
                "published_at": None,
                "details": None
            }
            self.queue.append(item)
            new_items.append(item)

        if not self.is_running:
            self.start()

        return new_items

    def _check_queue(self):
        current_time = time.time()
        for item in self.queue:
            if item["status"] == "scheduled" and current_time >= item["scheduled_timestamp"]:
                item["status"] = "publishing"
                try:
                    result = publish_to_local_folder(
                        clip_path=item["path"],
                        episode_num=item["episode"],
                        part_num=item["part"]
                    )
                    item["status"] = "published" if result.get("success") else "error"
                    item["published_at"] = time.strftime("%I:%M:%S %p")
                    item["details"] = result
                    print(f"[Scheduler] Published Part {item['part']} at {item['published_at']}!")
                except Exception as e:
                    item["status"] = "error"
                    item["details"] = {"error": str(e)}

    def get_queue_status(self) -> Dict[str, Any]:
        current_time = time.time()
        enriched_queue = []
        for item in self.queue:
            copy_item = dict(item)
            if copy_item["status"] == "scheduled":
                diff = int(copy_item["scheduled_timestamp"] - current_time)
                copy_item["seconds_remaining"] = max(0, diff)
            else:
                copy_item["seconds_remaining"] = 0
            enriched_queue.append(copy_item)

        return {
            "is_running": self.is_running,
            "total_in_queue": len(self.queue),
            "published_count": sum(1 for i in self.queue if i["status"] == "published"),
            "pending_count": sum(1 for i in self.queue if i["status"] == "scheduled"),
            "items": enriched_queue
        }

    def clear_queue(self):
        self.queue.clear()

# Global scheduler instance
scheduler_instance = ClipScheduler()
