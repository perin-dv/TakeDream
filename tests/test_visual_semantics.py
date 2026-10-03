import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.processing import ProcessingCancelled
from core.project_manager import ProjectManager
from core.storage import read_json
from core.visual_semantics import (
    VISUAL_SEMANTICS_PATH,
    VisualSemanticsPipeline,
    _build_record,
)


class StubModel:
    identity = {"name": "test-model", "device": "cpu", "revision": "1"}

    def __init__(self):
        self.calls = 0

    def analyze(self, frames, **kwargs):
        self.calls += 1
        return {
            "scores": {"couple_portrait": 0.85, "kiss": 0.65},
            "peak_scores": {"couple_portrait": 0.90, "kiss": 0.70},
            "embedding": [1.0, 0.0],
        }


class VisualSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / "source.mp4"
        self.source.write_bytes(b"model layer is stubbed in unit tests")
        self.manager = ProjectManager(root / "projects")
        self.project = self.manager.create_project(
            "Vision",
            self.source,
            "Casamento",
            "Highlight",
        )
        self.candidates = [
            dict(
                asset_id="a",
                scene_id=index,
                path=str(self.source),
                start_ms=index * 4000,
                end_ms=(index + 1) * 4000,
                duration_ms=4000,
                score=80,
            )
            for index in range(2)
        ]
        self.model = StubModel()
        self.extractions = 0

        def extract(item, directory, ffmpeg, **kwargs):
            self.extractions += 1
            return [Path(directory) / "frame.jpg"], [item["start_ms"] + 2000]

        self.pipeline = VisualSemanticsPipeline(
            self.manager,
            model=self.model,
            frame_extractor=extract,
        )

    def test_persistence_reopening_reuses_cache_without_loading_or_extracting(self):
        self.pipeline.run(self.project, self.candidates)
        reopened = VisualSemanticsPipeline(
            self.manager,
            model=self.model,
            frame_extractor=lambda *args, **kwargs: self.fail("cache extracted frames"),
        )
        result = reopened.run(self.project, self.candidates)
        data = read_json(self.project / VISUAL_SEMANTICS_PATH)
        self.assertEqual(result["analysis"]["reused_from_cache"], 2)
        self.assertEqual(self.model.calls, 2)
        self.assertTrue(data["complete"])
        self.assertEqual(len(data["shots"]), 2)
        self.assertGreater(data["shots"][0]["roles"]["closing_score"], 0.6)
        self.assertTrue(
            any(
                tag["name"] == "repeated_visual" and tag["score"] > 0.9
                for tag in data["shots"][1]["tags"]
            )
        )

    def test_peak_accidental_floor_becomes_composition_risk(self):
        item = {
            "asset_id": "a",
            "scene_id": 1,
            "path": str(self.source),
            "start_ms": 1000,
            "end_ms": 5000,
            "score": 90,
        }
        result = {
            "scores": {"couple_portrait": 0.25, "accidental_floor": 0.12},
            "peak_scores": {"couple_portrait": 0.28, "accidental_floor": 0.82},
            "embedding": [1.0, 0.0],
            "background_score": 0.10,
        }
        record = _build_record(item, result, "cache")
        self.assertGreaterEqual(record["quality"]["composition_risk_score"], 0.82)
        self.assertGreaterEqual(record["quality"]["accidental_floor_score"], 0.82)

    def test_source_model_and_shot_changes_invalidate_cache(self):
        self.pipeline.run(self.project, self.candidates)
        self.source.write_bytes(b"changed source file")
        self.pipeline.run(self.project, self.candidates)
        self.assertEqual(self.model.calls, 4)
        self.model.identity = {**self.model.identity, "revision": "2"}
        self.pipeline.run(self.project, self.candidates)
        self.assertEqual(self.model.calls, 6)
        self.candidates[0]["end_ms"] -= 100
        self.pipeline.run(self.project, self.candidates)
        self.assertEqual(self.model.calls, 7)

    def test_analysis_never_regresses_exported_status(self):
        self.manager.update_processing(self.project, "exported")
        self.pipeline.run(self.project, self.candidates)
        self.assertEqual(self.manager.load_project(self.project)[1]["status"], "exported")

    def test_cancelled_analysis_does_not_report_complete_or_change_status(self):
        self.manager.update_processing(self.project, "rendered")
        cancel = SimpleNamespace(is_set=lambda: self.model.calls >= 1)
        with self.assertRaises(ProcessingCancelled):
            self.pipeline.run(self.project, self.candidates, cancel=cancel)
        self.assertEqual(self.manager.load_project(self.project)[1]["status"], "rendered")

    def test_corrupt_cache_is_recomputed(self):
        path = self.project / VISUAL_SEMANTICS_PATH
        path.parent.mkdir(exist_ok=True)
        path.write_text("{corrupt", encoding="utf-8")
        self.pipeline.run(self.project, self.candidates)
        self.assertTrue(read_json(path)["complete"])


if __name__ == "__main__":
    unittest.main()
