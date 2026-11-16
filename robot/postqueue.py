"""Posting queue helpers. The queue is a JSON list of items:

{
  "id": "2026-10-25-v1-a",          unique id
  "file": "media/hook-v1.mp4",       path relative to the queue folder
  "caption": "...",
  "scheduled_at": "2026-10-25T09:30:00Z",   UTC
  "platform": "instagram",
  "trial": "MANUAL" | "SS_PERFORMANCE" | null,
  "approved": true,                  only approved items are ever posted
  "group": "video-01", "variant": "V1",
  "status": "pending" | "posted" | "error",
  "media_id": null, "posted_at": null, "error": null
}
"""
import json
from datetime import datetime, timezone


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save(path, items):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def due(items, now=None, platform="instagram", limit=3, max_attempts=3):
    """Approved, pending items for this platform whose time has come, oldest first."""
    now = now or datetime.now(timezone.utc)
    ready = [i for i in items
             if i.get("platform") == platform
             and i.get("approved") is True
             and i.get("status", "pending") == "pending"
             and i.get("attempts", 0) < max_attempts
             and parse_time(i["scheduled_at"]) <= now]
    ready.sort(key=lambda i: parse_time(i["scheduled_at"]))
    return ready[:limit]
