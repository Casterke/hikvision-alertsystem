"""Telegram and MQTT notifications."""
from pathlib import Path
from typing import Optional

import requests

from src.config import (
    MQTT_BROKER,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_TOPIC,
    MQTT_USER,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)


def send_telegram(message: str, image_path: Optional[str] = None) -> bool:
    """Send message (and optionally image) via Telegram bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                r = requests.post(
                    f"{base}/sendPhoto",
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": message},
                    files={"photo": f},
                    timeout=10
                )
        else:
            r = requests.post(
                f"{base}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
                timeout=10
            )
        return r.status_code == 200
    except Exception as e:
        print("Telegram send error:", e)
        return False


def send_mqtt(message: str) -> bool:
    """Publish message to MQTT topic."""
    if not MQTT_BROKER or not MQTT_TOPIC:
        return False
    try:
        import paho.mqtt.publish as publish
        auth = None
        if MQTT_USER and MQTT_PASSWORD:
            auth = {"username": MQTT_USER, "password": MQTT_PASSWORD}
        publish.single(
            MQTT_TOPIC,
            message,
            hostname=MQTT_BROKER,
            port=MQTT_PORT,
            auth=auth,
            timeout=5
        )
        return True
    except Exception as e:
        print("MQTT send error:", e)
        return False


def send_notifications(channel_id: str, message: str, image_path: Optional[str] = None):
    """Send to both Telegram and MQTT if configured."""
    send_telegram(message, image_path)
    send_mqtt(message)
