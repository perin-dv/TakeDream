from __future__ import annotations


def _visual_quality_risk(candidate):
    """Retorna riscos semânticos/técnicos calculados pela visão real.

    Os frames do CLIP são extraídos já dentro das margens seguras do Motion Gate.
    Portanto, whip/composition altos aqui significam defeito que ainda existe na
    região que seria usada: chicote interno, chão/teto, reposicionamento ou quadro
    sem assunto claro.
    """
    semantics = candidate.get("visual_semantics") if isinstance(candidate, dict) else None
    quality = semantics.get("quality") if isinstance(semantics, dict) else None
    if not isinstance(quality, dict):
        return 0.0, 0.0, 0.0, 0.0

    def value(name):
        try:
            return max(0.0, min(1.0, float(quality.get(name, 0.0) or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    return (
        value("whip_score"),
        value("shake_score"),
        value("motion_blur_score"),
        value("composition_risk_score"),
    )


def is_usable_wedding_candidate(candidate):
    """Gate editorial para o primeiro corte de casamento.

    Material apenas mediano continua elegível como fallback. O que é rejeitado
    cedo são falhas editoriais claras: chicote interno, tremor extremo, blur
    extremo, câmera no chão/teto e reposicionamento sem assunto.
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

    motion_classification = str(candidate.get("motion_classification") or "")
    try:
        motion_confidence = max(
            0.0,
            min(1.0, float(candidate.get("motion_confidence", 0.0) or 0.0)),
        )
    except (TypeError, ValueError):
        motion_confidence = 0.0

    # Motion Gate V2: um pico interno não pode ser "salvo" aparando bordas.
    # Se a confiança é razoável, removemos o take inteiro do corte automático.
    if motion_classification == "internal_whip" and motion_confidence >= 0.42:
        return False

    whip, shake, blur, composition = _visual_quality_risk(candidate)
    if whip >= 0.58:
        return False
    if shake >= 0.82:
        return False
    if blur >= 0.88:
        return False
    if composition >= 0.55:
        return False

    label = str(candidate.get("quality_label") or "").strip().lower()
    sampled = candidate.get("quality_sampled") is True

    # Hard reject técnico apenas para material praticamente inutilizável.
    if sampled and label == "fraca" and quality < 30.0:
        return False
    if sampled and quality > 0 and quality < 24.0:
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

    label = str(candidate.get("quality_label") or "").strip().lower()
    if label == "fraca":
        quality_penalty = 22.0
    elif label == "utilizavel":
        quality_penalty = 3.0
    else:
        quality_penalty = 0.0

    whip, shake, blur, composition = _visual_quality_risk(candidate)
    # A composição ruim pesa mais que pequenas oscilações de câmera: um take
    # tecnicamente nítido apontado para o chão continua sendo um take inválido.
    editorial_penalty = (
        whip * 34.0
        + shake * 16.0
        + blur * 12.0
        + composition * 46.0
    )

    motion_classification = str(candidate.get("motion_classification") or "")
    if motion_classification == "internal_whip":
        try:
            editorial_penalty += float(candidate.get("motion_confidence", 0.0) or 0.0) * 45.0
        except (TypeError, ValueError):
            pass

    return round(
        quality
        + semantic_bonus
        + duration_bonus
        + sampled_bonus
        - quality_penalty
        - editorial_penalty,
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

        overlap = min(end, other_end) - max(start, other_start)
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
