from __future__ import annotations

from statistics import median

from core.best_shot_selector import candidate_selection_score
from core.wedding_semantics import STORY_SECTIONS, enrich_story_candidate


PHASE_DEFINITIONS = (
    {
        "key": "cold_open",
        "label": "Preview emocional",
        "sections": ("cerimonia", "votos_falas", "casal", "finale"),
        "audio_intent": "music_priority",
        "shot_limits_ms": (1800, 4500),
    },
    {
        "key": "preparation_a",
        "label": "Preparação I",
        "sections": ("making_of",),
        "audio_intent": "music_priority",
        "shot_limits_ms": (2800, 6000),
    },
    {
        "key": "details",
        "label": "Detalhes e ambientação",
        "sections": ("making_of", "recepcao"),
        "audio_intent": "music_priority",
        "shot_limits_ms": (2600, 5600),
    },
    {
        "key": "preparation_b",
        "label": "Preparação II",
        "sections": ("making_of",),
        "audio_intent": "music_priority",
        "shot_limits_ms": (2400, 5200),
    },
    {
        "key": "ceremony",
        "label": "Entrada e cerimônia",
        "sections": ("cerimonia",),
        "audio_intent": "music_priority",
        "shot_limits_ms": (1100, 3000),
    },
    {
        "key": "vows_couple",
        "label": "Votos e casal",
        "sections": ("votos_falas", "casal", "cerimonia"),
        "audio_intent": "dialogue_if_detected",
        "shot_limits_ms": (2300, 5200),
    },
    {
        "key": "finale",
        "label": "Fechamento",
        "sections": ("casal", "finale", "festa"),
        "audio_intent": "music_priority",
        "shot_limits_ms": (1600, 3400),
    },
)


