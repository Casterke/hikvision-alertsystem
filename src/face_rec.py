"""Face recognition against known_faces library."""
from pathlib import Path
from typing import Optional

from src.config import FACE_MATCH_THRESHOLD
from src.db import _conn

try:
    import face_recognition
except ImportError:
    face_recognition = None


def _load_known_faces():
    """Load name -> embedding from known_faces table."""
    if not face_recognition:
        return {}
    with _conn() as conn:
        cur = conn.execute("SELECT name, embedding_blob FROM known_faces")
        known = {}
        for row in cur.fetchall():
            import pickle
            emb = pickle.loads(row["embedding_blob"])
            known[row["name"]] = emb
        return known


def extract_embedding(image_path: str) -> Optional[list]:
    """Extract face embedding from image. Returns None if no face or on error."""
    if not face_recognition:
        return None
    try:
        img = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(img)
        if encodings:
            return encodings[0].tolist()
    except Exception as e:
        print("Face embedding error:", e)
    return None


def match_face(embedding: list) -> Optional[str]:
    """
    Match embedding against known_faces.
    Returns name if match above threshold, else None.
    """
    if not face_recognition:
        return None
    known = _load_known_faces()
    if not known:
        return None
    import numpy as np
    enc = np.array(embedding)
    for name, known_enc in known.items():
        if isinstance(known_enc, list):
            known_enc = np.array(known_enc)
        dist = face_recognition.face_distance([known_enc], enc)[0]
        if dist <= FACE_MATCH_THRESHOLD:  # face_recognition: lower dist = better match, typical < 0.6
            return name
    return None


def add_known_face(name: str, image_path: str) -> bool:
    """Add a face to the library. Returns True on success."""
    emb = extract_embedding(image_path)
    if emb is None:
        return False
    import pickle
    with _conn() as conn:
        conn.execute(
            "INSERT INTO known_faces (name, embedding_blob) VALUES (?, ?)",
            (name, pickle.dumps(emb))
        )
    return True
