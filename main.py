"""
main.py — J.A.R.V.I.S. giriş noktası
"""
from __future__ import annotations
import time
import sys
import threading

from core.logger import setup_logging
from loguru import logger

from config.settings import settings
from memory.memory_manager import MemoryManager
from core.ai_brain import AIBrain
from core.agent import AgentLoop
from modules.speech import SpeechSpeaker, SpeechListener
from modules.action_executor import ActionExecutor
from tools.autostart import enable_autostart, is_autostart_enabled


def main() -> None:
    logger.info("=" * 60)
    logger.info("  J.A.R.V.I.S. starting up")
    logger.info("=" * 60)

    memory = MemoryManager()

    try:
        brain = AIBrain(memory)
    except RuntimeError as e:
        logger.critical("Cannot start without API key: {}", e)
        print(f"\n[FATAL] {e}\nPlease set GEMINI_API_KEY in your .env file.\n")
        sys.exit(1)

    speaker = SpeechSpeaker()
    executor = ActionExecutor()

    from modules.vision import VisionModule
    vision = VisionModule(memory)

    try:
        from gui.main_window import JarvisWindow
    except ImportError as e:
        logger.warning("GUI unavailable ({}), headless mode", e)
        _run_headless(memory, brain, speaker, executor)
        return

    gui = JarvisWindow(
        on_command=lambda text: agent.submit(text),
        on_listen_toggle=lambda active: None,  # artık kullanılmıyor
        on_camera_toggle=_make_camera_toggle(vision),
        on_register_face=lambda name: _register_face(vision, name, speaker),
    )

    vision._on_frame = lambda frame: gui.update_camera_frame(
        vision.annotated_frame() or frame
    )

    agent = AgentLoop(
        memory=memory,
        brain=brain,
        executor=executor,
        speaker=speaker,
        on_status=gui.set_status,
        on_log=gui.append_log,
        on_confirm=gui.confirm_dialog,
    )
    agent.start()

    # Otomatik sürekli dinleme — tuşa basmak gerekmez
    listener = SpeechListener(on_result=agent.submit)
    listener.start()

    if settings.autostart_on_boot and not is_autostart_enabled():
        enable_autostart()

    # Worker thread'in hazır olmasını bekle
    time.sleep(1.5)
    speaker.speak(
        "J.A.R.V.I.S. online. All systems nominal. "
        "How can I assist you today?"
    )
    gui.set_status("READY")
    gui.append_log("J.A.R.V.I.S. initialised. All systems nominal.")
    gui.append_log("Sürekli dinleme aktif — konuşabilirsiniz.")

    gui.run()


def _make_camera_toggle(vision):
    def toggle(active: bool):
        if active:
            ok = vision.start()
            if not ok:
                logger.error("Kamera açılamadı")
        else:
            vision.stop()
    return toggle


def _register_face(vision, name: str, speaker: SpeechSpeaker) -> None:
    ok = vision.register_face(name)
    if ok:
        speaker.speak(f"Face registered for {name}.")
    else:
        speaker.speak("Face registration failed. Please ensure your face is visible.")


def _run_headless(memory, brain, speaker, executor) -> None:
    logger.info("Headless CLI mode")
    from core.agent import AgentLoop

    agent = AgentLoop(
        memory=memory, brain=brain, executor=executor, speaker=speaker,
        on_status=lambda s: print(f"[STATUS] {s}"),
        on_log=lambda l: print(f"[LOG] {l}"),
        on_confirm=lambda m: input(f"\n{m}\nApprove? [y/N] ").lower() == "y",
    )
    agent.start()
    speaker.speak("J.A.R.V.I.S. online in CLI mode.")

    print("\nJ.A.R.V.I.S. CLI – 'exit' yazarak çıkabilirsiniz\n")
    while True:
        try:
            cmd = input("Sen: ").strip()
            if cmd.lower() in ("exit", "quit"):
                break
            if cmd:
                agent.submit(cmd)
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()