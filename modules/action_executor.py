"""
modules/action_executor.py
"""
from __future__ import annotations
import os
import sys
import subprocess
import platform
import shutil
import webbrowser
import time
import urllib.parse
from pathlib import Path
from typing import Any

import psutil
import pyautogui
from loguru import logger

from config.settings import settings


BLOCKED_COMMANDS = [
    "format ", "del /s", "rm -rf", "shutdown", "reboot",
    "reg delete", "bcdedit", "diskpart",
]

NAME_ALIASES: dict[str, str] = {
    "chrome":            "chrome",
    "google chrome":     "chrome",
    "firefox":           "firefox",
    "edge":              "msedge",
    "microsoft edge":    "msedge",
    "notepad":           "notepad",
    "not defteri":       "notepad",
    "calculator":        "calc",
    "hesap makinesi":    "calc",
    "paint":             "mspaint",
    "explorer":          "explorer",
    "dosya gezgini":     "explorer",
    "cmd":               "cmd",
    "komut istemi":      "cmd",
    "powershell":        "powershell",
    "task manager":      "taskmgr",
    "görev yöneticisi":  "taskmgr",
    "word":              "winword",
    "excel":             "excel",
    "powerpoint":        "powerpnt",
    "vscode":            "code",
    "vs code":           "code",
    "spotify":           "spotify",
    "discord":           "discord",
    "telegram":          "telegram",
    "whatsapp":          "whatsapp",
    "steam":             "steam",
    "obs":               "obs64",
    "vlc":               "vlc",
    "zoom":              "zoom",
}

# WhatsApp Web URL şeması
WHATSAPP_WEB = "https://web.whatsapp.com"


class ActionResult:
    def __init__(self, success: bool, output: str = "", error: str = "") -> None:
        self.success = success
        self.output  = output
        self.error   = error

    def to_dict(self) -> dict:
        return {"success": self.success, "output": self.output, "error": self.error}


