from __future__ import annotations

import math
import tempfile
import wave
from array import array
from pathlib import Path
from statistics import median

from core.processing import ProcessingError, check_cancelled
from media.process import run_media


class MusicAnalyzer:
    """Local music structure analyzer used by wedding/reference editing.

    V1 extracts a mono PCM WAV with FFmpeg and measures energy peaks and
    transitions. `tempo_bpm_estimate` is deliberately labelled as an estimate;
    it is not intended to replace a dedicated musical beat tracker.
    """

    def __init__(self, ffmpeg_path=None, runner=run_media):
        self.ffmpeg_path = ffmpeg_path
        self.runner = runner

    def analyze(
        self,
        source,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise ProcessingError("A musica selecionada nao foi encontrada.")

        check_cancelled(cancel)
        stage("Preparando audio para analisar ritmo...")
        progress(5)

        if source.suffix.lower() == ".wav":
            try:
                result = self.analyze_wav(source, cancel=cancel)
            except (wave.Error, EOFError):
                result = None
            if result is not None:
                progress(100)
                stage("Analise musical concluida.")
                return result

        if not self.ffmpeg_path:
            raise ProcessingError(
                "FFmpeg nao encontrado para analisar a musica selecionada."
            )

        with tempfile.TemporaryDirectory(prefix="takedream-music-") as temporary:
            wav_path = Path(temporary) / "music-analysis.wav"
            command = [
                self.ffmpeg_path,
                "-hide_banner",
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(wav_path),
            ]
            self.runner(command, cancel=cancel, timeout=600)
            check_cancelled(cancel)
            progress(35)
            result = self.analyze_wav(wav_path, cancel=cancel)

        progress(100)
        stage("Analise musical concluida.")
        return result

    @staticmethod
    def analyze_wav(path, *, cancel=None, frame_ms=100):
        path = Path(path)
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            total_frames = handle.getnframes()

            if sample_width != 2:
                raise ProcessingError(
                    "A analise musical V1 espera audio PCM de 16 bits."
                )
            if sample_rate <= 0 or total_frames <= 0:
                raise ProcessingError("Audio invalido para analise musical.")

            samples_per_window = max(1, int(sample_rate * frame_ms / 1000))
            bytes_per_window = samples_per_window * channels * sample_width
            energies = []
            positions_ms = []
            frame_cursor = 0

            while True:
                check_cancelled(cancel)
                raw = handle.readframes(samples_per_window)
                if not raw:
                    break
                values = array("h")
                values.frombytes(raw[: bytes_per_window])
                if not values:
                    break

                if channels > 1:
                    mono = []
                    for index in range(0, len(values) - channels + 1, channels):
                        mono.append(
                            sum(values[index:index + channels]) / channels
                        )
                    values_for_rms = mono
                else:
                    values_for_rms = values

                square_sum = sum(float(value) * float(value) for value in values_for_rms)
                rms = math.sqrt(square_sum / max(1, len(values_for_rms))) / 32768.0
                energies.append(max(0.0, min(1.0, rms)))
                positions_ms.append(int(round(frame_cursor * 1000 / sample_rate)))
                frame_cursor += len(raw) // (channels * sample_width)

        duration_ms = int(round(total_frames * 1000 / sample_rate))
        if not energies:
            raise ProcessingError("Nao foi possivel medir a energia da musica.")

        maximum = max(energies) or 1.0
        normalized = [value / maximum for value in energies]
        baseline = median(normalized)
        threshold = max(0.22, min(0.78, baseline * 1.45))

        peaks = []
        last_peak_ms = -1000
        for index in range(1, len(normalized) - 1):
            value = normalized[index]
            if value < threshold:
                continue
            if value < normalized[index - 1] or value < normalized[index + 1]:
                continue
            position = positions_ms[index]
            if position - last_peak_ms < 280:
                if peaks and value > peaks[-1]["strength"]:
                    peaks[-1] = {"time_ms": position, "strength": round(value, 4)}
                    last_peak_ms = position
                continue
            peaks.append({"time_ms": position, "strength": round(value, 4)})
            last_peak_ms = position

        intervals = [
            peaks[index]["time_ms"] - peaks[index - 1]["time_ms"]
            for index in range(1, len(peaks))
            if 280 <= peaks[index]["time_ms"] - peaks[index - 1]["time_ms"] <= 1800
        ]
        tempo = None
        if intervals:
            interval = median(intervals)
            if interval > 0:
                tempo = 60000.0 / interval
                while tempo < 60:
                    tempo *= 2
                while tempo > 180:
                    tempo /= 2
                tempo = round(tempo, 1)

        transitions = []
        for index in range(2, len(normalized)):
            before = sum(normalized[max(0, index - 3):index]) / min(3, index)
            after_slice = normalized[index:min(len(normalized), index + 3)]
            if not after_slice:
                continue
            after = sum(after_slice) / len(after_slice)
            delta = after - before
            if abs(delta) >= 0.22:
                position = positions_ms[index]
                if not transitions or position - transitions[-1]["time_ms"] >= 800:
                    transitions.append(
                        {
                            "time_ms": position,
                            "direction": "up" if delta > 0 else "down",
                            "strength": round(abs(delta), 4),
                        }
                    )

        section_count = 8
        energy_sections = []
        for section in range(section_count):
            start_index = int(len(normalized) * section / section_count)
            end_index = int(len(normalized) * (section + 1) / section_count)
            values = normalized[start_index:max(start_index + 1, end_index)]
            energy_sections.append(
                {
                    "index": section,
                    "start_ms": int(duration_ms * section / section_count),
                    "end_ms": int(duration_ms * (section + 1) / section_count),
                    "energy": round(sum(values) / max(1, len(values)), 4),
                }
            )

        strongest = sorted(peaks, key=lambda item: item["strength"], reverse=True)[:24]
        edit_points = sorted(
            {
                int(item["time_ms"])
                for item in strongest + transitions
                if 0 < int(item["time_ms"]) < duration_ms
            }
        )

        return {
            "schema_version": "0.1",
            "engine": "local-music-energy-v1",
            "duration_ms": duration_ms,
            "sample_rate": sample_rate,
            "analysis_window_ms": int(frame_ms),
            "tempo_bpm_estimate": tempo,
            "energy_average": round(sum(normalized) / len(normalized), 4),
            "energy_peak_count": len(peaks),
            "energy_peaks": peaks,
            "transitions": transitions,
            "energy_sections": energy_sections,
            "edit_points_ms": edit_points,
        }
