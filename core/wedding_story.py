from __future__ import annotations

from core.best_shot_selector import (
    asset_usage,
    per_asset_limit,
    rank_wedding_candidates,
    source_too_close,
)
from core.wedding_semantics import (
    analyze_story_semantics,
    enrich_story_candidate,
)


STORY_ORDER = (
    "making_of",
    "cerimonia",
    "votos_falas",
    "casal",
    "recepcao",
    "festa",
    "finale",
)

STORY_LABELS = {
    "making_of": "Making of",
    "cerimonia": "Cerimônia",
    "votos_falas": "Votos e falas",
    "casal": "Casal",
    "recepcao": "Recepção",
    "festa": "Festa",
    "finale": "Final",
    "nao_classificado": "Não classificado",
}


def classify_story_section(candidate):
    return analyze_story_semantics(candidate).get(
        "section",
        "nao_classificado",
    )


def _candidate_key(candidate):
    return (
        str(candidate.get("asset_id", "")),
        int(candidate.get("scene_id", -1) or -1),
        int(candidate.get("start_ms", 0) or 0),
        int(candidate.get("end_ms", 0) or 0),
    )


def _duration_ms(candidate, fallback_ms):
    try:
        duration = int(candidate.get("duration_ms", 0) or 0)
    except (TypeError, ValueError):
        duration = 0
    return max(500, min(duration if duration > 0 else fallback_ms, fallback_ms))


def _section_budgets(deliverable, target_ms):
    story_budget = deliverable.get("story_budget") if isinstance(deliverable, dict) else None
    sections = story_budget.get("sections") if isinstance(story_budget, dict) else None
    if not isinstance(sections, dict):
        weights = {
            "making_of": 0.14,
            "cerimonia": 0.24,
            "votos_falas": 0.18,
            "casal": 0.17,
            "recepcao": 0.11,
            "festa": 0.12,
            "finale": 0.04,
        }
        return {
            name: int(round(target_ms * weight))
            for name, weight in weights.items()
        }

    budgets = {}
    for name in STORY_ORDER:
        try:
            seconds = int(sections.get(name, 0) or 0)
        except (TypeError, ValueError):
            seconds = 0
        budgets[name] = max(0, seconds * 1000)
    return budgets


