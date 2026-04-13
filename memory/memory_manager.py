"""
memory/memory_manager.py
────────────────────────
3-Layer Memory Architecture
  1. SHORT-TERM  – current session list (in-process)
  2. WORKING     – active task queue (in-process)
  3. LONG-TERM   – SQLite via SQLAlchemy (persisted)
"""

from __future__ import annotations
import json
import threading
from collections import deque
from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    Float, create_engine, text
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import settings


# ──────────────────────────────────────────────
# ORM Models
# ──────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(128), unique=True, nullable=False)
    face_file   = Column(String(256))
    preferences = Column(Text, default="{}")
    created_at  = Column(DateTime, default=datetime.utcnow)
    last_seen   = Column(DateTime, default=datetime.utcnow)


class CommandHistory(Base):
    __tablename__ = "command_history"
    id          = Column(Integer, primary_key=True)
    user_name   = Column(String(128), default="unknown")
    command     = Column(Text, nullable=False)
    intent      = Column(String(128))
    result      = Column(Text)
    success     = Column(Integer, default=1)          # 1/0
    created_at  = Column(DateTime, default=datetime.utcnow)


class LearnedBehaviour(Base):
    __tablename__ = "learned_behaviours"
    id          = Column(Integer, primary_key=True)
    trigger     = Column(String(256), nullable=False)
    action      = Column(Text, nullable=False)
    confidence  = Column(Float, default=0.5)
    use_count   = Column(Integer, default=0)
    created_at  = Column(DateTime, default=datetime.utcnow)


class FaceRecord(Base):
    __tablename__ = "face_records"
    id          = Column(Integer, primary_key=True)
    user_name   = Column(String(128), nullable=False)
    embedding   = Column(Text, nullable=False)        # JSON list[float]
    image_path  = Column(String(256))
    created_at  = Column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# Memory Manager
# ──────────────────────────────────────────────

class MemoryManager:
    """Thread-safe memory manager for all three layers."""

    def __init__(self, db_url: str | None = None) -> None:
        self._lock = threading.Lock()

        # Layer 1 – short-term (ring buffer, max 50 entries)
        self._short_term: deque[dict] = deque(maxlen=50)

        # Layer 2 – working memory (active tasks)
        self._working: dict[str, Any] = {}

        # Layer 3 – long-term SQLite
        db_url = db_url or f"sqlite:///{settings.db_path}"
        self._engine = create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        logger.info("MemoryManager initialised – DB at {}", settings.db_path)

    # ────── Short-term ──────

    def remember(self, key: str, value: Any) -> None:
        with self._lock:
            self._short_term.append({"key": key, "value": value,
                                     "ts": datetime.utcnow().isoformat()})

    def recall(self, key: str) -> Any | None:
        with self._lock:
            for entry in reversed(self._short_term):
                if entry["key"] == key:
                    return entry["value"]
        return None

    def get_recent_context(self, n: int = 10) -> list[dict]:
        with self._lock:
            return list(self._short_term)[-n:]

    # ────── Working memory ──────

    def set_task(self, task_id: str, data: Any) -> None:
        with self._lock:
            self._working[task_id] = data

    def get_task(self, task_id: str) -> Any | None:
        with self._lock:
            return self._working.get(task_id)

    def complete_task(self, task_id: str) -> None:
        with self._lock:
            self._working.pop(task_id, None)

    def get_active_tasks(self) -> dict:
        with self._lock:
            return dict(self._working)

    # ────── Long-term ──────

    def log_command(self, user: str, command: str,
                    intent: str, result: str, success: bool) -> None:
        try:
            with Session(self._engine) as s:
                s.add(CommandHistory(
                    user_name=user, command=command,
                    intent=intent, result=result,
                    success=1 if success else 0,
                ))
                s.commit()
        except Exception as e:
            logger.error("Failed to log command: {}", e)

    def get_command_history(self, limit: int = 20) -> list[dict]:
        try:
            with Session(self._engine) as s:
                rows = (s.query(CommandHistory)
                          .order_by(CommandHistory.created_at.desc())
                          .limit(limit).all())
                return [
                    {"command": r.command, "intent": r.intent,
                     "success": bool(r.success),
                     "ts": r.created_at.isoformat()} for r in rows
                ]
        except Exception as e:
            logger.error("Failed to read command history: {}", e)
            return []

    def upsert_user_profile(self, name: str, preferences: dict) -> None:
        try:
            with Session(self._engine) as s:
                profile = s.query(UserProfile).filter_by(name=name).first()
                if profile:
                    profile.preferences = json.dumps(preferences)
                    profile.last_seen = datetime.utcnow()
                else:
                    s.add(UserProfile(name=name,
                                      preferences=json.dumps(preferences)))
                s.commit()
        except Exception as e:
            logger.error("Failed to upsert user profile: {}", e)

    def get_user_profile(self, name: str) -> dict | None:
        try:
            with Session(self._engine) as s:
                p = s.query(UserProfile).filter_by(name=name).first()
                if p:
                    return {"name": p.name,
                            "preferences": json.loads(p.preferences or "{}"),
                            "last_seen": p.last_seen.isoformat()}
        except Exception as e:
            logger.error("Failed to get user profile: {}", e)
        return None

    def save_face_embedding(self, user_name: str,
                            embedding: list[float], image_path: str) -> None:
        try:
            with Session(self._engine) as s:
                s.add(FaceRecord(
                    user_name=user_name,
                    embedding=json.dumps(embedding),
                    image_path=image_path,
                ))
                s.commit()
            logger.info("Face embedding saved for {}", user_name)
        except Exception as e:
            logger.error("Failed to save face embedding: {}", e)

    def get_all_face_embeddings(self) -> list[dict]:
        try:
            with Session(self._engine) as s:
                rows = s.query(FaceRecord).all()
                return [
                    {"user": r.user_name,
                     "embedding": json.loads(r.embedding),
                     "image_path": r.image_path} for r in rows
                ]
        except Exception as e:
            logger.error("Failed to load face embeddings: {}", e)
            return []

    def learn_behaviour(self, trigger: str, action: str,
                        confidence: float = 0.5) -> None:
        try:
            with Session(self._engine) as s:
                b = s.query(LearnedBehaviour).filter_by(trigger=trigger).first()
                if b:
                    b.use_count += 1
                    b.confidence = min(1.0, b.confidence + 0.05)
                else:
                    s.add(LearnedBehaviour(trigger=trigger, action=action,
                                           confidence=confidence))
                s.commit()
        except Exception as e:
            logger.error("Failed to learn behaviour: {}", e)

    def get_learned_behaviours(self) -> list[dict]:
        try:
            with Session(self._engine) as s:
                rows = (s.query(LearnedBehaviour)
                          .order_by(LearnedBehaviour.confidence.desc()).all())
                return [{"trigger": r.trigger, "action": r.action,
                         "confidence": r.confidence} for r in rows]
        except Exception as e:
            logger.error("Failed to read learned behaviours: {}", e)
            return []
