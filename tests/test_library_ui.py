import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from app.ui.library import ExportCard, ProjectCard, ProjectGrid, Thumbnail, library_scroll
from app.ui.theme import apply_app_theme


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def project(self, path):
        return dict(project_dir=Path(path), name="Uma história " * 30,
                    profile="YouTube", style="Dinâmico", aspect_ratio="16:9",
                    source_filename="arquivo longo " * 30 + ".mp4",
                    status="review_rendered", updated_at="2026-09-25T12:00:00+00:00")

    def test_grid_reflows_without_horizontal_overflow_and_keeps_single_card_compact(self):
        for count in (1, 7):
            grid = ProjectGrid([ProjectCard(self.project("."), lambda: None, lambda: None) for _ in range(count)])
            scroll = library_scroll(grid)
            apply_app_theme(scroll)
            for width in (440, 840, 1160):
                scroll.resize(width, 560)
                scroll.show()
                for _ in range(5):
                    self.app.processEvents()
                self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                for card in grid.cards:
                    self.assertLessEqual(card.width(), 520)
                    self.assertEqual(card.height(), 326)
                if count > 1:
                    self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
            scroll.close()
            scroll.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_project_actions_and_status_use_the_supplied_project(self):
        calls = []
        card = ProjectCard(self.project("."), lambda: calls.append("project"), lambda: calls.append("folder"))
        for button in card.findChildren(QPushButton):
            button.click()
        self.assertEqual(calls, ["project", "folder"])
        self.assertIn("Revisado", [label.text() for label in card.findChildren(QLabel)])

    def test_export_metadata_is_not_guessed_for_custom_filenames(self):
        for filename, expected in (("video_final_1080p_9x16.mp4", {"1080p", "9:16"}), ("custom.mp4", set())):
            card = ExportCard(dict(project_name="Projeto", filename=filename,
                                   size_bytes=1024, modified_at=0), lambda: None, lambda: None)
            labels = {label.text() for label in card.findChildren(QLabel)}
            self.assertEqual(labels & {"1080p", "9:16"}, expected)

    def test_invalid_thumbnail_falls_back_without_changing_cached_files(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "cache" / "thumbnails"
            folder.mkdir(parents=True)
            image = folder / "thumb_001.jpg"
            image.write_bytes(b"invalid")
            thumb = Thumbnail(root)
            self.assertTrue(thumb.pixmap.isNull())
            self.assertEqual(image.read_bytes(), b"invalid")
