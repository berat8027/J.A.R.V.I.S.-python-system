"""
modules/speech.py
"""
from __future__ import annotations
import threading
import queue
import time
import re
from typing import Callable
from enum import Enum

import speech_recognition as sr
from loguru import logger

from config.settings import settings


class Priority(Enum):
    CRITICAL = 0
    HIGH     = 1
    NORMAL   = 2
    LOW      = 3


class TTSMessage:
    def __init__(self, text: str,
                 priority: Priority = Priority.NORMAL,
                 rate_override: int | None = None,
                 event: threading.Event | None = None) -> None:
        self.text          = text
        self.priority      = priority
        self.rate_override = rate_override
        self.event         = event
        self.timestamp     = time.time()

    def __lt__(self, other: "TTSMessage") -> bool:
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp


class SpeechSpeaker:

    def __init__(self) -> None:
        import heapq
        self._heap: list = []
        self._heap_lock  = threading.Lock()
        self._new_item   = threading.Event()
        self._speaking   = False
        self._speak_lock = threading.Lock()
        self._speak_count = 0
        self._total_chars = 0
        self._selected_voice_id: str | None = None

        # Başlangıçta en iyi sesi bir kez bul ve kaydet
        self._selected_voice_id = self._find_best_voice()

        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="TTS-Worker"
        )
        self._thread.start()
        logger.info("SpeechSpeaker hazır")

    def _find_best_voice(self) -> str | None:
        """Sistendeki sesleri tara, en uygun sesi seç ve ID'sini kaydet."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            voices = engine.getProperty("voices") or []

            # Tüm sesleri logla
            for v in voices:
                logger.info("Mevcut ses: [{}] {}", v.id, v.name)

            chosen = None

            # 1. Türkçe erkek ses
            for v in voices:
                name = (v.name or "").lower()
                if ("turkish" in name or "türk" in name) and \
                   any(k in name for k in ("male", "erkek", "can", "ali")):
                    chosen = v
                    break

            # 2. Herhangi Türkçe ses
            if not chosen:
                for v in voices:
                    name = (v.name or "").lower()
                    if "turkish" in name or "türk" in name:
                        chosen = v
                        break

            # 3. İngilizce erkek ses
            if not chosen:
                for v in voices:
                    name = (v.name or "").lower()
                    if any(k in name for k in ("david", "mark", "daniel",
                                               "george", "james", "male")):
                        chosen = v
                        break

            # 4. Zira hariç ilk ses (Zira kadın sesi)
            if not chosen:
                for v in voices:
                    name = (v.name or "").lower()
                    if "zira" not in name:
                        chosen = v
                        break

            # 5. Hiçbiri yoksa ilk ses
            if not chosen and voices:
                chosen = voices[0]

            engine.stop()
            del engine

            if chosen:
                logger.info("Seçilen TTS sesi: {}", chosen.name)
                return chosen.id

        except Exception as e:
            logger.error("Ses tarama hatası: {}", e)
        return None

    def speak(self, text: str,
              priority: Priority = Priority.HIGH,
              blocking: bool = False,
              rate_override: int | None = None) -> None:
        if not text or not text.strip():
            return
        text  = self._clean(text)
        event = threading.Event() if blocking else None
        msg   = TTSMessage(text, priority, rate_override, event)

        import heapq
        with self._heap_lock:
            heapq.heappush(self._heap, msg)
        self._new_item.set()

        if blocking and event:
            event.wait(timeout=60)

    def speak_critical(self, text: str) -> None:
        self.speak(text, priority=Priority.CRITICAL, blocking=True)

    def stop(self) -> None:
        with self._heap_lock:
            self._heap.clear()

    @property
    def is_speaking(self) -> bool:
        with self._speak_lock:
            return self._speaking

    def get_stats(self) -> dict:
        return {
            "konuşma_sayısı":  self._speak_count,
            "toplam_karakter": self._total_chars,
            "kuyruk":          len(self._heap),
            "konuşuyor":       self.is_speaking,
        }

    def _worker(self) -> None:
        import heapq
        while True:
            self._new_item.wait(timeout=0.2)
            self._new_item.clear()
            while True:
                msg = None
                with self._heap_lock:
                    if self._heap:
                        msg = heapq.heappop(self._heap)
                if msg is None:
                    break
                if time.time() - msg.timestamp > 300:
                    if msg.event:
                        msg.event.set()
                    continue
                self._say(msg)

    def _say(self, msg: TTSMessage) -> None:
        with self._speak_lock:
            self._speaking = True
        try:
            import pyttsx3
            engine = pyttsx3.init()

            # Hız — .env'den oku, override varsa onu kullan
            rate = msg.rate_override or settings.tts_rate
            engine.setProperty("rate",   rate)
            engine.setProperty("volume", settings.tts_volume)

            # Kaydedilen ses ID'sini kullan
            if self._selected_voice_id:
                engine.setProperty("voice", self._selected_voice_id)

            logger.debug("TTS ▶ rate={} [{}] {}",
                         rate, msg.priority.name, msg.text[:80])
            engine.say(msg.text)
            engine.runAndWait()

            try:
                engine.stop()
            except Exception:
                pass
            del engine

            self._speak_count += 1
            self._total_chars += len(msg.text)

        except Exception as e:
            logger.error("TTS hatası: {}", e)
        finally:
            with self._speak_lock:
                self._speaking = False
            if msg.event:
                msg.event.set()

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
            r"\U00002702-\U000027B0\U000024C2-\U0001F251]+",
            "", text, flags=re.UNICODE
        )
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
        text = re.sub(r"`{1,3}(.+?)`{1,3}", r"\1", text)
        text = re.sub(r"#{1,6}\s*",           "",    text)
        text = re.sub(r"\[(.+?)\]\(.+?\)",    r"\1", text)
        text = re.sub(r"https?://\S+",        "link", text)
        text = re.sub(r"\n+",                 ". ",  text)
        text = re.sub(r"\s{2,}",              " ",   text)
        text = re.sub(r"\.{2,}",              ".",   text)
        return text.strip()


# ──────────────────────────────────────────────
# STT Listener
# ──────────────────────────────────────────────

WAKE_WORDS = [
    "jarvis", "j.a.r.v.i.s", "hey jarvis",
    "selam jarvis", "merhaba jarvis",
]


class SpeechListener:

    def __init__(self,
                 on_result: Callable[[str], None],
                 speaker: SpeechSpeaker | None = None,
                 use_wake_word: bool = False,
                 language: str = "tr-TR") -> None:
        self._on_result     = on_result
        self._speaker       = speaker
        self._use_wake_word = use_wake_word
        self._language      = language
        self._wake_active   = not use_wake_word

        self._recogniser = sr.Recognizer()
        self._recogniser.energy_threshold         = settings.stt_energy_threshold
        self._recogniser.pause_threshold          = settings.stt_pause_threshold
        self._recogniser.dynamic_energy_threshold = True
        self._recogniser.non_speaking_duration    = 0.4

        self._running     = False
        self._paused      = False
        self._thread: threading.Thread | None = None
        self._heard_count = 0
        self._error_count = 0
        self._last_heard  = ""

        logger.info("SpeechListener hazır – dil={} wake={}",
                    language, use_wake_word)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="STT-Listener"
        )
        self._thread.start()
        logger.info("Dinleme başladı")

    def stop(self) -> None:
        self._running = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def set_language(self, lang: str) -> None:
        self._language = lang
        logger.info("STT dili: {}", lang)

    def recalibrate(self) -> None:
        try:
            with sr.Microphone() as source:
                self._recogniser.adjust_for_ambient_noise(source, duration=1)
            logger.info("Kalibrasyon tamam – eşik={}",
                        int(self._recogniser.energy_threshold))
        except Exception as e:
            logger.error("Kalibrasyon hatası: {}", e)

    def get_stats(self) -> dict:
        return {
            "duyulan":     self._heard_count,
            "hata":        self._error_count,
            "son_duyulan": self._last_heard,
            "aktif":       self._running,
            "dil":         self._language,
        }

    def _loop(self) -> None:
        with sr.Microphone() as source:
            logger.info("Mikrofon kalibre ediliyor...")
            self._recogniser.adjust_for_ambient_noise(source, duration=1.5)
            logger.info("Kalibrasyon tamamlandı – eşik={}",
                        int(self._recogniser.energy_threshold))

            while self._running:
                if self._paused or (self._speaker and self._speaker.is_speaking):
                    time.sleep(0.2)
                    continue

                try:
                    audio = self._recogniser.listen(
                        source, timeout=4, phrase_time_limit=20
                    )
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    logger.error("Mikrofon hatası: {}", e)
                    time.sleep(1)
                    continue

                threading.Thread(
                    target=self._recognize,
                    args=(audio,),
                    daemon=True,
                ).start()

    def _recognize(self, audio: sr.AudioData) -> None:
        try:
            text = self._recogniser.recognize_google(
                audio, language=self._language
            )
            if not text or not text.strip():
                return

            text = text.strip()
            logger.debug("Duyuldu: '{}'", text)
            self._heard_count += 1
            self._last_heard   = text

            if self._use_wake_word:
                text_lower = text.lower()
                is_wake    = any(w in text_lower for w in WAKE_WORDS)

                if not self._wake_active:
                    if is_wake:
                        self._wake_active = True
                        logger.info("Wake word algılandı")
                        if self._speaker:
                            self._speaker.speak("Efendim?",
                                                priority=Priority.HIGH)
                    return

                clean = text.lower()
                for w in WAKE_WORDS:
                    clean = clean.replace(w, "").strip()
                if clean:
                    self._on_result(clean)
                else:
                    if self._speaker:
                        self._speaker.speak("Sizi dinliyorum.",
                                            priority=Priority.HIGH)
            else:
                self._on_result(text)

        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            self._error_count += 1
            logger.warning("STT servis hatası: {}", e)
        except Exception as e:
            self._error_count += 1
            logger.error("Tanıma hatası: {}", e)