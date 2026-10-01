from __future__ import annotations

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
    """Compatibilidade pública para a classificação da narrativa.

    A decisão agora passa pelo classificador semântico V1, que também expõe
    confiança e evidências quando usado por ``build_story_candidate_plan``.
    """
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
    """Seleciona e ordena candidatos por capítulos de casamento.

    O Story Builder trabalha com decisões auditáveis. Cada candidato recebe a
    seção, confiança e evidências semânticas; material sem evidência suficiente
    continua disponível como fallback por qualidade.
    """
    candidates = [
        enrich_story_candidate(dict(item))
        for item in candidates
        if isinstance(item, dict)
    ]
    assets = [item for item in (assets or []) if isinstance(item, dict)]
    target_ms = max(1000, int(target_ms))
    base_clip_ms = max(500, int(base_clip_ms))
    max_clips = max(1, int(max_clips))

    asset_order = {
        asset.get("id"): index
        for index, asset in enumerate(assets)
    }

    grouped = {name: [] for name in STORY_ORDER}
    unclassified = []
    for candidate in candidates:
        section = candidate.get("semantic_story_section") or "nao_classificado"
        candidate["story_section"] = section
        if section in grouped:
            grouped[section].append(candidate)
        else:
            unclassified.append(candidate)

    def rank(items):
        return sorted(
            items,
            key=lambda item: (
                float(item.get("score", 0) or 0),
                float(item.get("semantic_confidence", 0) or 0),
                int(item.get("duration_ms", 0) or 0),
            ),
            reverse=True,
        )

    grouped = {name: rank(items) for name, items in grouped.items()}
    unclassified = rank(unclassified)
    budgets = _section_budgets(deliverable, target_ms)

    selected = []
    selected_keys = set()
    estimated_total = 0
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
                key = _candidate_key(candidate)
                if key in selected_keys:
                    continue
                asset_id = candidate.get("asset_id")
                if diversity_pass and asset_id in used_assets:
                    continue
                if not diversity_pass and section_stats[section]["estimated_ms"] >= quota:
                    break

                selected.append(candidate)
                selected_keys.add(key)
                used_assets.add(asset_id)
                estimate = _duration_ms(candidate, base_clip_ms)
                estimated_total += estimate
                section_stats[section]["estimated_ms"] += estimate
                section_stats[section]["selected_count"] += 1

                if section_stats[section]["estimated_ms"] >= quota:
                    break
            if section_stats[section]["estimated_ms"] >= quota or len(selected) >= max_clips:
                break

    fallback_pool = unclassified + rank(candidates)
    for candidate in fallback_pool:
        if len(selected) >= max_clips or estimated_total >= target_ms:
            break
        key = _candidate_key(candidate)
        if key in selected_keys:
            continue
        copy = dict(candidate)
        copy["story_section"] = copy.get("story_section") or "nao_classificado"
        selected.append(copy)
        selected_keys.add(key)
        estimated_total += _duration_ms(copy, base_clip_ms)

    if len(selected) < max_clips:
        ranked_all = rank(candidates)
        present_assets = {item.get("asset_id") for item in selected}
        for asset in assets:
            asset_id = asset.get("id")
            if asset_id in present_assets:
                continue
            best = next((item for item in ranked_all if item.get("asset_id") == asset_id), None)
            if best is None:
                continue
            key = _candidate_key(best)
            if key in selected_keys:
                continue
            copy = dict(best)
            copy["story_section"] = copy.get("semantic_story_section") or "nao_classificado"
            selected.append(copy)
            selected_keys.add(key)
            present_assets.add(asset_id)
            if len(selected) >= max_clips:
                break

    order = {name: index for index, name in enumerate(STORY_ORDER)}
    selected.sort(
        key=lambda item: (
            order.get(item.get("story_section"), len(STORY_ORDER)),
            asset_order.get(item.get("asset_id"), 999999),
            int(item.get("start_ms", 0) or 0),
        )
    )

    classified = [
        item for item in candidates
        if item.get("semantic_story_section") in STORY_ORDER
    ]
    confidences = [
        float(item.get("semantic_confidence", 0) or 0)
        for item in classified
    ]

    return {
        "schema_version": "0.2",
        "engine": "wedding-story-builder-v1",
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
    }
