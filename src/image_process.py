"""YOLO detection, crop person/car, face recognition, plate OCR, with early exit."""
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

import cv2

from src.config import DATA_DIR, YOLO_MODEL
from src.db import get_enabled_object_classes, log_notification, should_send_notification
from src.face_rec import extract_embedding, match_face
from src.plate_ocr import read_plate


def _load_yolo():
    from ultralytics import YOLO
    return YOLO(YOLO_MODEL)


def _crop_box(image, box, padding=8):
    """Crop image to bounding box with padding. box: xyxy format."""
    h, w = image.shape[:2]
    x1 = max(0, int(box[0]) - padding)
    y1 = max(0, int(box[1]) - padding)
    x2 = min(w, int(box[2]) + padding)
    y2 = min(h, int(box[3]) + padding)
    return image[y1:y2, x1:x2]


def process_event(event_id: str, channel_id: str, snapshot_paths: List[str], event_type: str = "linedetection"):
    """
    Process snapshots in time order. Early exit when face match or plate found.
    Sends one notification per event.
    """
    enabled_classes = set(get_enabled_object_classes())
    if not enabled_classes:
        return

    if not should_send_notification(channel_id, event_type):
        return

    model = _load_yolo()
    crops_dir = Path(snapshot_paths[0]).parent / "crops"
    crops_dir.mkdir(exist_ok=True)

    best_person = None  # (name or "unknown")
    best_plate = None   # plate str or None
    best_image_path = None

    done = False
    for path in sorted(snapshot_paths):
        if done:
            break
        img = cv2.imread(path)
        if img is None:
            continue
        results = model.predict(img, device="cpu", verbose=False)[0]
        if results.boxes is None:
            continue

        for i, box in enumerate(results.boxes):
            cls_id = int(box.cls[0])
            cls_name = model.names.get(cls_id, "")
            if cls_name not in enabled_classes:
                continue
            xyxy = box.xyxy[0].cpu().numpy()
            crop = _crop_box(img, xyxy)
            crop_path = crops_dir / f"{i}_{cls_name}.jpg"
            cv2.imwrite(str(crop_path), crop)

            if cls_name == "person":
                emb = extract_embedding(str(crop_path))
                if emb:
                    name = match_face(emb)
                    if name:
                        best_person = name
                        best_image_path = path
                        done = True
                        break
                    elif best_person is None:
                        best_person = "unknown"
                        best_image_path = path
            elif cls_name == "car":
                plate = read_plate(str(crop_path))
                if plate:
                    best_plate = plate
                    best_image_path = path
                    done = True
                    break
                elif best_plate is None and "car" in enabled_classes:
                    best_plate = "(not read)"
                    best_image_path = path

        if done:
            break

    if best_person is None and best_plate is None:
        return

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"Channel: {channel_id}", f"Time: {ts}"]
    if best_person:
        parts.append(f"Person: {best_person}")
    if best_plate:
        parts.append(f"Plate: {best_plate}")

    msg = " | ".join(parts)
    from src.notifications import send_notifications
    send_notifications(channel_id, msg, best_image_path)
    log_notification(channel_id, event_type)
