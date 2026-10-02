"""Select one short, meaningful wedding voice moment from likely vow shots."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory

from core.processing import ProcessingCancelled, ProcessingError, check_cancelled
from core.storage import read_json, write_json
from media.process import run_media
from transcription.faster_whisper import FasterWhisperTranscriber


DIALOGUE_ANALYSIS_PATH = "analysis/wedding_dialogue_focus.json"
SCHEMA_VERSION = "0.1"


PHRASE_WEIGHTS = {
    "eu prometo": 3.0,
    "prometo te": 2.8,
    "te amo": 3.0,
    "amo voce": 3.0,
    "amo você": 3.0,
    "meu amor": 2.4,
    "minha vida": 2.3,
    "para sempre": 2.5,
    "pra sempre": 2.5,
    "ao seu lado": 2.4,
    "escolho voce": 2.8,
    "escolho você": 2.8,
    "todos os dias": 2.0,
    "na alegria": 1.8,
    "na tristeza": 1.8,
    "minha esposa": 2.0,
    "meu marido": 2.0,
    "minha mulher": 1.8,
    "meu esposo": 1.8,
    "aceito": 2.2,
    "sou feliz": 1.7,
    "muito feliz": 1.5,
    "sonho": 1.2,
    "familia": 1.1,
    "família": 1.1,
}

FIRST_PERSON = (
    " eu ", " voce ", " você ", " te ", " nosso ", " nossa ",
    " minha ", " meu ", " juntos ", " juntas ",
)

OFFICIANT_PHRASES = (
    "em nome do pai",
    "eu vos declaro",
    "declaro voces",
    "declaro vocês",
    "pode beijar",
    "senhoras e senhores",
)


def _plain(value):
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def _tag_scores(clip):
    semantics = clip.get("visual_semantics") if isinstance(clip, dict) else None
    tags = semantics.get("tags") if isinstance(semantics, dict) else None
    result = {}
    for item in tags or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        try:
            result[str(item["name"])] = max(
                0.0, min(1.0, float(item.get("score", 0.0) or 0.0))
            )
        except (TypeError, ValueError):
            continue
    return result


def _visual_risk(clip):
    semantics = clip.get("visual_semantics") if isinstance(clip, dict) else None
    quality = semantics.get("quality") if isinstance(semantics, dict) else None
    if not isinstance(quality, dict):
        return 0.0
    values = []
    for key in ("whip_score", "shake_score", "motion_blur_score"):
        try:
            values.append(max(0.0, min(1.0, float(quality.get(key, 0.0) or 0.0))))
        except (TypeError, ValueError):
            values.append(0.0)
    return max(values, default=0.0)


def dialogue_candidate_score(clip):
    """Ranks likely bride/groom vow shots before doing expensive transcription."""
    if not isinstance(clip, dict) or clip.get("audio_present") is False:
        return -1.0
    duration = int(clip.get("duration_ms", 0) or 0)
    if duration < 1800:
        return -1.0

    tags = _tag_scores(clip)
    vows = tags.get("vows", 0.0)
    officiant = tags.get("officiant", 0.0)
    couple = max(
        tags.get("couple_closeup", 0.0),
        tags.get("couple_portrait", 0.0),
        tags.get("holding_hands", 0.0),
    )
    section = str(
        clip.get("semantic_story_section")
        or clip.get("story_section")
        or ""
    )
    phase = str(clip.get("director_phase") or "")
    role = str(clip.get("source_audio_role") or "")
    risk = _visual_risk(clip)
    if risk >= 0.62:
        return -1.0

    explicit = role == "dialogue" or section == "votos_falas"
    if not explicit and vows < 0.16:
        return -1.0

    score = vows * 2.6 + couple * 0.45
    if explicit:
        score += 0.90
    if phase == "vows_couple":
        score += 0.35
    if 2800 <= duration <= 6500:
        score += 0.18
    score -= officiant * 0.85
    score -= risk * 0.90
    return round(score, 4)


def _analysis_window(clip, max_ms=14000):
    safe_start = int(clip.get("source_start_ms", clip.get("start_ms", 0)) or 0)
    safe_end = int(clip.get("source_end_ms", clip.get("end_ms", safe_start)) or safe_start)
    current_start = int(clip.get("start_ms", safe_start) or safe_start)
    current_end = int(clip.get("end_ms", current_start) or current_start)
    if safe_end <= safe_start:
        safe_start, safe_end = current_start, current_end
    available = max(1, safe_end - safe_start)
    length = min(int(max_ms), available)
    center = (current_start + current_end) // 2
    start = max(safe_start, min(center - length // 2, safe_end - length))
    return start, start + length


def _cache_key(clip, start_ms, end_ms):
    source = Path(clip["path"]).expanduser().resolve()
    stat = source.stat()
    payload = [
        str(source),
        stat.st_size,
        stat.st_mtime_ns,
        int(start_ms),
        int(end_ms),
        "wedding-dialogue-whisper-v1",
    ]
    return hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()


def _extract_audio(tools, source, start_ms, end_ms, destination, cancel=None):
    if not tools.ffmpeg_path:
        raise ProcessingError("FFmpeg não encontrado para procurar votos.")
    duration_ms = max(1, int(end_ms) - int(start_ms))
    run_media(
        [
            str(tools.ffmpeg_path),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-ss",
            f"{start_ms / 1000:.3f}",
            "-t",
            f"{duration_ms / 1000:.3f}",
            "-i",
            str(Path(source).expanduser().resolve()),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(destination),
        ],
        cancel=cancel,
        timeout=90,
    )
    if not Path(destination).exists() or Path(destination).stat().st_size <= 44:
        raise ProcessingError("Não foi possível extrair o áudio do possível trecho de votos.")


def _word_probability(segment):
    values = []
    for word in segment.get("words", []) if isinstance(segment, dict) else []:
        try:
            values.append(float(word.get("probability", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    return sum(values) / len(values) if values else 0.0


def _segment_windows(segments):
    windows = []
    valid = [item for item in (segments or []) if isinstance(item, dict) and str(item.get("text") or "").strip()]
    for index, segment in enumerate(valid):
        group = [segment]
        start = int(segment.get("start_ms", 0) or 0)
        end = int(segment.get("end_ms", start) or start)
        text = str(segment.get("text") or "").strip()
        words = list(segment.get("words") or [])
        for next_segment in valid[index + 1:index + 3]:
            next_end = int(next_segment.get("end_ms", end) or end)
            if next_end - start > 7200:
                break
            combined_words = len((_plain(text + " " + str(next_segment.get("text") or ""))).split())
            if combined_words > 34:
                break
            group.append(next_segment)
            end = next_end
            text = (text + " " + str(next_segment.get("text") or "").strip()).strip()
            words.extend(next_segment.get("words") or [])
        windows.append({"start_ms": start, "end_ms": end, "text": text, "words": words})
    return windows


def dialogue_text_score(window):
    text_raw = str(window.get("text") or "").strip()
    text = _plain(text_raw)
    if not text:
        return -1.0
    padded = f" {text} "
    count = len(text.split())
    if count < 3:
        return -0.5

    score = 0.0
    for phrase, weight in PHRASE_WEIGHTS.items():
        if _plain(phrase) in text:
            score += weight
    score += sum(0.30 for token in FIRST_PERSON if _plain(token) in _plain(padded))
    score -= sum(1.2 for phrase in OFFICIANT_PHRASES if _plain(phrase) in text)

    if 6 <= count <= 26:
        score += 0.85
    elif count <= 34:
        score += 0.35

    probability = _word_probability(window)
    score += probability * 0.65
    duration = int(window.get("end_ms", 0) or 0) - int(window.get("start_ms", 0) or 0)
    if 2200 <= duration <= 6800:
        score += 0.45
    return round(score, 4)


def _shift_clip_to_dialogue(clip, analysis_start_ms, window):
    duration = max(1, int(clip.get("duration_ms", 0) or 0))
    safe_start = int(clip.get("source_start_ms", clip.get("start_ms", 0)) or 0)
    safe_end = int(clip.get("source_end_ms", clip.get("end_ms", safe_start)) or safe_start)
    phrase_start = analysis_start_ms + int(window.get("start_ms", 0) or 0)
    phrase_end = analysis_start_ms + int(window.get("end_ms", 0) or 0)
    center = (phrase_start + phrase_end) // 2

    if safe_end - safe_start >= duration:
        new_start = max(safe_start, min(center - duration // 2, safe_end - duration))
        clip["start_ms"] = int(new_start)
        clip["end_ms"] = int(new_start + duration)

    clip["source_audio_role"] = "dialogue"
    clip["source_audio_gain"] = 1.0
    clip["dialogue_director_selected"] = True
    clip["dialogue_text"] = str(window.get("text") or "").strip()
    clip["dialogue_score"] = float(window.get("score", 0.0) or 0.0)
    clip["dialogue_source_start_ms"] = int(phrase_start)
    clip["dialogue_source_end_ms"] = int(phrase_end)


class WeddingDialogueDirector:
    def __init__(self, tools, transcriber=None):
        self.tools = tools
        self.transcriber = transcriber or FasterWhisperTranscriber()

    def apply(
        self,
        project_root,
        clips,
        audio_presence,
        *,
        cancel=None,
        stage=lambda text: None,
        max_candidates=2,
    ):
        """Annotates one clip with a short meaningful dialogue moment.

        Failure to find useful speech is not fatal; the renderer can fall back to
        its visual vow heuristic. Actual transcription/model failures are also
        reported as a soft result so a wedding render never dies only because the
        emotional-audio enhancement was unavailable.
        """
        check_cancelled(cancel)
        root = Path(project_root).expanduser().resolve()
        path = root / DIALOGUE_ANALYSIS_PATH
        try:
            cached = read_json(path)
        except (OSError, ValueError):
            cached = {}
        records = {
            item.get("cache_key"): item
            for item in cached.get("records", [])
            if isinstance(item, dict) and item.get("cache_key")
        } if isinstance(cached, dict) else {}

        ranked = []
        for index, clip in enumerate(clips):
            if index >= len(audio_presence) or not audio_presence[index]:
                continue
            score = dialogue_candidate_score(clip)
            if score >= 0.0:
                ranked.append((score, index))
        ranked.sort(reverse=True)
        ranked = ranked[:max(1, int(max_candidates))]
        if not ranked:
            return {"selected_index": None, "reason": "no_vow_candidate", "records": []}

        stage("Procurando uma frase curta e importante nos votos...")
        evaluated = []
        try:
            for visual_score, index in ranked:
                check_cancelled(cancel)
                clip = clips[index]
                analysis_start, analysis_end = _analysis_window(clip)
                key = _cache_key(clip, analysis_start, analysis_end)
                record = records.get(key)
                if record is None:
                    with TemporaryDirectory(prefix="takedream-vows-") as temporary:
                        wav = Path(temporary) / "vows.wav"
                        _extract_audio(
                            self.tools,
                            clip["path"],
                            analysis_start,
                            analysis_end,
                            wav,
                            cancel=cancel,
                        )
                        transcript = self.transcriber.transcribe(
                            wav,
                            cancel=cancel,
                            stage=lambda _text: None,
                            progress=lambda _value: None,
                        )
                    windows = _segment_windows(transcript.get("segments", []))
                    scored = []
                    for window in windows:
                        item = dict(window)
                        item["score"] = dialogue_text_score(item)
                        scored.append(item)
                    scored.sort(key=lambda item: item["score"], reverse=True)
                    record = {
                        "cache_key": key,
                        "path": str(Path(clip["path"]).resolve()),
                        "analysis_start_ms": analysis_start,
                        "analysis_end_ms": analysis_end,
                        "visual_score": visual_score,
                        "language": transcript.get("language"),
                        "best_window": scored[0] if scored else None,
                    }
                    records[key] = record
                    write_json(
                        path,
                        {
                            "schema_version": SCHEMA_VERSION,
                            "engine": "wedding-dialogue-director-v1",
                            "records": list(records.values()),
                        },
                    )
                best = record.get("best_window")
                if isinstance(best, dict) and str(best.get("text") or "").strip():
                    combined = float(best.get("score", 0.0) or 0.0) + visual_score * 0.45
                    evaluated.append((combined, index, record, best))
        except ProcessingCancelled:
            raise
        except Exception as error:
            return {
                "selected_index": None,
                "reason": "transcription_unavailable",
                "error": str(error),
                "records": list(records.values()),
            }

        if not evaluated:
            return {"selected_index": None, "reason": "no_spoken_text", "records": list(records.values())}

        evaluated.sort(reverse=True, key=lambda row: row[0])
        combined, index, record, best = evaluated[0]
        # A fala pode ser simples se a imagem for claramente de votos, mas um
        # score textual positivo evita escolher ruído/duas palavras soltas.
        if float(best.get("score", 0.0) or 0.0) < 0.35:
            return {"selected_index": None, "reason": "weak_dialogue", "records": list(records.values())}

        for clip in clips:
            if clip.get("source_audio_role") == "dialogue":
                clip["source_audio_role"] = "music_priority"
                clip["source_audio_gain"] = 0.0
        _shift_clip_to_dialogue(
            clips[index],
            int(record["analysis_start_ms"]),
            best,
        )
        stage(f"Votos selecionados: “{str(best.get('text') or '').strip()[:90]}”")
        return {
            "selected_index": index,
            "reason": "selected",
            "dialogue_text": clips[index].get("dialogue_text"),
            "dialogue_score": clips[index].get("dialogue_score"),
            "combined_score": round(combined, 4),
            "records": list(records.values()),
        }
