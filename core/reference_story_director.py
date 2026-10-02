from __future__ import annotations

import math
import re
import unicodedata
from statistics import median

from core.best_shot_selector import candidate_selection_score
from core.wedding_semantics import STORY_SECTIONS, enrich_story_candidate


PHASE_DEFINITIONS = (
    {
        "key": "cold_open",
        "label": "Preview emocional",
        "sections": ("cerimonia", "votos_falas", "casal", "finale", "festa"),
        "audio_intent": "music_priority",
        "shot_limits_ms": (2200, 4800),
        "shot_count_limits": (4, 6),
        "topic_repeat_limit": 1,
    },
    {
        "key": "preparation_a",
        "label": "Preparação I",
        "sections": ("making_of",),
        "audio_intent": "music_priority",
        "shot_limits_ms": (3200, 6200),
        "shot_count_limits": (4, 24),
        "topic_repeat_limit": 2,
    },
    {
        "key": "details",
        "label": "Detalhes e ambientação",
        "sections": ("making_of", "recepcao"),
        "audio_intent": "music_priority",
        "shot_limits_ms": (3000, 5800),
        "shot_count_limits": (3, 20),
        "topic_repeat_limit": 2,
    },
    {
        "key": "preparation_b",
        "label": "Preparação II",
        "sections": ("making_of",),
        "audio_intent": "music_priority",
        "shot_limits_ms": (2800, 5400),
        "shot_count_limits": (3, 22),
        "topic_repeat_limit": 2,
    },
    {
        "key": "ceremony",
        "label": "Entrada e cerimônia",
        "sections": ("cerimonia",),
        "audio_intent": "music_priority",
        "shot_limits_ms": (1500, 3400),
        "shot_count_limits": (4, 26),
        "topic_repeat_limit": 2,
    },
    {
        "key": "vows_couple",
        "label": "Votos e casal",
        "sections": ("votos_falas", "casal", "cerimonia"),
        "audio_intent": "dialogue_if_detected",
        "shot_limits_ms": (2600, 5600),
        "shot_count_limits": (3, 16),
        "topic_repeat_limit": 2,
    },
    {
        "key": "finale",
        "label": "Fechamento",
        "sections": ("casal", "finale", "festa"),
        "audio_intent": "music_priority",
        "shot_limits_ms": (2200, 4200),
        "shot_count_limits": (2, 5),
        "topic_repeat_limit": 1,
    },
)


UNCLASSIFIED_SOURCE_BANDS = {
    "cold_open": (0.58, 1.00),
    "preparation_a": (0.00, 0.30),
    "details": (0.18, 0.50),
    "preparation_b": (0.38, 0.68),
    "ceremony": (0.60, 0.88),
    "vows_couple": (0.76, 0.97),
    "finale": (0.90, 1.00),
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _plain(value):
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


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
        if 0.55 <= ratio <= 0.86 and shot > 0 and shot <= max(2.35, overall_median * 0.74):
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
    """Build story slots from reference pacing without copying its duration.

    V2 treats the reference as an editing teacher: it learns phase proportions,
    shot cadence and climax position. Exact cut lengths are intentionally left
    for reference_mapping, where the *new* soundtrack can snap cuts to its own
    strong edit points.
    """
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
        budget_ms = max(0, phase_end_ms - phase_start_ms)
        minimum_shots, maximum_shots = definition["shot_count_limits"]
        desired_shots = int(math.ceil(budget_ms / max(500, target_shot_ms) * 1.16))
        desired_shots = int(_clamp(desired_shots, minimum_shots, maximum_shots))

        phases.append(
            {
                **definition,
                "story_sections": list(definition["sections"]),
                "start_ratio": round(start_ratio, 4),
                "end_ratio": round(end_ratio, 4),
                "start_ms": phase_start_ms,
                "end_ms": phase_end_ms,
                "budget_ms": budget_ms,
                "target_shot_ms": target_shot_ms,
                "desired_shots": desired_shots,
                "reference_energy": _energy_for_range(reference_music, start_ratio, end_ratio),
                "unclassified_source_band": list(
                    UNCLASSIFIED_SOURCE_BANDS.get(definition["key"], (0.0, 1.0))
                ),
            }
        )

    return {
        "schema_version": "0.2",
        "engine": "reference-story-director-v2",
        "target_duration_ms": target_ms,
        "climax_start_ratio": climax_ratio,
        "cold_open_enabled": True,
        "phase_count": len(phases),
        "phases": phases,
        "reference_semantic_claim": False,
        "fallback_ordering": "source_chronology",
        "exact_cut_owner": "new_music_reference_mapping",
        "anti_repetition": "topic-and-source-cluster-v2",
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


def _band_candidates(candidates, asset_order, low_ratio, high_ratio):
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: _source_order(item, asset_order))
    total = len(ordered)
    start = min(total, max(0, int(total * low_ratio)))
    end = min(total, max(start + 1, int(round(total * high_ratio))))
    return ordered[start:end]


def _flatten_tags(candidate):
    values = []
    for key in (
        "event_label",
        "moment_label",
        "vision_tags",
        "visual_tags",
        "detected_tags",
        "semantic_tags",
    ):
        value = candidate.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value)
        elif isinstance(value, dict):
            values.extend(str(item) for item in value.values())
    return [_plain(item) for item in values if _plain(item)]


