import array
import json
import sys
import wave
from pathlib import Path


WAVEFORM_SCHEMA = "0.1"
DEFAULT_BUCKETS = 900
SAMPLE_WINDOW_FRAMES = 2048


def _cache_path(project_dir):
    return Path(project_dir) / "analysis" / "waveform.json"


def _wav_path(project_dir):
    return Path(project_dir) / "audio" / "extracted.wav"


def _read_cached(cache_file):
    if not cache_file.exists():
        return None

    try:
        data = json.loads(
            cache_file.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None

    if (
        data.get("schema_version") != WAVEFORM_SCHEMA
        or not isinstance(data.get("peaks"), list)
        or not data["peaks"]
    ):
        return None

    return data["peaks"]


def load_or_create_waveform(
    project_dir,
    buckets=DEFAULT_BUCKETS,
):
    project_dir = Path(project_dir)
    cache_file = _cache_path(project_dir)

    cached = _read_cached(cache_file)
    if cached is not None:
        return cached

    wav_file = _wav_path(project_dir)
    if not wav_file.exists():
        return []

    with wave.open(str(wav_file), "rb") as audio:
        if audio.getsampwidth() != 2:
            return []

        total_frames = audio.getnframes()
        channels = max(1, audio.getnchannels())

        if total_frames <= 0:
            return []

        bucket_count = max(
            1,
            min(int(buckets), total_frames),
        )
        peaks = []

        for index in range(bucket_count):
            center = int(
                ((index + 0.5) / bucket_count)
                * total_frames
            )
            start = max(
                0,
                center - SAMPLE_WINDOW_FRAMES // 2,
            )
            audio.setpos(
                min(start, total_frames - 1)
            )
            raw = audio.readframes(
                SAMPLE_WINDOW_FRAMES
            )

            if not raw:
                peaks.append(0)
                continue

            samples = array.array("h")
            samples.frombytes(raw)

            if sys.byteorder == "big":
                samples.byteswap()

            if channels > 1:
                samples = samples[::channels]

            peak = max(
                (abs(sample) for sample in samples),
                default=0,
            )
            normalized = min(
                1000,
                int(round((peak / 32768) * 1000)),
            )
            peaks.append(normalized)

    cache_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    cache_file.write_text(
        json.dumps(
            {
                "schema_version": WAVEFORM_SCHEMA,
                "peaks": peaks,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return peaks
