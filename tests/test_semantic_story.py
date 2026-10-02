import unittest

from core.ending_director import EndingDirector
from core.reference_story_director import arrange_candidates_by_reference
from core.semantic_signals import build_semantic_director, repetition_penalty
from core.wedding_assembly import build_wedding_assembly_plan


def candidate(name, tags, closing=0.0, score=80, risk=0.0, embedding=None):
    return {"asset_id":name,"scene_id":0,"path":name+".mp4","filename":name+".mp4",
            "start_ms":0,"end_ms":12000,"duration_ms":12000,"score":score,
            "visual_semantics":{"tags":[{"name":tag,"score":value} for tag,value in tags.items()],
                                "quality":{"shake_score":risk},"roles":{"closing_score":closing},
                                "embedding":embedding or []}}


class SemanticStoryTests(unittest.TestCase):
    def test_bad_endings_are_blocked_even_with_higher_generic_or_closing_scores(self):
        good = candidate("couple",{"couple_portrait":0.8},closing=0.65,score=60)
        for tag in ("children","guests_reaction","officiant","party","decor_detail"):
            bad = candidate("bad",{tag:0.95},closing=0.99,score=100)
            self.assertEqual(EndingDirector().choose([bad,good])["candidate"]["asset_id"],"couple")
        shaky = candidate("shake",{"kiss":0.95},closing=0.99,score=100,risk=0.9)
        self.assertEqual(EndingDirector().choose([shaky,good])["candidate"]["asset_id"],"couple")

    def test_closing_score_overcomes_generic_quality_ranking(self):
        high_quality = candidate("technical",{"embrace":0.8},closing=0.35,score=99)
        emotional = candidate("emotional",{"kiss":0.8},closing=0.85,score=65)
        self.assertEqual(EndingDirector().choose([high_quality,emotional])["candidate"]["asset_id"],"emotional")

    def test_ring_symbol_and_material_shortage_are_explicit(self):
        symbol = candidate("ring",{"ring_detail":0.8},closing=0.7)
        bad = candidate("crowd",{"guests_reaction":0.9},score=100)
        self.assertFalse(EndingDirector().choose([bad,symbol])["fallback"])
        self.assertTrue(EndingDirector().choose([bad])["fallback"])

    def test_tag_and_embedding_repetition_reduce_score(self):
        previous = candidate("a",{"makeup":0.9},embedding=[1,0])
        repeat = candidate("b",{"makeup":0.8},embedding=[0.999,0.001])
        different = candidate("c",{"ring_detail":0.8},embedding=[0,1])
        self.assertGreater(repetition_penalty(repeat,[previous]),30)
        self.assertEqual(repetition_penalty(different,[previous]),0)

    def test_slots_choose_semantic_material_over_generic_score(self):
        items = [candidate("makeup",{"makeup":0.9},score=65),candidate("ring",{"ring_detail":0.8}),
                 candidate("entrance",{"bride_entrance":0.8}),candidate("vows",{"vows":0.9}),
                 candidate("portrait",{"couple_portrait":0.9},closing=0.8),candidate("children",{"children":0.95},score=100)]
        for slot,expected in (("preparation","makeup"),("details","ring"),("anticipation","entrance"),
                              ("emotional_peak","vows"),("couple_hero","portrait")):
            director={"phases":[{"key":slot,"desired_shots":1,"story_sections":[],"topic_repeat_limit":1}]}
            chosen=arrange_candidates_by_reference(items,[],director,1)
            self.assertEqual(chosen[0]["asset_id"],expected)

    def test_slot_selection_prefers_a_different_composition_after_repeat(self):
        items = [candidate("first", {"makeup":0.9}, score=95, embedding=[1,0]),
                 candidate("repeat", {"makeup":0.9}, score=94, embedding=[1,0]),
                 candidate("hair", {"hair":0.9}, score=72, embedding=[0,1])]
        director = {"phases":[{"key":"preparation","desired_shots":2,"topic_repeat_limit":2}]}
        chosen = arrange_candidates_by_reference(items,[],director,2)
        self.assertEqual([item["asset_id"] for item in chosen],["first","hair"])

    def test_ending_survives_duration_trim_with_and_without_reference(self):
        items=[candidate("prep",{"makeup":0.9}),candidate("crowd",{"children":0.9},score=100),
               candidate("couple",{"embrace":0.9},closing=0.85)]
        project={"style":"Highlight","deliverable":{"type":"trailer","target_seconds":18},"review_settings":{}}
        for director in (None,build_semantic_director(18000)):
            plan=build_wedding_assembly_plan(project,{"assets":[{"id":item["asset_id"]} for item in items]},
                                             {"best_take_candidates":items},reference_story_director=director)
            last=plan["clips"][-1]
            self.assertEqual(last["asset_id"],"couple")
            self.assertTrue(last["ending_director_selected"])
            self.assertGreaterEqual(last["duration_ms"],3000)
            self.assertLessEqual(plan["estimated_duration_ms"],18000)
            self.assertEqual(last["timeline_end_ms"],sum(x["duration_ms"] for x in plan["clips"]))
            self.assertLessEqual(last["end_ms"],last["source_end_ms"])