def _topic_key(candidate, asset_order):
    tags = _flatten_tags(candidate)
    if tags:
        return "tag:" + "|".join(sorted(set(tags))[:3])

    section = candidate.get("semantic_story_section")
    category = _plain(candidate.get("category_hint"))
    order = asset_order.get(candidate.get("asset_id"), 10**9)
    cluster = order // 3 if order < 10**9 else 10**9

    if section in STORY_SECTIONS and category and category != "nao classificado":
        return f"{section}:{category}:cluster-{cluster}"
    if section in STORY_SECTIONS:
        return f"{section}:cluster-{cluster}"
    return f"source-cluster:{cluster}"


def _pick_candidate(
    pool,
    *,
    used,
    previous_asset,
    asset_order,
    phase_asset_usage,
    phase_topic_usage,
    global_topic_usage,
    topic_repeat_limit,
):
    available = [item for item in pool if _candidate_key(item) not in used]
    if not available:
        return None

    ranked = []
    for item in available:
        topic = _topic_key(item, asset_order)
        asset_id = item.get("asset_id")
        score = candidate_selection_score(item)
        score -= phase_asset_usage.get(asset_id, 0) * 14.0
        score -= phase_topic_usage.get(topic, 0) * 18.0
        score -= global_topic_usage.get(topic, 0) * 5.0
        if asset_id == previous_asset:
            score -= 22.0
        if phase_topic_usage.get(topic, 0) >= topic_repeat_limit:
            score -= 36.0
        ranked.append((score, item, topic))

    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1] if ranked else None


def _phase_pool(enriched, phase, asset_order):
    allowed = set(phase.get("story_sections") or [])
    preferred = [
        item for item in enriched
        if item.get("semantic_story_section") in allowed
    ]

    band = phase.get("unclassified_source_band") or [0.0, 1.0]
    try:
        low_ratio = _clamp(float(band[0]), 0.0, 1.0)
        high_ratio = _clamp(float(band[1]), 0.0, 1.0)
    except (TypeError, ValueError, IndexError):
        low_ratio, high_ratio = 0.0, 1.0

    band_all = _band_candidates(enriched, asset_order, low_ratio, high_ratio)
    soft_fallback = []
    for item in band_all:
        section = item.get("semantic_story_section")
        confidence = float(item.get("semantic_confidence", 0.0) or 0.0)
        if section in allowed or section not in STORY_SECTIONS or confidence < 0.82:
            soft_fallback.append(item)

    if phase.get("key") == "cold_open":
        preferred = sorted(preferred, key=candidate_selection_score, reverse=True)
        soft_fallback = sorted(soft_fallback, key=candidate_selection_score, reverse=True)
    else:
        preferred = sorted(preferred, key=lambda item: _source_order(item, asset_order))
        soft_fallback = sorted(soft_fallback, key=lambda item: _source_order(item, asset_order))

    return preferred + [item for item in soft_fallback if item not in preferred] + [
        item for item in band_all if item not in preferred and item not in soft_fallback
    ]


