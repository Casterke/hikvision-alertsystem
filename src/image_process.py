"""YOLO detection, crop person/car, face recognition, plate OCR, with early exit."""
import json
import shutil
import threading
from pathlib import Path
from typing import List, Optional, Tuple

import cv2

from src.config import DATA_DIR, NOTIFICATION_COOLDOWN, YOLO_MODEL
from src.db import get_enabled_object_classes, log_notification, save_recorded_event, should_send_notification
from src.face_rec import extract_embedding, match_face
from src.plate_ocr import read_plate, read_plate_raw


_notification_locks: dict[tuple, threading.Lock] = {}
_lock_guard = threading.Lock()


def _get_notification_lock(channel_id: str, event_type: str) -> threading.Lock:
    key = (channel_id, event_type)
    with _lock_guard:
        if key not in _notification_locks:
            _notification_locks[key] = threading.Lock()
        return _notification_locks[key]


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


def process_event(event_id: str, channel_id: str, snapshot_paths: List[str], event_type: str = "linedetection") -> bool:
    """
    Process snapshots in time order. Early exit when face match or plate found.
    Sends one notification per event (cooldown per channel+event_type).
    Saves event to DB when something is detected.
    Returns True if something was detected (event kept), False if nothing recognized (caller should delete event folder).
    """
    enabled_classes = set(get_enabled_object_classes())
    if not enabled_classes:
        return False

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
        return False

    # Save to DB so events can be browsed
    save_recorded_event(
        event_id=event_id,
        channel_id=channel_id,
        event_type=event_type,
        person_name=best_person,
        plate=best_plate,
        snapshot_count=len(snapshot_paths),
    )

    lock = _get_notification_lock(channel_id, event_type)
    with lock:
        if not should_send_notification(channel_id, event_type, NOTIFICATION_COOLDOWN):
            return True
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

    return True


def process_image_debug(image_path: str) -> dict:
    """
    Run the same YOLO/face/plate pipeline on an image for debugging.
    No notifications. Returns all detections.
    Expects image_path to be under DATA_DIR/debug/{debug_id}/ e.g. .../original.jpg
    """
    enabled_classes = set(get_enabled_object_classes())
    debug_dir = Path(image_path).resolve().parent
    debug_id = debug_dir.name

    img = cv2.imread(image_path)
    if img is None:
        result = {"debug_id": debug_id, "error": "Could not read image", "detections": []}
        (debug_dir / "result.json").write_text(json.dumps(result, indent=2))
        return result

    detections = []
    if not enabled_classes:
        result = {
            "debug_id": debug_id,
            "original_path": "original.jpg",
            "annotated_path": None,
            "detections": [],
        }
        (debug_dir / "result.json").write_text(json.dumps(result, indent=2))
        return result

    model = _load_yolo()
    results = model.predict(img, device="cpu", verbose=False)[0]

    annotated = img.copy()
    if results.boxes is None:
        result = {
            "debug_id": debug_id,
            "original_path": "original.jpg",
            "annotated_path": None,
            "detections": [],
        }
        (debug_dir / "result.json").write_text(json.dumps(result, indent=2))
        return result

    for i, box in enumerate(results.boxes):
        cls_id = int(box.cls[0])
        cls_name = model.names.get(cls_id, "")
        if cls_name not in enabled_classes:
            continue
        xyxy = box.xyxy[0].cpu().numpy()
        crop = _crop_box(img, xyxy)
        crop_filename = f"{i}_{cls_name}.jpg"
        crop_path = debug_dir / crop_filename
        cv2.imwrite(str(crop_path), crop)

        detection = {"class": cls_name, "crop": crop_filename}
        if cls_name == "person":
            emb = extract_embedding(str(crop_path))
            if emb:
                name = match_face(emb)
                detection["face_match"] = name if name else "unknown"
            else:
                detection["face_match"] = "(no face)"
        elif cls_name == "car":
            plate, raw_ocr = read_plate_raw(str(crop_path))
            detection["plate"] = plate if plate else "(not read)"
            if not plate and raw_ocr:
                detection["plate_raw"] = raw_ocr
        detections.append(detection)

        # Draw box on annotated image
        x1, y1, x2, y2 = map(int, xyxy)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = cls_name
        if "face_match" in detection:
            label += f": {detection['face_match']}"
        elif "plate" in detection:
            label += f": {detection['plate']}"
        cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    result = {
        "debug_id": debug_id,
        "original_path": "original.jpg",
        "annotated_path": None,
        "detections": detections,
    }
    if detections:
        annotated_path = debug_dir / "annotated.jpg"
        cv2.imwrite(str(annotated_path), annotated)
        result["annotated_path"] = "annotated.jpg"

    (debug_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result
