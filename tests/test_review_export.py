import tempfile
import unittest
from pathlib import Path

from core.export_pipeline import ExportPipeline
from core.project_manager import ProjectManager
from core.review_pipeline import ReviewRenderPipeline
from core.storage import write_json
from editor.edit_plan import build_edit_plan
from editor.review import (
    add_manual_cut,
    adjust_cut,
    edited_to_source_ms,
    restore_cut,
    source_to_edited_ms,
)
from renderer.export_profiles import get_export_profile
from renderer.ffmpeg_renderer import build_filter_graph


class ReviewPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_edit_plan(
            5000,
            "YouTube",
            "Dinâmico",
            {
                "silences": [
                    {
                        "start_ms": 1000,
                        "end_ms": 2200,
                        "duration_ms": 1200,
                    }
                ]
            },
        )

    def test_restore_cut_updates_stats(self):
        remove_index = next(
            index
            for index, segment in enumerate(self.plan["segments"])
            if segment["action"] == "remove"
        )

        before = self.plan["stats"]
        restored = restore_cut(self.plan, remove_index)
        after = restored["stats"]

        self.assertEqual(after["cuts"], before["cuts"] - 1)
        self.assertLess(
            after["removed_duration_ms"],
            before["removed_duration_ms"],
        )
        self.assertGreater(
            after["estimated_duration_ms"],
            before["estimated_duration_ms"],
        )

    def test_timeline_mapping_skips_removed_region(self):
        remove = next(
            segment
            for segment in self.plan["segments"]
            if segment["action"] == "remove"
        )

        edited_at_cut = source_to_edited_ms(
            self.plan,
            remove["start_ms"],
        )
        mapped_source = edited_to_source_ms(
            self.plan,
            edited_at_cut,
        )

        self.assertGreaterEqual(
            mapped_source,
            remove["end_ms"],
        )

    def test_manual_cut_splits_keep_segment_and_updates_stats(self):
        base = build_edit_plan(
            5000,
            "YouTube",
            "Clean",
            {"silences": []},
        )

        updated = add_manual_cut(base, 1200, 1800)

        self.assertEqual(updated["stats"]["cuts"], 1)
        self.assertEqual(updated["stats"]["removed_duration_ms"], 600)
        self.assertEqual(updated["stats"]["estimated_duration_ms"], 4400)

        removed = [
            segment
            for segment in updated["segments"]
            if segment["action"] == "remove"
        ]
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["start_ms"], 1200)
        self.assertEqual(removed[0]["end_ms"], 1800)
        self.assertEqual(removed[0]["reason"], "manual_cut")

    def test_manual_cut_normalizes_reversed_marks(self):
        base = build_edit_plan(
            3000,
            "YouTube",
            "Clean",
            {"silences": []},
        )

        updated = add_manual_cut(base, 1800, 1200)
        removed = next(
            segment
            for segment in updated["segments"]
            if segment["action"] == "remove"
        )

        self.assertEqual(
            (removed["start_ms"], removed["end_ms"]),
            (1200, 1800),
        )

    def test_adjust_cut_moves_selected_boundaries(self):
        remove_index = next(
            index
            for index, segment in enumerate(self.plan["segments"])
            if segment["action"] == "remove"
        )
        original = self.plan["segments"][remove_index]

        updated = adjust_cut(
            self.plan,
            remove_index,
            start_delta_ms=-100,
            end_delta_ms=100,
        )

        removed = [
            segment
            for segment in updated["segments"]
            if segment["action"] == "remove"
        ]

        self.assertEqual(len(removed), 1)
        self.assertEqual(
            removed[0]["start_ms"],
            original["start_ms"] - 100,
        )
        self.assertEqual(
            removed[0]["end_ms"],
            original["end_ms"] + 100,
        )

    def test_adjust_cut_rejects_inverted_range(self):
        base = build_edit_plan(
            2000,
            "YouTube",
            "Dinâmico",
            {
                "silences": [
                    {
                        "start_ms": 500,
                        "end_ms": 1400,
                        "duration_ms": 900,
                    }
                ]
            },
        )
        remove_index = next(
            index
            for index, segment in enumerate(base["segments"])
            if segment["action"] == "remove"
        )

        with self.assertRaises(ValueError):
            adjust_cut(
                base,
                remove_index,
                start_delta_ms=1000,
            )

    def test_export_profiles(self):
        self.assertIsNone(get_export_profile("original").height)
        self.assertEqual(get_export_profile("1080p").height, 1080)
        self.assertEqual(get_export_profile("720p").height, 720)
        self.assertEqual(get_export_profile("480p").height, 480)

    def test_scaled_filter_graph_contains_scale(self):
        graph = build_filter_graph(self.plan, output_height=720)
        self.assertIn("scale=-2:720:flags=lanczos[outv]", graph)


class FakeRenderer:
    def __init__(self):
        self.calls = []

    def render(self, source, destination, edit_plan, cancel=None, **options):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-video")
        self.calls.append(
            {
                "source": Path(source),
                "destination": destination,
                "plan": edit_plan,
                "options": options,
            }
        )
        return destination


class PipelineTests(unittest.TestCase):
    def _project(self, root):
        source = root / "source.mp4"
        source.write_bytes(b"source")

        manager = ProjectManager(root / "projects")
        project = manager.create_project(
            "Review",
            source,
            "YouTube",
            "Dinâmico",
        )

        plan = build_edit_plan(
            5000,
            "YouTube",
            "Dinâmico",
            {
                "silences": [
                    {
                        "start_ms": 1000,
                        "end_ms": 2200,
                        "duration_ms": 1200,
                    }
                ]
            },
        )
        write_json(project / "decisions" / "edit_plan.json", plan)
        return project, plan

    def test_review_pipeline_writes_new_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, plan = self._project(Path(temporary))
            renderer = FakeRenderer()

            result = ReviewRenderPipeline(
                renderer=renderer
            ).run(project, plan)

            self.assertTrue((project / result["output_path"]).exists())
            self.assertEqual(len(renderer.calls), 1)

            _, project_data = ProjectManager().load_project(project)
            self.assertEqual(
                project_data["output_path"],
                result["output_path"],
            )

    def test_export_pipeline_uses_selected_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self._project(Path(temporary))
            renderer = FakeRenderer()

            result = ExportPipeline(
                renderer=renderer
            ).run(project, "720p")

            self.assertTrue((project / result["export_path"]).exists())
            self.assertEqual(result["export_profile"], "720p")
            self.assertEqual(
                renderer.calls[0]["options"]["output_height"],
                720,
            )
            self.assertEqual(
                renderer.calls[0]["options"]["audio_bitrate"],
                "160k",
            )

    def test_original_export_reuses_existing_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, _ = self._project(Path(temporary))
            preview = project / "output" / "video_editado.mp4"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_bytes(b"preview-video")

            manager = ProjectManager()
            manager.update_processing(
                project,
                "rendered",
                output_path="output/video_editado.mp4",
            )

            class FakeTools:
                def probe(self, path, cancel=None):
                    return {"video": {"height": 1080}}

            renderer = FakeRenderer()
            result = ExportPipeline(
                tools=FakeTools(),
                renderer=renderer,
            ).run(project, "original")

            self.assertTrue((project / result["export_path"]).exists())
            self.assertEqual(
                (project / result["export_path"]).read_bytes(),
                b"preview-video",
            )
            self.assertEqual(result["export_mode"], "smart_copy")
            self.assertEqual(renderer.calls, [])


if __name__ == "__main__":
    unittest.main()
