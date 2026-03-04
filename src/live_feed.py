"""In-memory feed of recent events and snapshots for live view."""
from collections import deque
from datetime import datetime
from threading import Lock

MAX_EVENTS = 100
MAX_SNAPSHOTS = 20

_events = deque(maxlen=MAX_EVENTS)
_snapshots = deque(maxlen=MAX_SNAPSHOTS)
_lock = Lock()


def push_event(channel_id: str, event_type: str):
    with _lock:
        _events.append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "channel_id": channel_id,
            "event_type": event_type,
        })


def push_snapshots(event_id: str, channel_id: str, paths: list):
    with _lock:
        files = [p.split("/")[-1] if "/" in p else p.split("\\")[-1] for p in paths]
        _snapshots.append({
            "event_id": event_id,
            "channel_id": channel_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": files,
        })


def get_feed():
    with _lock:
        return {
            "events": list(_events),
            "snapshots": list(_snapshots),
        }