class ActionExecutor:

    def __init__(self) -> None:
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE    = 0.05
        logger.info("ActionExecutor hazır – platform={}", platform.system())

    def execute(self, action: dict[str, Any]) -> ActionResult:
        tool   = action.get("tool", "")
        params = action.get("params", {})
        logger.info("Tool='{}' params={}", tool, params)

        dispatch = {
            "open_app":           self._open_app,
            "close_app":          self._close_app,
            "close_jarvis":       self._close_jarvis,
            "open_url":           self._open_url,
            "search_web":         self._search_web,
            "whatsapp_send":      self._whatsapp_send,
            "type_text":          self._type_text,
            "hotkey":             self._hotkey,
            "wait":               self._wait,
            "take_screenshot":    self._take_screenshot,
            "run_command":        self._run_command,
            "system_info":        self._system_info,
            "file_create":        self._file_create,
            "file_read":          self._file_read,
            "file_delete":        self._file_delete,
            "move_mouse":         self._move_mouse,
            "click":              self._click,
        }

        fn = dispatch.get(tool)
        if fn is None:
            return ActionResult(False, error=f"Bilinmeyen araç: {tool}")
        try:
            return fn(**params)
        except TypeError as e:
            return ActionResult(False, error=f"Hatalı parametre ({tool}): {e}")
        except Exception as e:
            logger.error("Tool '{}' hatası: {}", tool, e)
            return ActionResult(False, error=str(e))

    # ────── Uygulama Aç ──────

    def _open_app(self, name: str) -> ActionResult:
        key = name.lower().strip()
        exe = NAME_ALIASES.get(key, key)

        # WhatsApp Web'e yönlendir
        if exe == "whatsapp":
            webbrowser.open(WHATSAPP_WEB)
            return ActionResult(True, output="WhatsApp Web açıldı.")

        # 1. PATH'de ara
        found = shutil.which(exe)
        if found:
            subprocess.Popen([found], shell=False)
            return ActionResult(True, output=f"Açıldı: {name}")

        # 2. Shell ile dene
        try:
            subprocess.Popen(exe, shell=True)
            return ActionResult(True, output=f"Açıldı: {name}")
        except Exception:
            pass

        # 3. where komutu ile bul
        try:
            r = subprocess.run(
                f'where "{exe}"', shell=True,
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                path = r.stdout.strip().split("\n")[0]
                subprocess.Popen([path], shell=False)
                return ActionResult(True, output=f"Açıldı: {name}")
        except Exception:
            pass

        # 4. os.startfile
        try:
            os.startfile(exe)
            return ActionResult(True, output=f"Açıldı: {name}")
        except Exception:
            pass

        return ActionResult(False, error=f"'{name}' bulunamadı veya açılamadı.")

    # ────── Uygulama Kapat ──────

    def _close_app(self, name: str) -> ActionResult:
        key = name.lower().strip()

        # JARVIS'i kendisi kapatmak istiyorsa
        if any(k in key for k in ("jarvis", "j.a.r.v.i.s", "asistan", "uygulama")):
            return self._close_jarvis()

        killed = []
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                proc_name = proc.info["name"].lower()
                if key in proc_name or proc_name.replace(".exe", "") in key:
                    proc.terminate()
                    killed.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed:
            return ActionResult(True, output=f"Kapatıldı: {', '.join(killed)}")
        return ActionResult(False, error=f"'{name}' adında çalışan uygulama bulunamadı.")

    def _close_jarvis(self) -> ActionResult:
        """J.A.R.V.I.S. penceresini kapat."""
        try:
            import tkinter as tk
            # GUI'yi ana thread'den kapat
            for widget in tk._default_root.winfo_children():
                pass
            tk._default_root.after(500, tk._default_root.destroy)
            return ActionResult(True, output="J.A.R.V.I.S. kapatılıyor.")
        except Exception:
            # Fallback: process'i kendisi kapat
            os._exit(0)

    # ────── WhatsApp Mesaj ──────

    def _whatsapp_send(self, contact: str, message: str) -> ActionResult:
        """
        WhatsApp Web üzerinden mesaj gönderir.
        Önce WhatsApp Web'i açar, kullanıcı arar, mesajı yazar.
        """
        # WhatsApp Web'i aç
        webbrowser.open(WHATSAPP_WEB)
        time.sleep(4)  # Sayfa yüklensin

        # Ctrl+Alt+/ ile arama kutusunu aç (WhatsApp Web kısayolu)
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(1)

        # Kişi adını yaz
        pyautogui.typewrite(contact, interval=0.08)
        time.sleep(2)

        # Enter ile kişiyi seç
        pyautogui.press("enter")
        time.sleep(1)

        # Mesaj kutusuna tıkla ve mesajı yaz
        pyautogui.press("tab")
        time.sleep(0.5)
        pyautogui.typewrite(message, interval=0.05)
        time.sleep(0.5)

        # Göndermeden önce dur — kullanıcı onaylasın
        # pyautogui.press("enter")  # Otomatik göndermek için aktif et

        return ActionResult(
            True,
            output=f"WhatsApp Web açıldı, '{contact}' arandı, mesaj yazıldı."
        )

    # ────── Web ──────

    def _open_url(self, url: str) -> ActionResult:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return ActionResult(True, output=f"Açıldı: {url}")

    def _search_web(self, query: str) -> ActionResult:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(url)
        return ActionResult(True, output=f"Aranıyor: {query}")

    # ────── Klavye / Mouse ──────

    def _type_text(self, text: str, interval: float = 0.05) -> ActionResult:
        time.sleep(0.3)
        # Türkçe karakter desteği için clipboard kullan
        try:
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            pyautogui.typewrite(text, interval=interval)
        return ActionResult(True, output=f"{len(text)} karakter yazıldı.")

    def _hotkey(self, keys: list[str]) -> ActionResult:
        pyautogui.hotkey(*keys)
        return ActionResult(True, output=f"Kısayol: {'+'.join(keys)}")

    def _wait(self, seconds: float = 1.0) -> ActionResult:
        time.sleep(seconds)
        return ActionResult(True, output=f"{seconds}s beklendi.")

    def _move_mouse(self, x: int, y: int, duration: float = 0.3) -> ActionResult:
        pyautogui.moveTo(x, y, duration=duration)
        return ActionResult(True, output=f"Mouse: ({x}, {y})")

    def _click(self, x: int, y: int, button: str = "left") -> ActionResult:
        pyautogui.click(x, y, button=button)
        return ActionResult(True, output=f"Tıklandı: ({x}, {y})")

    # ────── Sistem ──────

    def _take_screenshot(self, path: str = "") -> ActionResult:
        if not path:
            path = str(settings.data_dir / f"screenshot_{int(time.time())}.png")
        img = pyautogui.screenshot()
        img.save(path)
        return ActionResult(True, output=f"Ekran görüntüsü: {path}")

    def _run_command(self, cmd: str, shell: bool = True) -> ActionResult:
        for blocked in BLOCKED_COMMANDS:
            if blocked in cmd.lower():
                return ActionResult(False, error="Güvenlik filtresi bu komutu engelledi.")
        try:
            result = subprocess.run(
                cmd, shell=shell, capture_output=True,
                text=True, timeout=30,
                encoding="utf-8", errors="replace"
            )
            out = result.stdout[:2000] + result.stderr[:500]
            return ActionResult(result.returncode == 0, output=out)
        except subprocess.TimeoutExpired:
            return ActionResult(False, error="Komut zaman aşımına uğradı.")
        except Exception as e:
            return ActionResult(False, error=str(e))

    def _system_info(self) -> ActionResult:
        info = {
            "cpu_percent":  psutil.cpu_percent(interval=0.5),
            "ram_percent":  psutil.virtual_memory().percent,
            "ram_used_gb":  round(psutil.virtual_memory().used / 1e9, 2),
            "disk_percent": psutil.disk_usage("/").percent,
            "platform":     platform.platform(),
        }
        return ActionResult(True, output=str(info))

    # ────── Dosya ──────

    def _file_create(self, path: str, content: str = "") -> ActionResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ActionResult(True, output=f"Oluşturuldu: {path}")
        except Exception as e:
            return ActionResult(False, error=str(e))

    def _file_read(self, path: str) -> ActionResult:
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            return ActionResult(True, output=content[:4000])
        except Exception as e:
            return ActionResult(False, error=str(e))

    def _file_delete(self, path: str) -> ActionResult:
        try:
            p = Path(path)
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return ActionResult(True, output=f"Silindi: {path}")
        except Exception as e:
            return ActionResult(False, error=str(e))