def _decorate_candidate(candidate, phase, asset_order):
    copy = dict(candidate)
    copy["story_section"] = (
        copy.get("semantic_story_section")
        if copy.get("semantic_story_section") in STORY_SECTIONS
        else "nao_classificado"
    )
    copy["director_phase"] = phase.get("key")
    copy["director_phase_label"] = phase.get("label")
    # Exact duration is intentionally delegated to reference_mapping so the new
    # soundtrack, not the reference file duration, owns the final cut timing.
    copy["director_target_duration_ms"] = None
    copy["director_reference_target_duration_ms"] = phase.get("target_shot_ms")
    copy["director_audio_intent"] = phase.get("audio_intent")
    copy["director_reference_energy"] = phase.get("reference_energy", 0.0)
    copy["director_topic_key"] = _topic_key(copy, asset_order)
    return copy


def arrange_candidates_by_reference(candidates, assets, director, max_clips):
    """Fill narrative slots with anti-repetition and chronology-aware fallback."""
    enriched = [
        enrich_story_candidate(dict(item))
        for item in candidates or []
        if isinstance(item, dict)
    ]
    asset_order = _source_order_map(assets)
    used = set()
    global_topic_usage = {}
    phase_buckets = []
    previous_asset = None

    for phase in director.get("phases", []) or []:
        if sum(len(items) for items in phase_buckets) >= max_clips:
            break

        pool = _phase_pool(enriched, phase, asset_order)
        desired_shots = max(1, int(phase.get("desired_shots", 1) or 1))
        topic_repeat_limit = max(1, int(phase.get("topic_repeat_limit", 2) or 2))
        phase_asset_usage = {}
        phase_topic_usage = {}
        bucket = []

        while len(bucket) < desired_shots and len(used) < max_clips:
            candidate = _pick_candidate(
                pool,
                used=used,
                previous_asset=previous_asset,
                asset_order=asset_order,
                phase_asset_usage=phase_asset_usage,
                phase_topic_usage=phase_topic_usage,
                global_topic_usage=global_topic_usage,
                topic_repeat_limit=topic_repeat_limit,
            )
            if candidate is None:
                break

            decorated = _decorate_candidate(candidate, phase, asset_order)
            key = _candidate_key(candidate)
            topic = decorated["director_topic_key"]
            asset_id = candidate.get("asset_id")
            bucket.append(decorated)
            used.add(key)
            phase_asset_usage[asset_id] = phase_asset_usage.get(asset_id, 0) + 1
            phase_topic_usage[topic] = phase_topic_usage.get(topic, 0) + 1
            global_topic_usage[topic] = global_topic_usage.get(topic, 0) + 1
            previous_asset = asset_id

        phase_buckets.append(bucket)

    # If a phase could not fill its slots, distribute remaining material inside
    # the existing phases instead of appending one long chronology tail.
    remaining_capacity = max_clips - sum(len(items) for items in phase_buckets)
    if remaining_capacity > 0:
        progress = True
        while progress and remaining_capacity > 0:
            progress = False
            for phase_index, phase in enumerate(director.get("phases", []) or []):
                if remaining_capacity <= 0:
                    break
                bucket = phase_buckets[phase_index] if phase_index < len(phase_buckets) else []
                desired = max(1, int(phase.get("desired_shots", 1) or 1))
                if len(bucket) >= desired + 2:
                    continue
                pool = _phase_pool(enriched, phase, asset_order)
                phase_asset_usage = {}
                phase_topic_usage = {}
                for item in bucket:
                    asset_id = item.get("asset_id")
                    topic = item.get("director_topic_key") or _topic_key(item, asset_order)
                    phase_asset_usage[asset_id] = phase_asset_usage.get(asset_id, 0) + 1
                    phase_topic_usage[topic] = phase_topic_usage.get(topic, 0) + 1
                candidate = _pick_candidate(
                    pool,
                    used=used,
                    previous_asset=previous_asset,
                    asset_order=asset_order,
                    phase_asset_usage=phase_asset_usage,
                    phase_topic_usage=phase_topic_usage,
                    global_topic_usage=global_topic_usage,
                    topic_repeat_limit=max(1, int(phase.get("topic_repeat_limit", 2) or 2)),
                )
                if candidate is None:
                    continue
                decorated = _decorate_candidate(candidate, phase, asset_order)
                key = _candidate_key(candidate)
                topic = decorated["director_topic_key"]
                bucket.append(decorated)
                used.add(key)
                global_topic_usage[topic] = global_topic_usage.get(topic, 0) + 1
                previous_asset = candidate.get("asset_id")
                remaining_capacity -= 1
                progress = True

    selected = []
    for bucket in phase_buckets:
        selected.extend(bucket)
        if len(selected) >= max_clips:
            break
    return selected[:max_clips]
