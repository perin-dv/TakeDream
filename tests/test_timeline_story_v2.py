import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.widgets.timeline_widget import TimelineWidget
from core.content_pipeline import load_content_analysis
from core.storage import write_json
from editor.edit_plan import build_edit_plan


class TimelineStoryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_wedding_plan_becomes_story_overlay_without_content_analysis_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "decisions").mkdir(parents=True)
            write_json(
                root / "decisions" / "wedding_assembly_plan.json",
                {
                    "schema_version": "0.3",
                    "estimated_duration_ms": 60000,
                    "clip_count": 4,
                    "media_count": 3,
                    "story_builder": "wedding-story-builder-v1",
                    "story_sections": [],
                    "clips": [
                        {
                            "timeline_start_ms": 0,
                            "timeline_end_ms": 10000,
                            "story_section": "making_of",
                        },
                        {
                            "timeline_start_ms": 10000,
                            "timeline_end_ms": 25000,
                            "story_section": "cerimonia",
                        },
                        {
                            "timeline_start_ms": 25000,
                            "timeline_end_ms": 40000,
                            "story_section": "cerimonia",
                        },
                        {
                            "timeline_start_ms": 40000,
                            "timeline_end_ms": 60000,
                            "story_section": "festa",
                        },
                    ],
                },
            )

            analysis = load_content_analysis(root)
            self.assertIsNotNone(analysis)
            story = analysis["wedding_story"]
            self.assertEqual(story["engine"], "wedding-story-timeline-v2")
            self.assertEqual(len(story["blocks"]), 3)
            self.assertEqual(story["blocks"][1]["section"], "cerimonia")
            self.assertEqual(story["blocks"][1]["duration_ms"], 30000)

    def test_timeline_accepts_real_story_blocks(self):
        widget = TimelineWidget()
        try:
            plan = build_edit_plan(
                60000,
                "Casamento",
                "Highlight",
                {"silences": []},
            )
            widget.set_plan(plan)
            widget.set_content_analysis(
                {
                    "schema_version": "0.1",
                    "wedding_story": {
                        "blocks": [
                            {
                                "section": "making_of",
                                "label": "Making of",
                                "start_ms": 0,
                                "end_ms": 20000,
                            },
                            {
                                "section": "cerimonia",
                                "label": "Cerimônia",
                                "start_ms": 20000,
                                "end_ms": 45000,
                            },
                            {
                                "section": "festa",
                                "label": "Festa",
                                "start_ms": 45000,
                                "end_ms": 60000,
                            },
                        ]
                    },
                }
            )
            self.assertEqual(len(widget.story_blocks()), 3)
            self.assertEqual(widget.story_blocks()[1]["label"], "Cerimônia")
            self.assertGreater(widget.sizeHint().height(), 100)
        finally:
            widget.close()


if __name__ == "__main__":
    unittest.main()
