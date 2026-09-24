import shutil
import tempfile
import unittest
from pathlib import Path

from editor.edit_plan import build_edit_plan, validate_edit_plan
from media.ffmpeg_tools import FFmpegTools
from media.process import run_media
from renderer.ffmpeg_renderer import FFmpegRenderer, build_filter_graph


class EditPlanTests(unittest.TestCase):
    def test_dynamic_is_more_aggressive_than_clean(self):
        silences = {
            "silences": [
                {"start_ms": 1000, "end_ms": 2100, "duration_ms": 1100},
                {"start_ms": 3000, "end_ms": 3700, "duration_ms": 700},
                {"start_ms": 5000, "end_ms": 7000, "duration_ms": 2000},
            ]
        }

        dynamic = build_edit_plan(
            8000,
            "YouTube",
            "Dinâmico",
            silences,
        )
        clean = build_edit_plan(
            8000,
            "YouTube",
            "Clean",
            silences,
        )

        self.assertGreater(
            dynamic["stats"]["cuts"],
            clean["stats"]["cuts"],
        )
        self.assertGreater(
            dynamic["stats"]["removed_duration_ms"],
            clean["stats"]["removed_duration_ms"],
        )

    def test_plan_is_contiguous_and_preserves_edges(self):
        plan = build_edit_plan(
            5000,
            "YouTube",
            "Dinâmico",
            {
                "silences": [
                    {"start_ms": 0, "end_ms": 1200, "duration_ms": 1200},
                    {"start_ms": 3800, "end_ms": 5000, "duration_ms": 1200},
                ]
            },
        )

        validate_edit_plan(plan)
        self.assertEqual(plan["segments"][0]["start_ms"], 0)
        self.assertEqual(plan["segments"][-1]["end_ms"], 5000)

        removals = [
            segment
            for segment in plan["segments"]
            if segment["action"] == "remove"
        ]
        self.assertTrue(all(segment["start_ms"] >= 250 for segment in removals))
        self.assertTrue(all(segment["end_ms"] <= 4750 for segment in removals))

    def test_invalid_gap_is_rejected(self):
        plan = build_edit_plan(
            3000,
            "YouTube",
            "Clean",
            {"silences": []},
        )
        plan["segments"] = [
            {
                "start_ms": 0,
                "end_ms": 1000,
                "action": "keep",
                "reason": "content",
            },
            {
                "start_ms": 1100,
                "end_ms": 3000,
                "action": "keep",
                "reason": "content",
            },
        ]

        with self.assertRaises(ValueError):
            validate_edit_plan(plan)

    def test_filter_graph_matches_keep_segments(self):
        plan = build_edit_plan(
            4000,
            "YouTube",
            "Dinâmico",
            {
                "silences": [
                    {"start_ms": 1000, "end_ms": 2000, "duration_ms": 1000}
                ]
            },
        )

        graph = build_filter_graph(plan)
        keep_count = sum(
            1
            for segment in plan["segments"]
            if segment["action"] == "keep"
        )

        self.assertIn(
            f"concat=n={keep_count}:v=1:a=1[outv][outa]",
            graph,
        )
        self.assertIn("[0:v:0]trim=", graph)
        self.assertIn("[0:a:0]atrim=", graph)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg/FFprobe não estão no PATH.",
)
class AutoRenderIntegrationTests(unittest.TestCase):
    def test_real_renderer_creates_shorter_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            destination = root / "edited.mp4"

            ffmpeg = shutil.which("ffmpeg")

            run_media(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-nostdin",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x180:rate=25:duration=4",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=1000:sample_rate=48000:duration=4",
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-y",
                    str(source),
                ]
            )

            plan = build_edit_plan(
                4000,
                "YouTube",
                "Dinâmico",
                {
                    "silences": [
                        {
                            "start_ms": 1000,
                            "end_ms": 2000,
                            "duration_ms": 1000,
                        }
                    ]
                },
            )

            tools = FFmpegTools()
            renderer = FFmpegRenderer(tools)
            renderer.render(source, destination, plan)

            self.assertTrue(destination.exists())
            metadata = tools.probe(destination)
            duration = metadata["container"]["duration_seconds"]

            self.assertIsNotNone(duration)
            self.assertLess(duration, 3.8)
            self.assertGreater(duration, 2.8)
            self.assertTrue(metadata["audio"]["present"])


if __name__ == "__main__":
    unittest.main()
