import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLockFile, QThread, QTimer
from PySide6.QtWidgets import QApplication

from app.windows.main_window import MainWindow
from app.windows.project_window import ProjectWindow
from core.processing import check_cancelled
from core.project_manager import ProjectManager
from core.results import AUDIO_PATH, TRANSCRIPT_PATH, SILENCES_PATH
from core.storage import write_json
from tests.helpers import make_wav, transcript, silences


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        source = self.root / "source.mp4"
        source.touch()
        manager = ProjectManager(self.root / "projects")
        self.project = manager.create_project("UI", source, "YouTube", "Clean")
        self.warnings = patch("app.windows.project_window.QMessageBox.warning")
        self.warning = self.warnings.start()
        self.addCleanup(self.warnings.stop)
        self.window = ProjectWindow(self.project)
        self.window.show()
        self.wait_until(lambda: self.window.worker is None and self.window.status_label.text() != "Pronto para analisar o vídeo.")
        self.addCleanup(self.cleanup_window)

    def wait_until(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            time.sleep(0.005)
        self.fail("A operação Qt não terminou a tempo.")

    def cleanup_window(self):
        self.window.close()
        self.wait_until(lambda: self.window.worker is None)
        self.window.close()
        self.app.processEvents()

    def test_main_window_starts(self):
        main = MainWindow()
        main.show()
        self.app.processEvents()
        self.assertTrue(main.isVisible())
        main.close()

    def test_worker_keeps_event_loop_responsive_and_blocks_double_start(self):
        ticks = []
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        thread_checks = []
        def work(*args, **kwargs):
            thread_checks.append(QThread.currentThread() != self.app.thread())
            time.sleep(0.2)
            return {"audio_path": AUDIO_PATH, "transcript": transcript(), "silences": silences(), "errors": []}
        try:
            with patch("app.processing_worker.TranscriptionPipeline.run", side_effect=work) as run:
                self.window.process_button.click()
                self.assertFalse(self.window.process_button.isEnabled())
                self.window._start_worker("process")
                self.wait_until(lambda: self.window.worker is None)
                run.assert_called_once()
            self.assertGreater(len(ticks), 3)
            self.assertEqual(thread_checks, [True])
            self.assertIn("Idioma: pt", self.window.result_label.text())
            self.assertTrue(self.window.process_button.isEnabled())
        finally:
            timer.stop()

    def test_close_cancels_without_destroying_running_thread(self):
        def work(*args, **kwargs):
            while not kwargs["cancel"].wait(0.01):
                pass
            check_cancelled(kwargs["cancel"])
        with patch("app.processing_worker.TranscriptionPipeline.run", side_effect=work):
            self.window.process_button.click()
            self.window.close()
            self.assertIsNotNone(self.window.worker)
            self.wait_until(lambda: self.window.worker is None)
            self.assertFalse(self.window.isVisible())

    def test_error_signal_restores_controls(self):
        with patch("app.processing_worker.TranscriptionPipeline.run", side_effect=RuntimeError("download failed")):
            self.window.process_button.click()
            self.wait_until(lambda: self.window.worker is None)
        self.assertIn("download failed", self.window.status_label.text())
        self.assertTrue(self.window.process_button.isEnabled())
        self.warning.assert_called_once()

    def test_media_analysis_runs_outside_main_thread(self):
        calls = []
        metadata = {"container": {"duration_display": "00:01"}, "video": {}, "audio": {"present": False}}
        def probe(*args, **kwargs):
            calls.append(QThread.currentThread() != self.app.thread())
            return metadata
        with patch("media.ffmpeg_tools.FFmpegTools.probe", side_effect=probe):
            self.window.analyze_button.click()
            self.wait_until(lambda: self.window.worker is None)
        self.assertEqual(calls, [True])
        self.assertEqual(self.window.duration_value.text(), "00:01")

    def test_project_lock_prevents_second_worker(self):
        lock = QLockFile(str(self.project / ".processing.lock"))
        self.assertTrue(lock.tryLock(0))
        try:
            with patch("app.processing_worker.TranscriptionPipeline.run") as run:
                self.window.process_button.click()
                self.wait_until(lambda: self.window.worker is None)
                run.assert_not_called()
            self.assertIn("outra janela", self.window.status_label.text())
        finally:
            lock.unlock()

    def test_reopen_loads_results_without_transcribing(self):
        make_wav(self.project / AUDIO_PATH)
        write_json(self.project / TRANSCRIPT_PATH, transcript())
        write_json(self.project / SILENCES_PATH, silences())
        self.window.close()
        with patch("app.processing_worker.TranscriptionPipeline.run") as run:
            self.window = ProjectWindow(self.project)
            self.window.show()
            self.wait_until(lambda: "Idioma: pt" in self.window.result_label.text())
            self.wait_until(lambda: self.window.worker is None)
            run.assert_not_called()
        self.assertIn("Silêncios encontrados: 1", self.window.result_label.text())


if __name__ == "__main__":
    unittest.main()
