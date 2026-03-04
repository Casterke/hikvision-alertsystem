# Hikvision Alert System

Python application that subscribes to the Hikvision ISAPI event stream (linedetection, motion, etc.), captures snapshots during events, runs Ultralytics YOLO (YOLOv8) object detection, and optionally performs face recognition or license plate OCR. Notifications are sent via Telegram and/or MQTT.

## Features

- **Autodiscovery**: Channels and event types discovered from NVR via ISAPI
- **Event sampling**: Waits a few seconds, then captures multiple snapshots over up to 120 seconds
- **Two-stage recognition**: Person → face matching against known library; Car → license plate OCR
- **Web UI**: Manage channels, events, object classes, and known faces
- **Notifications**: Telegram and MQTT (no email)
- **CPU-only**: Runs without GPU

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

- `NVR_URL`, `NVR_USR`, `NVR_PASS` – Hikvision NVR connection
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` – optional Telegram
- `MQTT_BROKER`, `MQTT_TOPIC` – optional MQTT
- `WEB_USER`, `WEB_PASSWORD` – optional; if empty, credentials are auto-generated on first run

## Running

### Local

```bash
pip install -r requirements.txt
python run.py
```

Web UI: http://localhost:5000

### Docker

```bash
docker compose up -d
```

Volumes: `./data` (SQLite, snapshots, events), `./config`

If port 5000 is in use, edit `docker-compose.yml` and change the host port (e.g. `"5001:5000"`).

## License

See LICENSE.
