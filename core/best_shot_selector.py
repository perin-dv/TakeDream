from __future__ import annotations


def is_usable_wedding_candidate(candidate):
    """Quality gate conservador para o primeiro corte de casamento.

    Cenas realmente amostradas pelo FFmpeg e marcadas como fracas são
    descartadas. Cenas cuja qualidade foi apenas estimada continuam elegíveis,
    porque não temos evidência suficiente para rejeitá-las.
    """
    if not isinstance(candidate, dict):
        return False

    try:
        duration_ms = int(candidate.get("duration_ms", 0) or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    if duration_ms < 500:
        return False

    try:
        quality = float(candidate.get("score", 0) or 0)
    except (TypeError, ValueError):
        quality = 0.0

    label = str(candidate.get("quality_label") or "").strip().lower()
    sampled = candidate.get("quality_sampled") is True

    if sampled and (label == "fraca" or quality < 52.0):
        return False
    if label == "fraca" and quality < 48.0:
        return False

    return True


def candidate_selection_score(candidate):
    if not isinstance(candidate, dict):
        return 0.0

    quality = float(candidate.get("score", 0) or 0)
    semantic = float(candidate.get("semantic_confidence", 0) or 0)
    duration_ms = max(0, int(candidate.get("duration_ms", 0) or 0))

    duration_bonus = min(4.0, duration_ms / 2500.0)
    semantic_bonus = semantic * 8.0
    sampled_bonus = 1.5 if candidate.get("quality_sampled") is True else 0.0
    degraded_penalty = 7.0 if candidate.get("quality_label") == "fraca" else 0.0

    return round(
        quality + semantic_bonus + duration_bonus + sampled_bonus - degraded_penalty,
        3,
    )


def rank_wedding_candidates(candidates):
    return sorted(
        (
            dict(item)
            for item in candidates
            if isinstance(item, dict) and is_usable_wedding_candidate(item)
        ),
        key=lambda item: (
            candidate_selection_score(item),
            float(item.get("score", 0) or 0),
            int(item.get("duration_ms", 0) or 0),
        ),
        reverse=True,
    )


def per_asset_limit(deliverable_type):
    return {
        "teaser": 2,
        "trailer": 5,
        "film": 14,
        "custom": 8,
    }.get(str(deliverable_type or "trailer"), 5)


def source_too_close(candidate, selected, minimum_gap_ms=1200):
    """Evita selecionar cenas praticamente vizinhas do mesmo arquivo."""
    asset_id = candidate.get("asset_id")
    if not asset_id:
        return False

    try:
        start = int(candidate.get("start_ms", 0) or 0)
        end = int(candidate.get("end_ms", start) or start)
    except (TypeError, ValueError):
        return False

    for other in selected:
        if other.get("asset_id") != asset_id:
            continue
        try:
            other_start = int(other.get("start_ms", 0) or 0)
            other_end = int(other.get("end_ms", other_start) or other_start)
        except (TypeError, ValueError):
            continue

        overlap = min(end, other_end) - max(start, other_end if False else other_start)
        if overlap > 0:
            return True

        gap = min(abs(start - other_end), abs(other_start - end))
        if gap < int(minimum_gap_ms):
            return True

    return False


def asset_usage(selected):
    counts = {}
    for item in selected:
        asset_id = item.get("asset_id")
        if asset_id:
            counts[asset_id] = counts.get(asset_id, 0) + 1
    return counts
