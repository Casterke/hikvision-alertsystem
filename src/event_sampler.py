"""Event sampling: wait N sec, capture snapshots at interval, max EVENT_MAX_DURATION."""
import time
import uuid
from datetime import datetime
from pathlib import Path
from threading import Thread

from src.config import (
    DATA_DIR,
    EVENT_INITIAL_WAIT,
    EVENT_MAX_DURATION,
    EVENT_SAMPLE_INTERVAL,
)
from src.isapi_client import download_snapshot


def sample_event(channel_id: str, on_complete) -> None:
    """
    Sample snapshots for an event:
    1. Wait EVENT_INITIAL_WAIT seconds
    2. Capture snapshots every EVENT_SAMPLE_INTERVAL for up to EVENT_MAX_DURATION
    3. Call on_complete(event_id, snapshot_paths) when done
    """
    event_id = str(uuid.uuid4())
    events_dir = DATA_DIR / "events" / event_id
    events_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = []

    time.sleep(EVENT_INITIAL_WAIT)
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= EVENT_MAX_DURATION:
            break

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        idx = len(snapshot_paths) + 1
        filename = f"{idx:03d}_{ts}.jpg"
        path = events_dir / filename

        content = download_snapshot(channel_id)
        if content:
            path.write_bytes(content)
            snapshot_paths.append(str(path))

        time.sleep(EVENT_SAMPLE_INTERVAL)

    if snapshot_paths:
        on_complete(event_id, channel_id, sorted(snapshot_paths))


def sample_event_async(channel_id: str, on_complete) -> Thread:
    """Run sample_event in a background thread."""
    t = Thread(target=sample_event, args=(channel_id, on_complete))
    t.daemon = True
    t.start()
    return t
