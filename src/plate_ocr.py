"""License plate detection (YOLO) + OCR (EasyOCR) per Medium article."""
import re
from typing import Optional, Tuple

import cv2

from src.config import PLATE_MODEL

_plate_model = None
_ocr_reader = None


def _get_plate_model():
    global _plate_model
    if _plate_model is not None:
        return _plate_model
    from ultralytics import YOLO
    _plate_model = YOLO(PLATE_MODEL)
    return _plate_model


def _get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is not None:
        return _ocr_reader
    import easyocr
    _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _ocr_reader


def _detect_plate_regions(img):
    """
    Run YOLO plate detector, return list of (x1,y1,x2,y2,conf) for plate boxes.
    """
    model = _get_plate_model()
    results = model.predict(img, device="cpu", verbose=False)[0]
    if results.boxes is None:
        return []
    boxes = []
    for box in results.boxes:
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].cpu().numpy()
        x1, y1, x2, y2 = map(int, xyxy)
        boxes.append((x1, y1, x2, y2, conf))
    return sorted(boxes, key=lambda b: b[4], reverse=True)


def _crop_plate(img, box, padding=4):
    """Crop plate region with padding."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box[:4]
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(w, x2 + padding)
    y2 = min(h, y2 + padding)
    return img[y1:y2, x1:x2]


def _preprocess_plate_for_ocr(img, min_height: int = 80):
    """
    Upscale and enhance contrast so big plate letters are easier to detect
    than small bezel text. Returns RGB image.
    """
    h, w = img.shape[:2]
    if len(img.shape) == 2:
        gray = img
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Upscale if too small - plate letters need ~20+ px height for good OCR
    scale = max(1.0, min_height / h)
    if scale > 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # CLAHE contrast enhancement - helps reflective/low-contrast plate letters
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)


def _read_text_with_easyocr(img) -> str:
    """Run EasyOCR on image (numpy BGR or RGB). Returns joined text."""
    reader = _get_ocr_reader()
    # Preprocess: upscale + contrast so big letters beat small bezel text
    img_rgb = _preprocess_plate_for_ocr(img)
    # min_size=25 filters out small bezel text; allowlist restricts to plate chars
    result = reader.readtext(
        img_rgb,
        detail=1,
        min_size=25,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -.",
        contrast_ths=0.15,
        adjust_contrast=0.6,
    )
    if not result:
        return ""
    # Filter low confidence, join text
    min_conf = 0.3
    parts = [item[1] for item in result if item[2] >= min_conf]
    return " ".join(parts) if parts else ""


def _clean_plate(text: str) -> str:
    """Clean OCR output: strip, collapse spaces, uppercase."""
    text = re.sub(r"\s+", " ", text.strip().upper())
    text = re.sub(r"[^A-Z0-9\-\.\s]", "", text)
    return text.strip()


def _is_valid_plate(text: str) -> bool:
    """Check if text looks like a plate (4+ alphanumeric chars)."""
    alnum = re.sub(r"[^A-Z0-9]", "", text.upper())
    return len(alnum) >= 4


def read_plate(image_path: str) -> Optional[str]:
    """
    Detect plate with YOLO, crop it, run EasyOCR. Returns plate text or None.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None

    boxes = _detect_plate_regions(img)
    for box in boxes:
        crop = _crop_plate(img, box)
        if crop.size == 0:
            continue
        text = _read_text_with_easyocr(crop)
        cleaned = _clean_plate(text)
        if cleaned and _is_valid_plate(cleaned):
            return cleaned

    # Fallback: run EasyOCR on full image (in case YOLO missed the plate)
    text = _read_text_with_easyocr(img)
    cleaned = _clean_plate(text)
    if cleaned and _is_valid_plate(cleaned):
        return cleaned
    return None


def read_plate_raw(image_path: str) -> Tuple[Optional[str], str]:
    """
    Same as read_plate but returns (plate, raw_text) for debug UI.
    Raw shows OCR output for debugging when plate is not recognized.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None, "(could not read image)"

    best_plate = None
    best_raw = ""

    boxes = _detect_plate_regions(img)
    for box in boxes:
        crop = _crop_plate(img, box)
        if crop.size == 0:
            continue
        text = _read_text_with_easyocr(crop)
        cleaned = _clean_plate(text)
        if text and len(text) > len(best_raw):
            best_raw = text
        if cleaned and _is_valid_plate(cleaned):
            best_plate = cleaned
            best_raw = text or cleaned

    if not best_plate:
        if not boxes:
            text = _read_text_with_easyocr(img)
            best_raw = text or "(no plate detected, no text)"
            cleaned = _clean_plate(text)
            if cleaned and _is_valid_plate(cleaned):
                best_plate = cleaned
        elif not best_raw:
            best_raw = "(plate detected, no text)"

    return best_plate, best_raw or "(no text detected)"
