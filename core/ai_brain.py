"""
core/ai_brain.py
"""
from __future__ import annotations
import json
import time
import hashlib
import re
from typing import Any
from collections import OrderedDict

from loguru import logger

from config.settings import settings
from memory.memory_manager import MemoryManager


_SYSTEM_PROMPT = """You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), a desktop AI assistant on Windows.

## CRITICAL RULE
You MUST respond with ONLY a valid JSON object. No markdown. No explanation. No code fences. JUST RAW JSON starting with { and ending with }

## RESPONSE SCHEMA
{
  "intent": "string",
  "plan": ["step 1", "step 2"],
  "actions": [{"tool": "tool_name", "params": {}}],
  "risk_level": "low",
  "requires_confirmation": false,
  "response_text": "What you say out loud to the user"
}

## AVAILABLE TOOLS
- open_app: {"name": "app_name"}
- close_app: {"name": "app_name"}
- open_url: {"url": "https://..."}
- search_web: {"query": "..."}
- type_text: {"text": "..."}
- hotkey: {"keys": ["ctrl", "c"]}
- wait: {"seconds": 1.5}
- take_screenshot: {}
- run_command: {"cmd": "...", "shell": true}
- system_info: {}
- file_create: {"path": "...", "content": "..."}
- file_read: {"path": "..."}
- file_delete: {"path": "..."}
- move_mouse: {"x": 0, "y": 0}
- click: {"x": 0, "y": 0, "button": "left"}

## CHAIN EXAMPLES

User: "open chrome and go to youtube"
{"intent":"open_browser","plan":["Open Chrome","Navigate to YouTube"],"actions":[{"tool":"open_app","params":{"name":"chrome"}},{"tool":"wait","params":{"seconds":2}},{"tool":"open_url","params":{"url":"https://youtube.com"}}],"risk_level":"low","requires_confirmation":false,"response_text":"Opening Chrome and navigating to YouTube."}

User: "whatsapp'ta Yunus Emre Peker'e mesaj yaz"
{"intent":"send_message","plan":["WhatsApp Web aç","Kişiyi ara","Mesajı yaz"],"actions":[{"tool":"whatsapp_send","params":{"contact":"Yunus Emre Peker","message":"Bu bir deneme metnidir."}}],"risk_level":"medium","requires_confirmation":true,"response_text":"WhatsApp Web açılıyor ve mesaj yazılıyor."}

User: "J.A.R.V.I.S. penceresini kapat"
{"intent":"close_self","plan":["JARVIS'i kapat"],"actions":[{"tool":"close_jarvis","params":{}}],"risk_level":"low","requires_confirmation":false,"response_text":"Kapatıyorum efendim. Görüşmek üzere."}
User: "selam" or "hello" or "merhaba"
{"intent":"greeting","plan":[],"actions":[],"risk_level":"low","requires_confirmation":false,"response_text":"Merhaba efendim! Size nasıl yardımcı olabilirim?"}

User: "Chrome'u aç ardından YouTube'a gir"
{"intent":"open_browser","plan":["Chrome'u aç","YouTube'a git"],"actions":[{"tool":"open_app","params":{"name":"chrome"}},{"tool":"wait","params":{"seconds":2}},{"tool":"open_url","params":{"url":"https://youtube.com"}}],"risk_level":"low","requires_confirmation":false,"response_text":"Chrome açılıyor ve YouTube'a yönlendiriyorum."}

User: "Heijan" or any artist/person name
{"intent":"search","plan":["Search for Heijan"],"actions":[{"tool":"search_web","params":{"query":"Heijan"}}],"risk_level":"low","requires_confirmation":false,"response_text":"Heijan için arama yapıyorum."}

## RULES
1. response_text MUST be in the SAME LANGUAGE the user used
2. For greetings/questions with no action: set actions to empty array []
3. Always add wait after open_app
4. risk_level high = requires_confirmation true
5. delete/format/shutdown = always high risk
6. YouTube search URL: https://www.youtube.com/results?search_query=WORDS
7. Google search URL: https://www.google.com/search?q=WORDS
"""


