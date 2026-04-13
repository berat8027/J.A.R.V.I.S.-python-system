"""
config/settings.py
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger


def _find_and_load_env() -> None:
    base = Path(__file__).parent.parent
    candidates = [
        base / ".env",
        base.parent / ".env",
        Path(os.getcwd()) / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=True)
            logger.info(".env yüklendi: {}", p)
            return
    load_dotenv(override=True)
    logger.warning(".env bulunamadı – sistem ortam değişkenleri kullanılıyor")


_find_and_load_env()


class _Redacted:
    __slots__ = ("_v",)

    def __init__(self, v: str) -> None:
        object.__setattr__(self, "_v", v)

    def get(self) -> str:
        return object.__getattribute__(self, "_v")

    def __repr__(self) -> str:
        return "<redacted>"

    def __str__(self) -> str:
        return "<redacted>"

    def __bool__(self) -> bool:
        v = self.get()
        return bool(v) and v not in ("your_gemini_api_key_here", "")


class Settings:
    def __init__(self) -> None:
        raw_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self._api_key = _Redacted(raw_key)

        if not self._api_key:
            logger.error(
                "GEMINI_API_KEY ayarlanmamış! "
                "jarvis\\.env dosyasını açıp GEMINI_API_KEY=... satırını doldurun."
            )

        self.gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.tts_rate: int = int(os.environ.get("TTS_RATE", 175))
        self.tts_volume: float = float(os.environ.get("TTS_VOLUME", 0.9))
        self.stt_energy_threshold: int = int(os.environ.get("STT_ENERGY_THRESHOLD", 300))
        self.stt_pause_threshold: float = float(os.environ.get("STT_PAUSE_THRESHOLD", 0.8))
        self.camera_index: int = int(os.environ.get("CAMERA_INDEX", 0))
        self.require_confirmation: bool = (
            os.environ.get("REQUIRE_CONFIRMATION_FOR_CRITICAL_ACTIONS", "true").lower() == "true"
        )
        self.whitelist_enabled: bool = (
            os.environ.get("WHITELIST_ENABLED", "true").lower() == "true"
        )
        self.autostart_on_boot: bool = (
            os.environ.get("AUTOSTART_ON_BOOT", "false").lower() == "true"
        )
        self.log_level: str = os.environ.get("LOG_LEVEL", "INFO")

        self.base_dir: Path = Path(__file__).parent.parent
        self.data_dir: Path = self.base_dir / "data"
        self.faces_dir: Path = self.data_dir / "faces"
        self.embeddings_dir: Path = self.data_dir / "embeddings"
        self.logs_dir: Path = self.base_dir / "logs"
        self.db_path: Path = self.data_dir / "jarvis.db"

        for d in (self.data_dir, self.faces_dir, self.embeddings_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def gemini_api_key(self) -> _Redacted:
        return self._api_key

    def get_api_key(self) -> str:
        return self._api_key.get()


settings = Settings()