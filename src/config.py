"""Load configuration from .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(_env_path)


# NVR
NVR_URL = os.getenv("NVR_URL", "http://localhost")
NVR_USR = os.getenv("NVR_USR", "admin")
NVR_PASS = os.getenv("NVR_PASS", "")
NVR_CHANNELS = int(os.getenv("NVR_CHANNELS", "16"))
NVR_CONNECT_TIMEOUT = int(os.getenv("NVR_CONNECT_TIMEOUT", "10"))
NVR_READ_TIMEOUT = int(os.getenv("NVR_READ_TIMEOUT", "15"))
NVR_STREAM_READ_TIMEOUT = int(os.getenv("NVR_STREAM_READ_TIMEOUT", "120"))
NVR_RETRIES = int(os.getenv("NVR_RETRIES", "10"))
NVR_RETRY_DELAY = int(os.getenv("NVR_RETRY_DELAY", "3"))

# YOLO
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")

# Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NOTIFICATION_COOLDOWN = int(os.getenv("NOTIFICATION_COOLDOWN", "120"))
MQTT_BROKER = os.getenv("MQTT_BROKER", "")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "hikvision/alerts")
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

# Event sampling
EVENT_INITIAL_WAIT = int(os.getenv("EVENT_INITIAL_WAIT", "3"))
EVENT_SAMPLE_INTERVAL = int(os.getenv("EVENT_SAMPLE_INTERVAL", "4"))
EVENT_MAX_DURATION = int(os.getenv("EVENT_MAX_DURATION", "120"))

# Recognition
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.6"))
# YOLO model for license plate detection (HuggingFace or local path)
PLATE_MODEL = os.getenv(
    "PLATE_MODEL",
    "https://huggingface.co/Koushim/yolov8-license-plate-detection/resolve/main/best.pt",
)
# Web auth
WEB_USER = os.getenv("WEB_USER", "")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")

# Paths - support Docker /config and /app/data vs local
USE_DOCKER_PATHS = os.path.exists("/config")
DATA_DIR = Path("/app/data" if USE_DOCKER_PATHS else _project_root / "data")
CONFIG_DIR = Path("/config" if USE_DOCKER_PATHS else _project_root / "config")
APP_PATH = Path("/app" if USE_DOCKER_PATHS else _project_root)

# Ensure data dirs exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "snapshot").mkdir(exist_ok=True)
(DATA_DIR / "output").mkdir(exist_ok=True)
(DATA_DIR / "events").mkdir(exist_ok=True)
(DATA_DIR / "channels").mkdir(exist_ok=True)
(DATA_DIR / "output" / "unrecognized").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "debug").mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "alerts.db"
