"""
tools/autostart.py
──────────────────
Windows autostart integration via registry.
Non-Windows platforms silently skip.
"""

from __future__ import annotations
import sys
from pathlib import Path
from loguru import logger


APP_NAME = "JARVIS_Assistant"


def enable_autostart() -> bool:
    """Add JARVIS to Windows startup registry."""
    if sys.platform != "win32":
        logger.info("Autostart only supported on Windows")
        return False
    try:
        import winreg
        exe = sys.executable
        script = str(Path(__file__).parent.parent / "main.py")
        cmd = f'"{exe}" "{script}"'

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        logger.info("Autostart enabled")
        return True
    except Exception as e:
        logger.error("Failed to enable autostart: {}", e)
        return False


def disable_autostart() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
        logger.info("Autostart disabled")
        return True
    except FileNotFoundError:
        return True  # already not set
    except Exception as e:
        logger.error("Failed to disable autostart: {}", e)
        return False


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
