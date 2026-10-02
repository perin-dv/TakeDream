import tempfile
import unittest
from pathlib import Path

from core.project_manager import ProjectManager


class DashboardDataTests(unittest.TestCase):
    def test_project_preferences_and_lists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"fake-video")

            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Projeto Bonito",
                source,
                "YouTube",
                "Dinâmico",
                aspect_ratio="9:16",
                captions_enabled=True,
                auto_zoom=True,
                caption_style="Impacto",
                export_quality="720p",
            )

            _, data = manager.load_project(project)

            self.assertEqual(data["aspect_ratio"], "9:16")
            self.assertEqual(
                data["review_settings"]["aspect_ratio"],
                "9:16",
            )
            self.assertTrue(
                data["review_settings"]["captions_enabled"]
            )
            self.assertTrue(
                data["review_settings"]["auto_zoom"]
            )
            self.assertEqual(
                data["review_settings"]["caption_style"],
                "Impacto",
            )
            self.assertEqual(
                data["preferred_export_profile"],
                "720p",
            )

            projects = manager.list_projects()
            self.assertEqual(len(projects), 1)
            self.assertEqual(
                projects[0]["name"],
                "Projeto Bonito",
            )
            self.assertEqual(
                projects[0]["aspect_ratio"],
                "9:16",
            )

    def test_list_exports_returns_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"fake-video")

            manager = ProjectManager(root / "projects")
            project = manager.create_project(
                "Export",
                source,
                "YouTube",
                "Clean",
            )

            export = (
                project
                / "exports"
                / "video_final_1080p_16x9.mp4"
            )
            export.write_bytes(b"final-video")

            exports = manager.list_exports()

            self.assertEqual(len(exports), 1)
            self.assertEqual(
                exports[0]["project_name"],
                "Export",
            )
            self.assertEqual(
                exports[0]["filename"],
                "video_final_1080p_16x9.mp4",
            )
            self.assertGreater(
                exports[0]["size_bytes"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
