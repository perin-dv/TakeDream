import unittest

from core.wedding_semantics import (
    analyze_story_semantics,
    enrich_story_candidate,
)
from core.wedding_story import classify_story_section


class WeddingSemanticsTests(unittest.TestCase):
    def test_path_evidence_classifies_ceremony(self):
        result = analyze_story_semantics(
            {
                "path": r"D:\CASAMENTO\CERIMONIA\entrada_noiva_C0058.MP4",
                "filename": "C0058.MP4",
                "category_hint": "nao_classificado",
            }
        )
        self.assertEqual(result["section"], "cerimonia")
        self.assertGreaterEqual(result["confidence"], 0.7)
        self.assertTrue(result["evidence"])

    def test_transcript_evidence_classifies_vows_without_filename_help(self):
        result = analyze_story_semantics(
            {
                "filename": "C0058.MP4",
                "category_hint": "nao_classificado",
                "speech_text": "Eu prometo te amar todos os dias da minha vida.",
                "audio_present": True,
            }
        )
        self.assertEqual(result["section"], "votos_falas")
        self.assertGreaterEqual(result["confidence"], 0.85)
        self.assertTrue(any("fala/transcrição" in item for item in result["evidence"]))

    def test_audio_alone_does_not_fake_semantic_classification(self):
        result = analyze_story_semantics(
            {
                "filename": "C0058.MP4",
                "category_hint": "nao_classificado",
                "audio_present": True,
                "duration_ms": 15000,
            }
        )
        self.assertEqual(result["section"], "nao_classificado")
        self.assertEqual(result["confidence"], 0.0)

    def test_real_future_vision_tags_are_supported_without_fake_detector(self):
        result = analyze_story_semantics(
            {
                "filename": "C0059.MP4",
                "vision_tags": ["dance floor", "party lights", "dancing crowd"],
            }
        )
        self.assertEqual(result["section"], "festa")
        self.assertGreater(result["confidence"], 0.8)

    def test_enrichment_preserves_candidate_and_adds_audit_fields(self):
        original = {
            "asset_id": "asset-1",
            "filename": "votos_noiva.mp4",
            "score": 91,
        }
        enriched = enrich_story_candidate(original)
        self.assertEqual(enriched["asset_id"], "asset-1")
        self.assertEqual(enriched["semantic_story_section"], "votos_falas")
        self.assertIn("semantic_confidence", enriched)
        self.assertIn("semantic_evidence", enriched)
        self.assertEqual(classify_story_section(original), "votos_falas")


if __name__ == "__main__":
    unittest.main()
