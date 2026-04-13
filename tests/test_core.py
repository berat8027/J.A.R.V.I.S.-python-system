"""
tests/test_core.py – Smoke tests (no camera/mic/GPU required)
"""
import sys, os, tempfile, pathlib, unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

for _m in ("pyautogui","cv2","speech_recognition","pyttsx3",
           "customtkinter","google.generativeai","PIL",
           "PIL.Image","PIL.ImageTk"):
    sys.modules.setdefault(_m, MagicMock())

class TestSettings(unittest.TestCase):
    def test_load(self):
        from config.settings import settings
        self.assertIsNotNone(settings.gemini_model)
        self.assertNotIn("AIza", repr(settings.gemini_api_key))
    def test_dirs(self):
        from config.settings import settings
        self.assertTrue(settings.data_dir.exists())

class TestMemory(unittest.TestCase):
    def _mgr(self):
        from memory.memory_manager import MemoryManager
        tmp = pathlib.Path(tempfile.mkdtemp()) / "t.db"
        return MemoryManager(db_url=f"sqlite:///{tmp}")

    def test_short_term(self):
        m = self._mgr()
        m.remember("k", "v")
        self.assertEqual(m.recall("k"), "v")

    def test_working(self):
        m = self._mgr()
        m.set_task("x", {"a": 1})
        self.assertEqual(m.get_task("x"), {"a": 1})
        m.complete_task("x")
        self.assertIsNone(m.get_task("x"))

    def test_command_log(self):
        m = self._mgr()
        m.log_command("u", "cmd", "intent", "ok", True)
        h = m.get_command_history(5)
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["intent"], "intent")

    def test_face(self):
        m = self._mgr()
        m.save_face_embedding("alice", [.1, .2, .3], "/tmp/a.jpg")
        faces = m.get_all_face_embeddings()
        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0]["user"], "alice")

    def test_learn(self):
        m = self._mgr()
        m.learn_behaviour("open chrome", "open_app")
        m.learn_behaviour("open chrome", "open_app")
        behaviours = m.get_learned_behaviours()
        self.assertGreater(behaviours[0]["confidence"], 0.5)

    def test_user_profile(self):
        m = self._mgr()
        m.upsert_user_profile("bob", {"theme": "dark"})
        p = m.get_user_profile("bob")
        self.assertIsNotNone(p)
        self.assertEqual(p["preferences"]["theme"], "dark")

    def test_recent_context(self):
        m = self._mgr()
        for i in range(12):
            m.remember(f"key{i}", i)
        ctx = m.get_recent_context(10)
        self.assertEqual(len(ctx), 10)

class TestExecutor(unittest.TestCase):
    def setUp(self):
        from modules.action_executor import ActionExecutor
        self.e = ActionExecutor()

    def test_sysinfo(self):
        r = self.e.execute({"tool": "system_info", "params": {}})
        self.assertTrue(r.success)
        self.assertIn("cpu_percent", r.output)

    def test_unknown(self):
        r = self.e.execute({"tool": "__bad__", "params": {}})
        self.assertFalse(r.success)

    def test_blocked(self):
        r = self.e.execute({
            "tool": "run_command",
            "params": {"cmd": "format c: /y", "shell": True}
        })
        self.assertFalse(r.success)
        self.assertIn("blocked", r.error.lower())

    def test_file_ops(self):
        p = os.path.join(tempfile.gettempdir(), "jarvis_test_q.txt")
        self.assertTrue(self.e.execute({"tool": "file_create",
                                        "params": {"path": p, "content": "hi"}}).success)
        r = self.e.execute({"tool": "file_read", "params": {"path": p}})
        self.assertIn("hi", r.output)
        self.assertTrue(self.e.execute({"tool": "file_delete",
                                        "params": {"path": p}}).success)

    def test_action_result_to_dict(self):
        from modules.action_executor import ActionResult
        r = ActionResult(True, output="ok", error="")
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["output"], "ok")

class TestHealth(unittest.TestCase):
    def test_report(self):
        from tools.health_reporter import get_health_report, format_health_speech
        r = get_health_report()
        for k in ("cpu_percent", "ram_percent", "disk_percent", "timestamp"):
            self.assertIn(k, r)
        txt = format_health_speech(r)
        self.assertIn("CPU", txt)
        self.assertIn("RAM", txt)

class TestScheduler(unittest.TestCase):
    def test_jobs(self):
        from tools.scheduler import TaskScheduler
        ts = TaskScheduler()
        ts.add_interval(60, lambda: None, label="hb")
        self.assertEqual(ts.list_jobs()[0]["label"], "hb")
        ts.stop()

if __name__ == "__main__":
    unittest.main(verbosity=2)
