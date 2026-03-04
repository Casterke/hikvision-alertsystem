"""License plate OCR for car crops."""
import re
from typing import Optional

from src.config import PLATE_REGEX

_tesseract_available = False
_paddle_available = False

try:
    import pytesseract
    _tesseract_available = True
except ImportError:
    pass

try:
    from paddleocr import PaddleOCR
    _paddle_available = True
except ImportError:
    pass

_ocr_engine = None


def _get_engine():
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    if _paddle_available:
        _ocr_engine = ("paddle", PaddleOCR(use_angle_cls=True, use_gpu=False, show_log=False))
        return _ocr_engine
    if _tesseract_available:
        _ocr_engine = ("tesseract", None)
        return _ocr_engine
    return None


def read_plate(image_path: str) -> Optional[str]:
    """
    Run OCR on image, return plate string if it matches PLATE_REGEX.
    Returns None if no valid plate found.
    """
    engine = _get_engine()
    if not engine:
        return None
    kind, obj = engine
    text = ""
    if kind == "paddle":
        result = obj.ocr(image_path, cls=True)
        if result and result[0]:
            text = " ".join(line[1][0] for line in result[0])
    elif kind == "tesseract":
        try:
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                return None
            text = pytesseract.image_to_string(img)
        except Exception:
            return None
    text = re.sub(r"\s+", "", text.upper())
    match = re.search(PLATE_REGEX, text)
    if match:
        return match.group(0)
    return None
