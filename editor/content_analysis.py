import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher


FILLERS = {
    "ah",
    "ahn",
    "hã",
    "hum",
    "hmm",
    "uh",
    "uhm",
    "erm",
}

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "que", "pra", "para", "por", "com", "sem",
    "mais", "mas", "como", "isso", "essa", "esse", "esta",
    "este", "aqui", "ali", "ele", "ela", "eles", "elas",
    "eu", "voce", "voces", "meu", "minha", "seu", "sua",
    "tem", "vai", "vou", "foi", "ser", "estar", "esta",
    "muito", "muita", "muitos", "muitas", "tambem", "entao",
    "né", "nao", "sim",
}


def _normalize(value):
    text = unicodedata.normalize(
        "NFKD",
        str(value).lower(),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def _word_text(word):
    if isinstance(word, dict):
        return str(
            word.get("word")
            or word.get("text")
            or ""
        )
    return str(word)


def _timestamp(word, key):
    if not isinstance(word, dict):
        return None

    value = word.get(key)
    if type(value) is int:
        return value

    return None


def _segment_words(segment):
    words = segment.get("words")
    return words if isinstance(words, list) else []


def _keywords(text, limit=3):
    tokens = [
        token
        for token in _normalize(text).split()
        if len(token) >= 5
        and token not in STOPWORDS
    ]

    if not tokens:
        return []

    counts = Counter(tokens)
    ranked = sorted(
        counts,
        key=lambda token: (
            counts[token],
            len(token),
        ),
        reverse=True,
    )
    return ranked[:limit]


def analyze_content(
    transcript,
    *,
    profile="YouTube",
    style="Dinâmico",
):
    if not isinstance(transcript, dict):
        raise ValueError("Transcrição inválida.")

    segments = transcript.get("segments")
    if not isinstance(segments, list):
        raise ValueError(
            "Transcrição não possui segmentos válidos."
        )

    filler_suggestions = []
    word_repetition_suggestions = []
    repetition_suggestions = []
    broll_suggestions = []
    zoom_events = []

    for segment_index, segment in enumerate(segments):
        previous_word = None

        for word_index, word in enumerate(
            _segment_words(segment)
        ):
            normalized = _normalize(
                _word_text(word)
            )
            start_ms = _timestamp(word, "start_ms")
            end_ms = _timestamp(word, "end_ms")

            if (
                start_ms is None
                or end_ms is None
                or end_ms <= start_ms
            ):
                previous_word = normalized or previous_word
                continue

            if normalized in FILLERS:
                filler_suggestions.append(
                    {
                        "type": "filler",
                        "segment_id": segment.get(
                            "id",
                            segment_index,
                        ),
                        "word_index": word_index,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "text": _word_text(word).strip(),
                        "confidence": 0.9,
                        "suggested_action": "review_remove",
                    }
                )

            if (
                normalized
                and normalized == previous_word
                and normalized not in FILLERS
                and len(normalized) > 1
            ):
                word_repetition_suggestions.append(
                    {
                        "type": "word_repetition",
                        "segment_id": segment.get(
                            "id",
                            segment_index,
                        ),
                        "word_index": word_index,
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "text": _word_text(word).strip(),
                        "confidence": 0.88,
                        "suggested_action": "review_remove",
                    }
                )

            if normalized:
                previous_word = normalized

    previous = None

    for index, segment in enumerate(segments):
        current_text = _normalize(
            segment.get("text", "")
        )

        if (
            previous is not None
            and len(current_text) >= 12
            and len(previous["text"]) >= 12
        ):
            similarity = SequenceMatcher(
                None,
                previous["text"],
                current_text,
            ).ratio()

            if similarity >= 0.82:
                repetition_suggestions.append(
                    {
                        "type": "possible_repetition",
                        "first_segment_id": previous["id"],
                        "second_segment_id": segment.get(
                            "id",
                            index,
                        ),
                        "start_ms": segment.get(
                            "start_ms",
                            0,
                        ),
                        "end_ms": segment.get(
                            "end_ms",
                            0,
                        ),
                        "text": segment.get(
                            "text",
                            "",
                        ).strip(),
                        "similarity": round(
                            similarity,
                            3,
                        ),
                        "suggested_action": "review_remove",
                    }
                )

        if current_text:
            previous = {
                "id": segment.get("id", index),
                "text": current_text,
            }

    last_broll_ms = -20000
    for index, segment in enumerate(segments):
        start_ms = int(
            segment.get("start_ms", 0)
        )
        end_ms = int(
            segment.get("end_ms", start_ms)
        )
        text = str(
            segment.get("text", "")
        ).strip()

        keywords = _keywords(text)

        if (
            keywords
            and start_ms - last_broll_ms >= 15000
            and end_ms > start_ms
        ):
            broll_suggestions.append(
                {
                    "segment_id": segment.get(
                        "id",
                        index,
                    ),
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "keywords": keywords,
                    "query": " ".join(keywords),
                    "status": "suggested",
                }
            )
            last_broll_ms = start_ms

    dynamic = str(style).lower() in {
        "dinâmico",
        "dinamico",
        "highlights",
        "conversão",
        "conversao",
    }

    minimum_gap = 9000 if dynamic else 15000
    last_zoom_ms = -minimum_gap

    if str(profile).lower() != "casamento":
        for index, segment in enumerate(segments):
            start_ms = int(
                segment.get("start_ms", 0)
            )
            end_ms = int(
                segment.get("end_ms", start_ms)
            )
            text = str(
                segment.get("text", "")
            ).strip()

            if (
                end_ms <= start_ms
                or len(_normalize(text).split()) < 6
                or start_ms - last_zoom_ms < minimum_gap
            ):
                continue

            zoom_events.append(
                {
                    "segment_id": segment.get(
                        "id",
                        index,
                    ),
                    "start_ms": start_ms,
                    "end_ms": min(
                        end_ms,
                        start_ms + 2800,
                    ),
                    "scale": (
                        1.07
                        if dynamic
                        else 1.04
                    ),
                    "reason": "speech_emphasis",
                }
            )
            last_zoom_ms = start_ms

    return {
        "schema_version": "0.1",
        "engine": "local-semantic-v1",
        "profile": profile,
        "style": style,
        "summary": {
            "fillers": len(filler_suggestions),
            "word_repetitions": len(
                word_repetition_suggestions
            ),
            "possible_repetitions": len(
                repetition_suggestions
            ),
            "broll_suggestions": len(
                broll_suggestions
            ),
            "zoom_events": len(zoom_events),
        },
        "speech_suggestions": (
            filler_suggestions
            + word_repetition_suggestions
            + repetition_suggestions
        ),
        "broll_suggestions": broll_suggestions,
        "zoom_events": zoom_events,
    }
