"""
core/agent.py
"""
from __future__ import annotations
import threading
import time
import uuid
from typing import Callable, Any

from loguru import logger

from core.ai_brain import AIBrain
from memory.memory_manager import MemoryManager
from modules.action_executor import ActionExecutor
from modules.speech import SpeechSpeaker
from config.settings import settings


class AgentLoop:

    def __init__(self,
                 memory: MemoryManager,
                 brain: AIBrain,
                 executor: ActionExecutor,
                 speaker: SpeechSpeaker,
                 on_status: Callable[[str], None] | None = None,
                 on_log: Callable[[str], None] | None = None,
                 on_confirm: Callable[[str], bool] | None = None) -> None:
        self._memory     = memory
        self._brain      = brain
        self._executor   = executor
        self._speaker    = speaker
        self._on_status  = on_status
        self._on_log     = on_log
        self._on_confirm = on_confirm

        self._input_queue: list[str] = []
        self._lock        = threading.Lock()
        self._running     = False
        self._current_user= "User"

    def submit(self, text: str) -> None:
        with self._lock:
            self._input_queue.append(text)

    def set_user(self, name: str) -> None:
        self._current_user = name

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()
        logger.info("AgentLoop başlatıldı")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            command = None
            with self._lock:
                if self._input_queue:
                    command = self._input_queue.pop(0)
            if command:
                self._process_command(command)
            else:
                time.sleep(0.05)

    def _process_command(self, command: str) -> None:
        task_id = str(uuid.uuid4())[:8]
        self._log(f"[{task_id}] SEN: {command}")
        self._status("Düşünüyor...")

        self._memory.remember("last_command", command)
        self._memory.set_task(task_id, {"command": command, "status": "planning"})

        # ── PLAN ──
        try:
            plan = self._brain.process(command)
        except Exception as e:
            logger.error("Brain hatası: {}", e)
            msg = "AI çekirdeğime bağlanamıyorum."
            self._log(f"JARVIS: {msg}")
            self._speak_blocking(msg)
            self._memory.complete_task(task_id)
            return

        intent        = plan.get("intent", "unknown")
        actions       = plan.get("actions", [])
        risk          = plan.get("risk_level", "low")
        needs_confirm = plan.get("requires_confirmation", False)
        response_txt  = plan.get("response_text", "Tamam.")
        follow_up     = plan.get("follow_up", "")

        self._log(f"[{task_id}] PLAN: intent={intent} risk={risk} steps={len(actions)}")

        # ── ONAY ──
        if (needs_confirm or risk == "high") and settings.require_confirmation:
            action_desc = "\n".join(
                f"  • {a['tool']}({a.get('params', {})})" for a in actions
            )
            approved = self._confirm(
                f"Planlanan işlemler:\n{action_desc}\n\nDevam edilsin mi?"
            )
            if not approved:
                msg = "Anlaşıldı, iptal ettim."
                self._log(f"[{task_id}] İptal edildi.")
                self._log(f"JARVIS: {msg}")
                self._speak_blocking(msg)
                self._memory.complete_task(task_id)
                return

        # ── ACT + OBSERVE ──
        all_ok  = True
        results = []

        for i, action in enumerate(actions):
            tool = action.get("tool", "?")
            self._status(f"Çalışıyor: {tool} ({i+1}/{len(actions)})")
            self._memory.set_task(task_id, {
                "command": command,
                "status":  "executing",
                "step":    i + 1,
            })

            result = self._executor.execute(action)
            results.append(result)

            if result.success:
                self._log(f"[{task_id}] ✓ {tool}: {result.output[:100]}")
            else:
                all_ok = False
                self._log(f"[{task_id}] ✗ {tool}: {result.error[:100]}")

        # ── MEMORY UPDATE ──
        summary = "; ".join(
            r.output[:60] if r.success else f"HATA:{r.error[:40]}"
            for r in results
        )
        self._memory.log_command(
            user=self._current_user,
            command=command,
            intent=intent,
            result=summary,
            success=all_ok,
        )
        self._memory.remember("last_result", summary)

        if all_ok and actions:
            self._memory.learn_behaviour(
                trigger=command[:100],
                action=actions[0].get("tool", ""),
            )

        # ── RESPOND ──
        if not all_ok and actions:
            error_details = "; ".join(
                r.error[:50] for r in results if not r.success
            )
            response_txt = f"Bir sorun oluştu: {error_details}"

        self._status("Hazır")
        self._log(f"JARVIS: {response_txt}")

        # Önce yanıtı söyle, follow_up varsa onu da ekle
        full_response = response_txt
        if follow_up:
            full_response = f"{response_txt} {follow_up}"

        self._speak_blocking(full_response)

        self._memory.complete_task(task_id)
        logger.info("[{}] TAMAMLANDI success={}", task_id, all_ok)

    # ── Speak blocking — yanıt bitmeden devam etme ──
    def _speak_blocking(self, text: str) -> None:
        """Konuşma bitene kadar bekler — sıralı TTS garantisi."""
        if not text:
            return
        self._speaker.speak(text, blocking=True)

    def _status(self, msg: str) -> None:
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass

    def _log(self, msg: str) -> None:
        logger.info(msg)
        if self._on_log:
            try:
                self._on_log(msg)
            except Exception:
                pass

    def _confirm(self, msg: str) -> bool:
        if self._on_confirm:
            try:
                return self._on_confirm(msg)
            except Exception:
                return False
        return False