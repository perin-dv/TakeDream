import re

from core.processing import ProcessingError, seconds_to_ms
from media.audio_extractor import wav_duration_ms
from media.process import run_media

THRESHOLD_DB = -35
MINIMUM_DURATION_MS = 600
_EVENT = re.compile(r"silence_(start|end):\s*([-+\d.eE]+)")


def parse_silencedetect(output, duration_ms):
    silences = []
    start = None
    for match in _EVENT.finditer(output):
        # FFmpeg can report a tiny negative rounding offset at the beginning.
        timestamp = min(duration_ms, seconds_to_ms(max(0.0, float(match[2]))))
        if match[1] == "start":
            if start is None:
                start = timestamp
        elif start is not None:
            end = max(start, timestamp)
            silences.append({"start_ms": start, "end_ms": end, "duration_ms": end - start})
            start = None
    if start is not None:
        silences.append({"start_ms": start, "end_ms": duration_ms, "duration_ms": duration_ms - start})
    return silences


class SilenceDetector:
    def __init__(self, ffmpeg_tools):
        self.tools = ffmpeg_tools

    def detect(self, audio_path, cancel=None):
        if not self.tools.ffmpeg_path:
            raise ProcessingError("FFmpeg não encontrado. Instale o FFmpeg e adicione-o ao PATH.")
        duration = wav_duration_ms(audio_path, cancel)
        _, output = run_media([
            self.tools.ffmpeg_path, "-hide_banner", "-nostdin", "-nostats", "-i", str(audio_path),
            "-af", f"silencedetect=noise={THRESHOLD_DB}dB:d={MINIMUM_DURATION_MS / 1000}",
            "-f", "null", "-",
        ], cancel)
        return {"schema_version": "0.1", "threshold_db": THRESHOLD_DB,
                "minimum_duration_ms": MINIMUM_DURATION_MS,
                "silences": parse_silencedetect(output, duration)}
