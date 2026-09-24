import wave
from types import SimpleNamespace


def make_wav(path, seconds=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x00\x00" * int(16000 * seconds))


def segment():
    return SimpleNamespace(id=0, start=0.125, end=0.9, text=" Olá! ",
                           words=[SimpleNamespace(start=0.125, end=0.9, word=" Olá!", probability=0.98)])


def transcript():
    from transcription.faster_whisper import serialize_segment
    return {"schema_version": "0.1", "model": {"name": "base", "device": "cpu", "compute_type": "int8"},
            "language": {"detected": "pt", "probability": 0.98}, "text": "Olá!",
            "segments": [serialize_segment(segment())]}


def silences():
    return {"schema_version": "0.1", "threshold_db": -35, "minimum_duration_ms": 600,
            "silences": [{"start_ms": 0, "end_ms": 1000, "duration_ms": 1000}]}