class _LRUCache:
    def __init__(self, maxsize: int = 100) -> None:
        self._cache: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = 300

    def _key(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def get(self, text: str) -> dict | None:
        k = self._key(text)
        if k in self._cache:
            result, ts = self._cache[k]
            if time.time() - ts < self._ttl:
                self._cache.move_to_end(k)
                return result
            del self._cache[k]
        return None

    def set(self, text: str, value: dict) -> None:
        k = self._key(text)
        self._cache[k] = (value, time.time())
        self._cache.move_to_end(k)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


class AIBrain:
    def __init__(self, memory: MemoryManager) -> None:
        api_key = settings.get_api_key()
        if not api_key or api_key in ("", "your_gemini_api_key_here"):
            raise RuntimeError(
                "Gemini API key yapılandırılmamış. .env dosyasını kontrol edin."
            )

        self._memory  = memory
        self._history: list[dict] = []
        self._cache   = _LRUCache()
        self._sdk     = "none"

        try:
            import google.genai as genai
            from google.genai import types
            self._client = genai.Client(api_key=api_key)
            self._types  = types
            self._sdk    = "new"
            logger.info("AIBrain hazır – google-genai | model={}", settings.gemini_model)
        except ImportError:
            pass

        if self._sdk == "none":
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=api_key)
                self._model_old = genai_old.GenerativeModel(
                    model_name=settings.gemini_model,
                    system_instruction=_SYSTEM_PROMPT,
                )
                self._chat_old = self._model_old.start_chat(history=[])
                self._sdk = "old"
                logger.warning("Eski SDK kullanılıyor.")
            except ImportError:
                raise ImportError("pip install google-genai çalıştırın.")

    def process(self, user_input: str) -> dict[str, Any]:
        # Cache kontrolü
        cache_key = user_input.lower().strip()
        cached = self._cache.get(cache_key)
        if cached:
            logger.debug("Cache hit: {}", user_input[:50])
            return cached

        prompt = self._build_prompt(user_input)

        for attempt in range(3):
            try:
                if attempt > 0:
                    wait = 2 ** attempt
                    logger.info("Yeniden deneniyor ({}/3), {}s...", attempt + 1, wait)
                    time.sleep(wait)

                raw = self._call_new(prompt) if self._sdk == "new" else self._call_old(prompt)
                result = self._parse(raw)

                if result["intent"] != "error" and not result.get("requires_confirmation"):
                    self._cache.set(cache_key, result)

                return result

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    delay = self._retry_delay(err)
                    logger.warning("Rate limit – {}s bekleniyor.", delay)
                    time.sleep(min(delay, 60))
                elif "thought" in err.lower() and "400" in err:
                    logger.warning("Thought signature hatası – history temizlendi.")
                    self._history.clear()
                else:
                    logger.error("API hatası (deneme {}): {}", attempt + 1, err[:200])
                    if attempt == 2:
                        break

        return self._fallback("Bağlantı sorunu yaşıyorum, lütfen tekrar deneyin.")

    def _build_prompt(self, user_input: str) -> str:
        parts = [user_input]
        recent = self._memory.get_recent_context(3)
        if recent:
            ctx = "\n".join(f"- {e['key']}: {e['value']}" for e in recent)
            parts.append(f"\n\nContext:\n{ctx}")
        return "".join(parts)

    def _call_new(self, prompt: str) -> str:
        contents = []
        for msg in self._history[-10:]:
            contents.append(
                self._types.Content(
                    role=msg["role"],
                    parts=[self._types.Part(text=msg["text"])]
                )
            )
        contents.append(
            self._types.Content(
                role="user",
                parts=[self._types.Part(text=prompt)]
            )
        )

        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=self._types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=1024,
            ),
        )

        text = response.text or ""
        self._history.append({"role": "user", "text": prompt})
        self._history.append({"role": "model", "text": text})
        if len(self._history) > 20:
            self._history = self._history[-16:]
        return text

    def _call_old(self, prompt: str) -> str:
        return self._chat_old.send_message(prompt).text or ""

    def _parse(self, raw: str) -> dict[str, Any]:
        logger.debug("Ham yanıt: {}", raw[:300])
        cleaned = raw.strip()

        # Markdown temizle
        if "```" in cleaned:
            for part in cleaned.split("```"):
                s = part.strip().lstrip("json").strip()
                if s.startswith("{"):
                    cleaned = s
                    break

        # Direkt parse
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # İçinde JSON ara
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    result = json.loads(m.group())
                except json.JSONDecodeError:
                    logger.warning("JSON parse başarısız. Ham: {}", cleaned[:200])
                    return self._fallback("Anlayamadım, tekrar söyler misiniz?")
            else:
                logger.warning("JSON bulunamadı. Ham: {}", cleaned[:200])
                return self._fallback("Anlayamadım, tekrar söyler misiniz?")

        result.setdefault("intent",                "unknown")
        result.setdefault("plan",                  [])
        result.setdefault("actions",               [])
        result.setdefault("risk_level",            "low")
        result.setdefault("requires_confirmation", False)
        result.setdefault("response_text",         "Tamam.")

        logger.info("PLAN → intent={} risk={} steps={}",
                    result["intent"], result["risk_level"], len(result["actions"]))
        return result

    def analyze_image(self, image_bytes: bytes,
                      prompt: str = "Describe what you see.") -> str:
        try:
            if self._sdk == "new":
                import base64
                b64 = base64.b64encode(image_bytes).decode()
                response = self._client.models.generate_content(
                    model=settings.gemini_model,
                    contents=[self._types.Content(parts=[
                        self._types.Part(inline_data=self._types.Blob(
                            mime_type="image/jpeg", data=b64
                        )),
                        self._types.Part(text=prompt),
                    ])],
                )
                return response.text or "Görsel analiz edildi."
            else:
                return self._model_old.generate_content(
                    [prompt, {"mime_type": "image/jpeg", "data": image_bytes}]
                ).text
        except Exception as e:
            logger.error("Görsel analiz hatası: {}", e)
            return "Görseli analiz edemedim."

    def free_chat(self, message: str) -> str:
        try:
            if self._sdk == "new":
                response = self._client.models.generate_content(
                    model=settings.gemini_model,
                    contents=message,
                    config=self._types.GenerateContentConfig(
                        system_instruction="Sen J.A.R.V.I.S.'sin. Samimi ve kısa konuş. Max 2 cümle.",
                        max_output_tokens=256,
                    ),
                )
                return response.text or "..."
            else:
                return self._chat_old.send_message(message).text
        except Exception as e:
            logger.error("free_chat hatası: {}", e)
            return "Şu an bağlanamıyorum."

    def clear_history(self) -> None:
        self._history.clear()
        self._cache.clear()
        logger.info("History ve cache temizlendi.")

    @staticmethod
    def _retry_delay(error_str: str) -> float:
        m = re.search(r"retry[^\d]*(\d+(?:\.\d+)?)\s*s", error_str, re.I)
        return float(m.group(1)) if m else 15.0

    @staticmethod
    def _fallback(text: str) -> dict:
        return {
            "intent":                "error",
            "plan":                  [],
            "actions":               [],
            "risk_level":            "low",
            "requires_confirmation": False,
            "response_text":         text,
        }