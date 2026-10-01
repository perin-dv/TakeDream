import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from app.windows.new_project_dialog import NewProjectDialog


class NewProjectMediaSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _close_dialog(self, dialog):
        # QMediaPlayer/FFmpeg pode manter um handle do arquivo aberto no Windows
        # mesmo depois de stop(). Como estes testes usam TemporaryDirectory,
        # removemos a source explicitamente antes da limpeza da pasta.
        dialog.player.stop()
        dialog.player.setSource(QUrl())
        dialog.close()
        self.app.processEvents()

    def test_multiple_videos_are_forwarded_to_project_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "A001.mp4"
            second = root / "B001.mov"
            first.write_bytes(b"a")
            second.write_bytes(b"b")

            dialog = NewProjectDialog()
            try:
                added = dialog._add_media_paths([first, second])
                data = dialog.project_data()

                self.assertEqual(added, 2)
                self.assertEqual(len(dialog.selected_media_paths), 2)
                self.assertEqual(data["source_video"], str(first.resolve()))
                self.assertEqual(data["source_videos"], [str(second.resolve())])
                self.assertIn("2 vídeos", dialog.media_count_label.text())
            finally:
                self._close_dialog(dialog)

    def test_folder_selection_discovers_videos_recursively(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "CAM01").mkdir()
            (root / "DRONE").mkdir()
            (root / "CAM01" / "C001.mp4").write_bytes(b"a")
            (root / "DRONE" / "D001.m4v").write_bytes(b"b")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")

            dialog = NewProjectDialog()
            try:
                added = dialog._add_media_paths([root])

                self.assertEqual(added, 2)
                self.assertEqual(len(dialog.selected_media_paths), 2)
                names = {Path(value).name for value in dialog.selected_media_paths}
                self.assertEqual(names, {"C001.mp4", "D001.m4v"})
            finally:
                self._close_dialog(dialog)


if __name__ == "__main__":
    unittest.main()
