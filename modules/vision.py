"""
modules/vision.py
─────────────────
Camera subsystem:
  VisionModule  – webcam stream, face detection, motion detection,
                  face embedding (simplified), snapshot, AI image analysis
"""

from __future__ import annotations
import io
import math
import json
import threading
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from loguru import logger

from config.settings import settings
from memory.memory_manager import MemoryManager


# Haar cascade for face detection
_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


class VisionModule:
    """Manages the webcam stream and all vision tasks."""

    def __init__(self, memory: MemoryManager,
                 on_frame: Callable[[np.ndarray], None] | None = None) -> None:
        self._memory = memory
        self._on_frame = on_frame          # GUI callback for live preview
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None

        # Face detection
        self._face_cascade = cv2.CascadeClassifier(_CASCADE_PATH)
        if self._face_cascade.empty():
            logger.warning("Haar cascade not loaded – face detection unavailable")

        # Motion detection
        self._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=50, detectShadows=False
        )
        self._motion_callbacks: list[Callable] = []

        # Face recognition (simple embeddings stored in DB)
        self._known_faces: list[dict] = []
        self._reload_known_faces()

        logger.info("VisionModule initialised")

    # ────── Stream control ──────

    def start(self) -> bool:
        if self._running:
            return True
        cap = cv2.VideoCapture(settings.camera_index)
        if not cap.isOpened():
            logger.error("Cannot open camera index {}", settings.camera_index)
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Camera stream started")
        return True

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info("Camera stream stopped")

    # ────── Main capture loop ──────

    def _loop(self) -> None:
        while self._running:
            if not self._cap:
                break
            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Camera frame read failed")
                time.sleep(0.1)
                continue

            with self._lock:
                self._latest_frame = frame.copy()

            # Motion
            self._check_motion(frame)

            # GUI callback
            if self._on_frame:
                try:
                    self._on_frame(frame)
                except Exception as e:
                    logger.error("on_frame callback error: {}", e)

            time.sleep(1 / 30)

    # ────── Face detection ──────

    def detect_faces(self, frame: np.ndarray | None = None) -> list[tuple]:
        """Returns list of (x, y, w, h) bounding boxes."""
        if frame is None:
            with self._lock:
                frame = self._latest_frame
        if frame is None:
            return []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=settings.face_detection_scale,
            minNeighbors=settings.face_detection_neighbors,
            minSize=(60, 60),
        )
        return [tuple(f) for f in faces] if len(faces) > 0 else []

    # ────── Face recognition ──────

    def _simple_embedding(self, face_img: np.ndarray) -> list[float]:
        """
        Simplified face embedding using pixel histogram.
        For production, replace with a proper FaceNet/ArcFace model.
        """
        resized = cv2.resize(face_img, (64, 64))
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        return hist.tolist()

    def _embedding_distance(self, a: list[float], b: list[float]) -> float:
        arr_a = np.array(a)
        arr_b = np.array(b)
        return float(np.linalg.norm(arr_a - arr_b))

    def _reload_known_faces(self) -> None:
        self._known_faces = self._memory.get_all_face_embeddings()
        logger.debug("Loaded {} known face records", len(self._known_faces))

    def identify_face(self, face_img: np.ndarray,
                      threshold: float = 0.35) -> str | None:
        """Returns user name if face matches a known embedding, else None."""
        if not self._known_faces:
            return None
        emb = self._simple_embedding(face_img)
        best_name, best_dist = None, float("inf")
        for record in self._known_faces:
            d = self._embedding_distance(emb, record["embedding"])
            if d < best_dist:
                best_dist, best_name = d, record["user"]
        if best_dist < threshold:
            logger.debug("Face matched {} (dist={:.3f})", best_name, best_dist)
            return best_name
        return None

    def register_face(self, user_name: str,
                      frame: np.ndarray | None = None) -> bool:
        """Capture current frame, extract face, save embedding."""
        if frame is None:
            with self._lock:
                frame = self._latest_frame
        if frame is None:
            logger.warning("No frame available for face registration")
            return False

        faces = self.detect_faces(frame)
        if not faces:
            logger.warning("No face detected for registration")
            return False

        x, y, w, h = faces[0]
        face_img = frame[y:y+h, x:x+w]
        emb = self._simple_embedding(face_img)

        # Save image
        img_path = settings.faces_dir / f"{user_name}_{int(time.time())}.jpg"
        cv2.imwrite(str(img_path), face_img)

        self._memory.save_face_embedding(user_name, emb, str(img_path))
        self._reload_known_faces()
        logger.info("Face registered for user '{}'", user_name)
        return True

    # ────── Motion detection ──────

    def _check_motion(self, frame: np.ndarray) -> None:
        mask = self._bg_subtractor.apply(frame)
        motion_pixels = cv2.countNonZero(mask)
        if motion_pixels > 5000:
            for cb in self._motion_callbacks:
                try:
                    cb(motion_pixels)
                except Exception:
                    pass

    def on_motion(self, callback: Callable[[int], None]) -> None:
        self._motion_callbacks.append(callback)

    # ────── Snapshot ──────

    def snapshot(self) -> bytes | None:
        """Return current frame as JPEG bytes."""
        with self._lock:
            frame = self._latest_frame
        if frame is None:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return bytes(buf)

    def get_latest_frame_bgr(self) -> np.ndarray | None:
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    # ────── Annotated frame for GUI ──────

    def annotated_frame(self) -> np.ndarray | None:
        frame = self.get_latest_frame_bgr()
        if frame is None:
            return None
        faces = self.detect_faces(frame)
        for (x, y, w, h) in faces:
            face_img = frame[y:y+h, x:x+w]
            name = self.identify_face(face_img) or "Unknown"
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 220, 255), 2)
            cv2.putText(frame, name, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 220, 255), 2)
        return frame
