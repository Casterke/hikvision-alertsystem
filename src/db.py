"""SQLite database and schema management."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.config import DB_PATH

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


def init_db():
    """Create tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hik_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT
            );

            CREATE TABLE IF NOT EXISTS event_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS channel_events (
                channel_id INTEGER NOT NULL,
                event_type_id INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (channel_id, event_type_id),
                FOREIGN KEY (channel_id) REFERENCES channels(id),
                FOREIGN KEY (event_type_id) REFERENCES event_types(id)
            );

            CREATE TABLE IF NOT EXISTS object_classes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS known_faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                embedding_blob BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recorded_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                channel_id TEXT NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'linedetection',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                person_name TEXT,
                plate TEXT,
                snapshot_count INTEGER NOT NULL DEFAULT 0
            );
        """)
        _seed_object_classes(conn)
        _seed_event_types(conn)


def _seed_object_classes(conn):
    """Seed object_classes from COCO if empty."""
    cur = conn.execute("SELECT COUNT(*) FROM object_classes")
    if cur.fetchone()[0] == 0:
        for i, name in enumerate(COCO_CLASSES):
            conn.execute(
                "INSERT INTO object_classes (id, name, enabled) VALUES (?, ?, ?)",
                (i, name, 1 if name in ("person", "car") else 0)
            )
        conn.commit()


def _seed_event_types(conn):
    """Seed common event types."""
    for name in ("linedetection", "motion", "videoloss", "tamperdetection"):
        conn.execute(
            "INSERT OR IGNORE INTO event_types (name, enabled) VALUES (?, ?)",
            (name, 1 if name == "linedetection" else 0)
        )
    conn.commit()


@contextmanager
def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_enabled_object_classes():
    """Return list of enabled object class names."""
    with _conn() as conn:
        cur = conn.execute(
            "SELECT name FROM object_classes WHERE enabled = 1 ORDER BY id"
        )
        return [r["name"] for r in cur.fetchall()]


def get_enabled_channels_and_events():
    """Return {(channel_id, event_type): enabled} for enabled channel+event combos."""
    with _conn() as conn:
        cur = conn.execute("""
            SELECT c.hik_id, et.name
            FROM channels c
            JOIN channel_events ce ON ce.channel_id = c.id
            JOIN event_types et ON et.id = ce.event_type_id
            WHERE c.enabled = 1 AND et.enabled = 1 AND ce.enabled = 1
        """)
        return {(r["hik_id"], r["name"]) for r in cur.fetchall()}


def should_send_notification(channel_id, event_type, cooldown_seconds=60):
    """Check if we can send (cooldown not exceeded)."""
    with _conn() as conn:
        cur = conn.execute("""
            SELECT sent_at FROM notification_log
            WHERE channel_id = ? AND event_type = ?
            ORDER BY sent_at DESC LIMIT 1
        """, (channel_id, event_type))
        row = cur.fetchone()
        if not row:
            return True
        from datetime import datetime
        sent = datetime.fromisoformat(row["sent_at"])
        elapsed = (datetime.now() - sent).total_seconds()
        return elapsed >= cooldown_seconds


def log_notification(channel_id, event_type):
    """Record that a notification was sent."""
    with _conn() as conn:
        conn.execute(
            "INSERT INTO notification_log (channel_id, event_type) VALUES (?, ?)",
            (channel_id, event_type)
        )


def save_recorded_event(event_id, channel_id, event_type, person_name=None, plate=None, snapshot_count=0):
    """Save a recorded event to the database (only call when something was detected)."""
    with _conn() as conn:
        conn.execute(
            """INSERT INTO recorded_events (event_id, channel_id, event_type, person_name, plate, snapshot_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, channel_id, event_type, person_name, plate, snapshot_count)
        )


def get_recorded_events(limit=100, offset=0):
    """Return recorded events for browsing, newest first."""
    with _conn() as conn:
        cur = conn.execute(
            """SELECT event_id, channel_id, event_type, created_at, person_name, plate, snapshot_count
               FROM recorded_events ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        return [dict(r) for r in cur.fetchall()]


def upsert_channels(channels):
    """Insert or update channels from discovery. Removes channels not in the list."""
    with _conn() as conn:
        hik_ids = [ch["hik_id"] for ch in channels]
        if hik_ids:
            placeholders = ",".join("?" * len(hik_ids))
            conn.execute(
                f"DELETE FROM channels WHERE hik_id NOT IN ({placeholders})",
                hik_ids,
            )
        for ch in channels:
            conn.execute(
                """INSERT INTO channels (hik_id, name, enabled) VALUES (?, ?, ?)
                   ON CONFLICT(hik_id) DO UPDATE SET name=excluded.name, last_seen=datetime('now')""",
                (ch["hik_id"], ch.get("name", ""), 1 if ch.get("enabled", True) else 0)
            )
            cur = conn.execute("SELECT id FROM channels WHERE hik_id = ?", (ch["hik_id"],))
            row = cur.fetchone()
            if not row:
                continue
            cid = row["id"]
            # Enable linedetection by default for new channels
            cur = conn.execute("SELECT id FROM event_types WHERE name = 'linedetection'")
            et_row = cur.fetchone()
            if et_row:
                conn.execute(
                    """INSERT OR IGNORE INTO channel_events (channel_id, event_type_id, enabled)
                       VALUES (?, ?, 1)""",
                    (cid, et_row["id"])
                )
        conn.commit()


def upsert_event_types(event_names):
    """Insert event types from discovery."""
    with _conn() as conn:
        for name in event_names:
            conn.execute(
                "INSERT OR IGNORE INTO event_types (name, enabled) VALUES (?, 1)",
                (name,)
            )
        conn.commit()