UNCLASSIFIED_SOURCE_BANDS = {
    "cold_open": (0.55, 1.00),
    "preparation_a": (0.00, 0.28),
    "details": (0.20, 0.52),
    "preparation_b": (0.42, 0.70),
    "ceremony": (0.62, 0.88),
    "vows_couple": (0.78, 0.97),
    "finale": (0.90, 1.00),
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _scene_durations_in_range(reference_style, start_ratio, end_ratio):
    if not isinstance(reference_style, dict):
        return []
    try:
        duration_ms = int(reference_style.get("duration_ms", 0) or 0)
    except (TypeError, ValueError):
        return []
    if duration_ms <= 0:
        return []

    start_ms = int(duration_ms * float(start_ratio))
    end_ms = int(duration_ms * float(end_ratio))
    values = []
    for scene in reference_style.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        try:
            scene_start = int(scene.get("start_ms", 0) or 0)
            scene_end = int(scene.get("end_ms", scene_start) or scene_start)
        except (TypeError, ValueError):
            continue
        midpoint = int((scene_start + scene_end) / 2)
        if start_ms <= midpoint < end_ms and scene_end > scene_start:
            values.append(scene_end - scene_start)
    return values


def _energy_for_range(reference_music, start_ratio, end_ratio):
    if not isinstance(reference_music, dict):
        return 0.0
    sections = reference_music.get("energy_sections")
    if not isinstance(sections, list) or not sections:
        return 0.0
    try:
        duration_ms = int(reference_music.get("duration_ms", 0) or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    if duration_ms <= 0:
        return 0.0

    start_ms = int(duration_ms * start_ratio)
    end_ms = int(duration_ms * end_ratio)
    values = []
    for item in sections:
        if not isinstance(item, dict):
            continue
        try:
            item_start = int(item.get("start_ms", 0) or 0)
            item_end = int(item.get("end_ms", item_start) or item_start)
            energy = float(item.get("energy", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if min(end_ms, item_end) > max(start_ms, item_start):
            values.append(energy)
    return round(sum(values) / len(values), 4) if values else 0.0


def _detect_climax_ratio(reference_style, reference_music):
    """Find where the reference clearly starts accelerating.

    This does not claim to understand wedding events in the reference frames.
    It measures pacing/energy and feeds that structural evidence into a wedding
    narrative grammar.
    """
    overall_median = 3.2
    if isinstance(reference_style, dict):
        try:
            overall_median = float(reference_style.get("median_shot_seconds", 3.2) or 3.2)
        except (TypeError, ValueError):
            overall_median = 3.2

    pace_candidates = []
    windows = reference_style.get("pacing_windows", []) if isinstance(reference_style, dict) else []
    for item in windows or []:
        if not isinstance(item, dict):
            continue
        try:
            ratio = float(item.get("start_ratio", 0.0) or 0.0)
            shot = float(item.get("median_shot_seconds", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if 0.55 <= ratio <= 0.86 and shot > 0 and shot <= max(2.25, overall_median * 0.72):
            pace_candidates.append(ratio)

    energy_candidates = []
    if isinstance(reference_music, dict):
        try:
            duration_ms = int(reference_music.get("duration_ms", 0) or 0)
        except (TypeError, ValueError):
            duration_ms = 0
        if duration_ms > 0:
            for item in reference_music.get("transitions", []) or []:
                if not isinstance(item, dict) or item.get("direction") != "up":
                    continue
                try:
                    ratio = int(item.get("time_ms", 0) or 0) / duration_ms
                    strength = float(item.get("strength", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                if 0.55 <= ratio <= 0.86 and strength >= 0.22:
                    energy_candidates.append(ratio)

    candidates = pace_candidates[:1] + energy_candidates[:1]
    if not candidates:
        return 0.76
    return round(_clamp(sum(candidates) / len(candidates), 0.68, 0.82), 4)


def _phase_boundaries(climax_ratio):
    cold_end = 0.08
    pre_span = max(0.30, climax_ratio - cold_end)
    prep_a_end = cold_end + pre_span * 0.32
    details_end = cold_end + pre_span * 0.63
    ceremony_end = min(0.90, max(climax_ratio + 0.09, 0.86))
    vows_end = 0.97
    return (
        (0.00, cold_end),
        (cold_end, prep_a_end),
        (prep_a_end, details_end),
        (details_end, climax_ratio),
        (climax_ratio, ceremony_end),
        (ceremony_end, vows_end),
        (vows_end, 1.00),
    )


def build_reference_story_director(reference_style, reference_music, target_ms):
    target_ms = max(1000, int(target_ms))
    climax_ratio = _detect_climax_ratio(reference_style, reference_music)
    boundaries = _phase_boundaries(climax_ratio)
    phases = []

    for definition, (start_ratio, end_ratio) in zip(PHASE_DEFINITIONS, boundaries):
        values = _scene_durations_in_range(reference_style, start_ratio, end_ratio)
        low, high = definition["shot_limits_ms"]
        if values:
            target_shot_ms = int(round(median(values)))
        else:
            target_shot_ms = int((low + high) / 2)
        target_shot_ms = int(_clamp(target_shot_ms, low, high))
        phase_start_ms = int(round(target_ms * start_ratio))
        phase_end_ms = int(round(target_ms * end_ratio))
        phases.append(
            {
                **definition,
                "story_sections": list(definition["sections"]),
                "start_ratio": round(start_ratio, 4),
                "end_ratio": round(end_ratio, 4),
                "start_ms": phase_start_ms,
                "end_ms": phase_end_ms,
                "budget_ms": max(0, phase_end_ms - phase_start_ms),
                "target_shot_ms": target_shot_ms,
                "reference_energy": _energy_for_range(reference_music, start_ratio, end_ratio),
                "unclassified_source_band": list(
                    UNCLASSIFIED_SOURCE_BANDS.get(definition["key"], (0.0, 1.0))
                ),
            }
        )

    return {
        "schema_version": "0.1",
        "engine": "reference-story-director-v1",
        "target_duration_ms": target_ms,
        "climax_start_ratio": climax_ratio,
        "cold_open_enabled": True,
        "phase_count": len(phases),
        "phases": phases,
        "reference_semantic_claim": False,
        "fallback_ordering": "source_chronology",
    }


def _candidate_key(candidate):
    return (
        str(candidate.get("asset_id") or ""),
        int(candidate.get("scene_id", -1) or -1),
        int(candidate.get("start_ms", 0) or 0),
        int(candidate.get("end_ms", 0) or 0),
    )


def _source_order_map(assets):
    return {
        item.get("id"): index
        for index, item in enumerate(assets or [])
        if isinstance(item, dict) and item.get("id")
    }


def _source_order(candidate, asset_order):
    return (
        asset_order.get(candidate.get("asset_id"), 10**9),
        int(candidate.get("start_ms", 0) or 0),
    )


def _band_candidates(unclassified, asset_order, low_ratio, high_ratio):
    if not unclassified:
        return []
    ordered = sorted(unclassified, key=lambda item: _source_order(item, asset_order))
    total = len(ordered)
    start = min(total, max(0, int(total * low_ratio)))
    end = min(total, max(start + 1, int(round(total * high_ratio))))
    return ordered[start:end]


def _choose_diverse(pool, used, previous_asset):
    available = [item for item in pool if _candidate_key(item) not in used]
    if not available:
        return None
    alternatives = [item for item in available if item.get("asset_id") != previous_asset]
    source = alternatives or available
    return max(source, key=lambda item: candidate_selection_score(item))


def arrange_candidates_by_reference(candidates, assets, director, max_clips):
    """Order the new wedding according to the reference-shaped story map.

    Classified material follows wedding chapters. When classification is absent,
    the fallback is source chronology in phase-sized bands, not global quality
    sorting. That prevents visually good but unrelated moments from being
    scattered across the trailer.
    """
    enriched = [
        enrich_story_candidate(dict(item))
        for item in candidates or []
        if isinstance(item, dict)
    ]
    asset_order = _source_order_map(assets)
    unclassified = [
        item for item in enriched
        if item.get("semantic_story_section") not in STORY_SECTIONS
    ]
    used = set()
    selected = []
    previous_asset = None
    estimated_total = 0

    for phase in director.get("phases", []) or []:
        if len(selected) >= max_clips:
            break
        allowed = set(phase.get("story_sections") or [])
        target_shot_ms = max(500, int(phase.get("target_shot_ms", 2500) or 2500))
        budget_ms = max(0, int(phase.get("budget_ms", 0) or 0))
        phase_total = 0

        preferred = [
            item for item in enriched
            if item.get("semantic_story_section") in allowed
        ]
        preferred.sort(
            key=lambda item: (
                candidate_selection_score(item),
                -_source_order(item, asset_order)[0],
            ),
            reverse=True,
        )

        band = phase.get("unclassified_source_band") or [0.0, 1.0]
        try:
            low_ratio = float(band[0])
            high_ratio = float(band[1])
        except (TypeError, ValueError, IndexError):
            low_ratio, high_ratio = 0.0, 1.0
        fallback = _band_candidates(
            unclassified,
            asset_order,
            _clamp(low_ratio, 0.0, 1.0),
            _clamp(high_ratio, 0.0, 1.0),
        )

        # Cold open is a highlight reel; later phases preserve more chronology.
        if phase.get("key") == "cold_open":
            fallback.sort(key=lambda item: candidate_selection_score(item), reverse=True)
        else:
            fallback.sort(key=lambda item: _source_order(item, asset_order))

        while phase_total < budget_ms and len(selected) < max_clips:
            candidate = _choose_diverse(preferred, used, previous_asset)
            if candidate is None:
                candidate = next(
                    (item for item in fallback if _candidate_key(item) not in used),
                    None,
                )
            if candidate is None:
                break

            copy = dict(candidate)
            copy["story_section"] = (
                copy.get("semantic_story_section")
                if copy.get("semantic_story_section") in STORY_SECTIONS
                else "nao_classificado"
            )
            copy["director_phase"] = phase.get("key")
            copy["director_phase_label"] = phase.get("label")
            copy["director_target_duration_ms"] = target_shot_ms
            copy["director_audio_intent"] = phase.get("audio_intent")
            copy["director_reference_energy"] = phase.get("reference_energy", 0.0)
            selected.append(copy)
            used.add(_candidate_key(candidate))
            previous_asset = candidate.get("asset_id")
            phase_total += min(
                max(500, int(candidate.get("duration_ms", 0) or 0)),
                target_shot_ms,
            )
            estimated_total += min(
                max(500, int(candidate.get("duration_ms", 0) or 0)),
                target_shot_ms,
            )

    # Fill shortages chronologically. This is deliberately not global score order.
    if len(selected) < max_clips and estimated_total < int(director.get("target_duration_ms", 0) or 0):
        remainder = sorted(enriched, key=lambda item: _source_order(item, asset_order))
        for candidate in remainder:
            if len(selected) >= max_clips:
                break
            key = _candidate_key(candidate)
            if key in used:
                continue
            copy = dict(candidate)
            copy["story_section"] = (
                copy.get("semantic_story_section")
                if copy.get("semantic_story_section") in STORY_SECTIONS
                else "nao_classificado"
            )
            copy["director_phase"] = "chronology_fill"
            copy["director_phase_label"] = "Complemento cronológico"
            copy["director_target_duration_ms"] = 2800
            copy["director_audio_intent"] = "music_priority"
            copy["director_reference_energy"] = 0.0
            selected.append(copy)
            used.add(key)
            estimated_total += min(
                max(500, int(candidate.get("duration_ms", 0) or 0)),
                2800,
            )
            if estimated_total >= int(director.get("target_duration_ms", 0) or 0):
                break

    return selected
