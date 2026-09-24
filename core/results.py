"""Validate persisted results before displaying or reusing them."""
import math
from pathlib import Path

from core.processing import ProcessingCancelled, ProcessingError
from core.storage import read_json
from media.audio_extractor import wav_duration_ms

AUDIO_PATH = "audio/extracted.wav"
TRANSCRIPT_PATH = "transcription/transcript.json"
SILENCES_PATH = "analysis/silences.json"


def _integer(value):
    return type(value) is int and value >= 0


def _probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def _interval(item):
    return (isinstance(item, dict) and _integer(item.get("start_ms"))
            and _integer(item.get("end_ms")) and item["end_ms"] >= item["start_ms"])


def _require(condition):
    if not condition:
        raise ValueError("Contrato de resultado inválido.")


def validate_transcript(data):
    try:
        _require(isinstance(data, dict) and data["schema_version"] == "0.1")
        _require(all(isinstance(data["model"][key], str) and data["model"][key] for key in ("name", "device", "compute_type")))
        _require(isinstance(data["language"]["detected"], str) and data["language"]["detected"])
        _require(_probability(data["language"]["probability"]))
        _require(isinstance(data["text"], str) and isinstance(data["segments"], list))
        previous_start = 0
        for segment in data["segments"]:
            _require(_interval(segment) and _integer(segment["id"]))
            _require(segment["start_ms"] >= previous_start)
            previous_start = segment["start_ms"]
            _require(isinstance(segment["text"], str))
            _require(isinstance(segment.get("words", []), list))
            for word in segment.get("words", []):
                _require(_interval(word) and isinstance(word["word"], str))
                _require(_probability(word["probability"]))
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("transcript.json possui estrutura inválida ou timestamps inválidos.") from error
    return data


def validate_silences(data):
    try:
        _require(isinstance(data, dict) and data["schema_version"] == "0.1")
        _require(type(data["threshold_db"]) in (int, float) and math.isfinite(data["threshold_db"]))
        _require(_integer(data["minimum_duration_ms"]) and data["minimum_duration_ms"] > 0)
        _require(isinstance(data["silences"], list))
        previous_end = 0
        for silence in data["silences"]:
            _require(_interval(silence) and _integer(silence["duration_ms"]))
            _require(silence["duration_ms"] == silence["end_ms"] - silence["start_ms"])
            _require(silence["start_ms"] >= previous_end)
            previous_end = silence["end_ms"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("silences.json possui estrutura inválida ou timestamps inválidos.") from error
    return data


def load_results(project_dir, cancel=None):
    root = Path(project_dir)
    result = {"audio_path": None, "transcript": None, "silences": None, "errors": []}
    if (root / AUDIO_PATH).exists():
        try:
            wav_duration_ms(root / AUDIO_PATH, cancel)
            result["audio_path"] = AUDIO_PATH
        except ProcessingError as error:
            if isinstance(error, ProcessingCancelled):
                raise
            result["errors"].append(str(error))
    for key, path, validate in (("transcript", TRANSCRIPT_PATH, validate_transcript),
                                ("silences", SILENCES_PATH, validate_silences)):
        if (root / path).exists():
            try:
                result[key] = validate(read_json(root / path))
            except ValueError as error:
                result["errors"].append(f"{path}: {error}")
    return result