def build_story_candidate_plan(
    candidates,
    assets,
    deliverable,
    *,
    target_ms,
    base_clip_ms,
    max_clips,
):
    """Seleciona, diversifica e ordena takes por capítulos de casamento."""
    candidates = [
        enrich_story_candidate(dict(item))
        for item in candidates
        if isinstance(item, dict)
    ]
    assets = [item for item in (assets or []) if isinstance(item, dict)]
    target_ms = max(1000, int(target_ms))
    base_clip_ms = max(500, int(base_clip_ms))
    max_clips = max(1, int(max_clips))

    deliverable_type = (
        deliverable.get("type", "trailer")
        if isinstance(deliverable, dict)
        else "trailer"
    )
    preferred_asset_limit = per_asset_limit(deliverable_type)

    grouped = {name: [] for name in STORY_ORDER}
    unclassified = []
    for candidate in candidates:
        section = candidate.get("semantic_story_section") or "nao_classificado"
        candidate["story_section"] = section
        if section in grouped:
            grouped[section].append(candidate)
        else:
            unclassified.append(candidate)

    grouped = {
        name: rank_wedding_candidates(items)
        for name, items in grouped.items()
    }
    unclassified = rank_wedding_candidates(unclassified)
    ranked_all = rank_wedding_candidates(candidates)
    budgets = _section_budgets(deliverable, target_ms)

    selected = []
    selected_keys = set()
    estimated_total = 0
    selection_counter = 0
    section_stats = {
        name: {
            "key": name,
            "label": STORY_LABELS[name],
            "budget_ms": budgets.get(name, 0),
            "estimated_ms": 0,
            "candidate_count": len(grouped[name]),
            "selected_count": 0,
        }
        for name in STORY_ORDER
    }

    def can_use(candidate, *, strict=True):
        key = _candidate_key(candidate)
        if key in selected_keys:
            return False
        if source_too_close(
            candidate,
            selected,
            minimum_gap_ms=1200 if strict else 350,
        ):
            return False
        if strict:
            counts = asset_usage(selected)
            asset_id = candidate.get("asset_id")
            if asset_id and counts.get(asset_id, 0) >= preferred_asset_limit:
                return False
        return True

    def append_candidate(candidate, section=None):
        nonlocal estimated_total, selection_counter
        copy = dict(candidate)
        copy["story_section"] = (
            section
            or copy.get("story_section")
            or copy.get("semantic_story_section")
            or "nao_classificado"
        )
        # Guarda a ordem em que o Best Shot Selector escolheu o take. Essa
        # sequência já intercala câmeras/mídias e não deve ser destruída por
        # uma ordenação posterior por asset_id.
        copy["_selection_order"] = selection_counter
        selection_counter += 1
        selected.append(copy)
        selected_keys.add(_candidate_key(copy))
        estimate = _duration_ms(copy, base_clip_ms)
        estimated_total += estimate
        story_section = copy.get("story_section")
        if story_section in section_stats:
            section_stats[story_section]["estimated_ms"] += estimate
            section_stats[story_section]["selected_count"] += 1
        return estimate

    for section in STORY_ORDER:
        quota = budgets.get(section, 0)
        if quota <= 0 or not grouped[section]:
            continue

        used_assets = set()
        pool = grouped[section]

        for diversity_pass in (True, False):
            for candidate in pool:
                if len(selected) >= max_clips:
                    break
                asset_id = candidate.get("asset_id")
                if diversity_pass and asset_id in used_assets:
                    continue
                if not can_use(candidate, strict=True):
                    continue
                if not diversity_pass and section_stats[section]["estimated_ms"] >= quota:
                    break

                append_candidate(candidate, section)
                used_assets.add(asset_id)
                if section_stats[section]["estimated_ms"] >= quota:
                    break

            if section_stats[section]["estimated_ms"] >= quota or len(selected) >= max_clips:
                break

    fallback_pool = unclassified + ranked_all
    for candidate in fallback_pool:
        if len(selected) >= max_clips or estimated_total >= target_ms:
            break
        if not can_use(candidate, strict=True):
            continue
        append_candidate(candidate)

    # Garante que mídias ainda ausentes tenham uma chance antes de relaxar os
    # limites de repetição. Isso mantém variedade de câmera em lotes pequenos.
    if len(selected) < max_clips:
        present_assets = {item.get("asset_id") for item in selected}
        for asset in assets:
            asset_id = asset.get("id")
            if asset_id in present_assets:
                continue
            best = next(
                (
                    item for item in ranked_all
                    if item.get("asset_id") == asset_id
                    and _candidate_key(item) not in selected_keys
                ),
                None,
            )
            if best is None:
                continue
            append_candidate(best)
            present_assets.add(asset_id)
            if len(selected) >= max_clips:
                break

    # Se referência/filme longo exigir mais takes, relaxa apenas o limite por
    # mídia. Ainda bloqueia sobreposição e cenas praticamente consecutivas.
    if estimated_total < target_ms and len(selected) < max_clips:
        for candidate in ranked_all:
            if len(selected) >= max_clips or estimated_total >= target_ms:
                break
            if not can_use(candidate, strict=False):
                continue
            append_candidate(candidate)

    # A narrativa continua agrupada por capítulo, porém dentro de cada
    # capítulo preservamos a sequência diversificada escolhida pelo seletor.
    # Ordenar por asset_id aqui fazia A,A,A,B,B,C e anulava a diversidade.
    order = {name: index for index, name in enumerate(STORY_ORDER)}
    selected.sort(
        key=lambda item: (
            order.get(item.get("story_section"), len(STORY_ORDER)),
            int(item.get("_selection_order", 0)),
        )
    )
    for item in selected:
        item.pop("_selection_order", None)

    classified = [
        item for item in candidates
        if item.get("semantic_story_section") in STORY_ORDER
    ]
    confidences = [
        float(item.get("semantic_confidence", 0) or 0)
        for item in classified
    ]

    return {
        "schema_version": "0.3",
        "engine": "wedding-story-builder-v1",
        "best_shot_engine": "best-shot-selector-v2",
        "semantic_engine": "wedding-semantics-v1",
        "story_order": list(STORY_ORDER),
        "selected_candidates": selected,
        "section_stats": [section_stats[name] for name in STORY_ORDER],
        "classified_candidates": len(classified),
        "unclassified_candidates": len(candidates) - len(classified),
        "average_semantic_confidence": (
            round(sum(confidences) / len(confidences), 3)
            if confidences
            else 0.0
        ),
        "preferred_per_asset_limit": preferred_asset_limit,
        "selected_asset_usage": asset_usage(selected),
    }
