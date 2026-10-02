"""Reserve a stable, emotionally meaningful last shot before duration trimming."""
from core.best_shot_selector import candidate_selection_score
from core.semantic_signals import BAD_ENDING, COUPLE, quality_risk, scores, strongest


class EndingDirector:
    def choose(self, candidates):
        analyzed = [item for item in candidates if item.get("visual_semantics")]
        if not analyzed:
            return {"candidate":None,"reason":"semantic_analysis_unavailable","fallback":True}
        ranked = []
        for item in analyzed:
            values = scores(item)
            risk = quality_risk(item)
            couple = strongest(values, COUPLE)
            symbol = strongest(values, ("holding_hands", "ring_detail", "ring_exchange", "ceremony_exit", "bouquet_detail"))
            bad = strongest(values, BAD_ENDING)
            available = int(item.get("motion_safe_end_ms") or item["end_ms"]) - int(item.get("motion_safe_start_ms") or item["start_ms"])
            if available < 500:
                continue
            positive = max(couple,symbol)
            safe = risk < 0.55 and positive >= 0.30 and bad < max(0.45, positive * 0.85)
            closing = float((item["visual_semantics"].get("roles") or {}).get("closing_score",0))
            priority = 1.0 if couple >= 0.30 else 0.6 if symbol >= 0.30 else 0.0
            score = closing * 100 + priority * 18 + candidate_selection_score(item) * 0.12 - bad*55 - risk*80
            ranked.append((safe,score,item,available))
        if not ranked:
            return {"candidate":None,"reason":"no_usable_shot","fallback":True}
        safe_pool = [row for row in ranked if row[0]]
        chosen = max(safe_pool or ranked,key=lambda row:row[1])
        copy = dict(chosen[2])
        copy.update(story_section="finale",director_phase="finale",director_phase_label="Encerramento emocional",
                    semantic_slot="closing",ending_director_selected=True)
        return {"candidate":copy,"reason":"stable_couple_or_symbol" if safe_pool else "extreme_material_shortage",
                "fallback":not bool(safe_pool),"score":round(chosen[1],3),
                "hold_ms":min(6000,chosen[3]),"safe_candidate_count":len(safe_pool)}
