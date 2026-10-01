from __future__ import annotations

import unicodedata


STORY_SECTIONS = (
    "making_of",
    "cerimonia",
    "votos_falas",
    "casal",
    "recepcao",
    "festa",
    "finale",
)


def _plain(value):
    text = str(value or "").lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _flatten_tags(value):
    if isinstance(value, str):
        return _plain(value)
    if isinstance(value, (list, tuple, set)):
        return " ".join(_plain(item) for item in value)
    if isinstance(value, dict):
        return " ".join(
            f"{_plain(key)} {_plain(item)}"
            for key, item in value.items()
        )
    return ""


PATH_KEYWORDS = {
    "making_of": (
        "making", "preparacao", "preparativos", "maquiagem", "vestido",
        "making noiva", "making noivo", "detalhes", "decoracao",
    ),
    "cerimonia": (
        "cerimonia", "igreja", "altar", "entrada noiva", "entrada noivo",
        "entrada padrinhos", "alianca", "aliancas", "beijo",
    ),
    "votos_falas": (
        "voto", "votos", "discurso", "speech", "depoimento", "celebrante",
        "padre", "pastor", "toast", "brinde fala",
    ),
    "casal": (
        "casal", "ensaio", "externa", "pos wedding", "pos-wedding",
        "retratos", "portrait",
    ),
    "recepcao": (
        "recepcao", "salao", "bolo", "mesa", "entrada salao", "jantar",
        "brinde",
    ),
    "festa": (
        "festa", "balada", "dance", "pista", "dj", "danca", "dancing",
    ),
    "finale": (
        "sparkler", "despedida", "encerramento", "saida dos noivos",
        "saida noivos", "chuva de arroz", "finale",
    ),
}

SPEECH_KEYWORDS = {
    "votos_falas": (
        "eu prometo", "prometo te", "aceito", "meu amor", "te amar",
        "todos os dias", "na alegria", "na tristeza", "meu marido",
        "minha esposa", "meu esposo", "minha mulher", "votos",
    ),
    "cerimonia": (
        "pode beijar", "declaro voces", "declaro vocês", "em nome do pai",
        "aliancas", "alianças", "casamento", "matrimonio", "matrimônio",
        "noivo", "noiva",
    ),
    "recepcao": (
        "um brinde", "saude aos noivos", "saúde aos noivos",
        "parabens aos noivos", "parabéns aos noivos",
    ),
}

VISION_TAG_KEYWORDS = {
    "making_of": (
        "makeup", "wedding dress", "dress detail", "getting ready",
        "bride preparation", "groom preparation", "decoration detail",
    ),
    "cerimonia": (
        "altar", "church", "wedding ceremony", "ring exchange", "rings",
        "bride entrance", "groom entrance", "kiss ceremony",
    ),
    "casal": (
        "couple portrait", "bride groom portrait", "romantic couple",
        "couple photoshoot",
    ),
    "recepcao": (
        "wedding cake", "reception table", "dinner reception", "toast",
    ),
    "festa": (
        "dance floor", "dj", "party lights", "dancing crowd",
    ),
    "finale": (
        "sparkler exit", "wedding exit", "rice toss",
    ),
}

CATEGORY_MAP = {
    "making_of_noiva": "making_of",
    "making_of_noivo": "making_of",
    "decoracao": "making_of",
    "drone": "making_of",
    "cerimonia": "cerimonia",
    "casal": "casal",
    "recepcao": "recepcao",
    "festa": "festa",
    "votos_falas": "votos_falas",
    "finale": "finale",
}


def _matches(text, groups):
    scores = {}
    evidence = {}
    for section, needles in groups.items():
        hits = [needle for needle in needles if _plain(needle) in text]
        if hits:
            scores[section] = len(hits)
            evidence[section] = hits
    return scores, evidence


def analyze_story_semantics(candidate):
    """Classifica um take usando sinais reais já disponíveis no projeto.

    Esta V1 não inventa visão computacional. Ela usa caminho/nome, categoria do
    Media Bin, texto/transcrição quando fornecidos e tags visuais somente se um
    detector real as tiver colocado no candidato. O retorno traz confiança e
    evidências para tornar a decisão auditável.
    """
    if not isinstance(candidate, dict):
        return {
            "section": "nao_classificado",
            "confidence": 0.0,
            "evidence": [],
            "engine": "wedding-semantics-v1",
        }

    category = _plain(candidate.get("category_hint"))
    path_text = " ".join(
        _plain(candidate.get(key))
        for key in ("path", "filename", "category_hint")
    )
    speech_text = " ".join(
        _plain(candidate.get(key))
        for key in (
            "speech_text",
            "transcript_text",
            "transcript",
            "recognized_text",
            "text",
        )
        if candidate.get(key)
    )
    vision_text = " ".join(
        _flatten_tags(candidate.get(key))
        for key in ("vision_tags", "visual_tags", "detected_tags", "semantic_tags")
        if candidate.get(key)
    )

    totals = {section: 0.0 for section in STORY_SECTIONS}
    evidences = {section: [] for section in STORY_SECTIONS}

    path_scores, path_evidence = _matches(path_text, PATH_KEYWORDS)
    for section, count in path_scores.items():
        totals[section] += 0.72 + min(0.14, 0.04 * (count - 1))
        evidences[section].append(
            "arquivo/pasta: " + ", ".join(path_evidence[section][:3])
        )

    mapped = CATEGORY_MAP.get(category)
    if mapped:
        totals[mapped] += 0.66
        evidences[mapped].append(f"categoria do Media Bin: {category}")

    speech_scores, speech_evidence = _matches(speech_text, SPEECH_KEYWORDS)
    for section, count in speech_scores.items():
        totals[section] += 0.86 + min(0.10, 0.03 * (count - 1))
        evidences[section].append(
            "fala/transcrição: " + ", ".join(speech_evidence[section][:3])
        )

    vision_scores, vision_evidence = _matches(vision_text, VISION_TAG_KEYWORDS)
    for section, count in vision_scores.items():
        totals[section] += 0.82 + min(0.12, 0.04 * (count - 1))
        evidences[section].append(
            "tags visuais: " + ", ".join(vision_evidence[section][:3])
        )

    best_section = max(totals, key=totals.get)
    best_score = totals[best_section]

    if best_score <= 0:
        return {
            "section": "nao_classificado",
            "confidence": 0.0,
            "evidence": [],
            "engine": "wedding-semantics-v1",
        }

    # Combina múltiplas evidências sem permitir confiança artificial > 1.
    confidence = min(0.99, best_score)
    return {
        "section": best_section,
        "confidence": round(confidence, 3),
        "evidence": evidences[best_section],
        "engine": "wedding-semantics-v1",
    }


def enrich_story_candidate(candidate):
    item = dict(candidate or {})
    semantic = analyze_story_semantics(item)
    item["semantic_story_section"] = semantic["section"]
    item["semantic_confidence"] = semantic["confidence"]
    item["semantic_evidence"] = list(semantic["evidence"])
    item["semantic_engine"] = semantic["engine"]
    return item
