import os
import tempfile
import wave
from pathlib import Path

from core.processing import ProcessingError, check_cancelled, seconds_to_ms
from media.process import run_media


def wav_duration_ms(path, cancel=None):
    """Check format AND payload, including truncated WAVs with a valid header."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, 16000, "NONE"):
                raise ValueError("Esperado WAV PCM 16-bit, mono, 16 kHz.")
            frames = audio.getnframes()
            if frames <= 0:
                raise ValueError("O WAV está vazio.")
            remaining = frames * 2
            while remaining:
                check_cancelled(cancel)
                chunk = audio.readframes(min(65536, (remaining + 1) // 2))
                if not chunk:
                    raise ValueError("O WAV está truncado.")
                remaining -= len(chunk)
            return seconds_to_ms(frames / 16000)
    except (OSError, EOFError, wave.Error, ValueError) as error:
        raise ProcessingError(f"Áudio inválido ({Path(path).name}): {error}") from error


class AudioExtractor:
    def __init__(self, ffmpeg_tools):
        self.tools = ffmpeg_tools

    def extract(self, source, destination, cancel=None):
        destination = Path(destination)
        if destination.exists():
            wav_duration_ms(destination, cancel)
            return destination
        if not self.tools.ffmpeg_path:
            raise ProcessingError("FFmpeg não encontrado. Instale o FFmpeg e adicione-o ao PATH.")
        metadata = self.tools.probe(source, cancel=cancel)
        if not metadata["audio"]["present"]:
            raise ProcessingError("O vídeo não possui faixa de áudio.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(suffix=".wav", prefix="extracted-", dir=destination.parent)
        os.close(fd)
        try:
            run_media([
                self.tools.ffmpeg_path, "-hide_banner", "-nostdin", "-v", "error",
                "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-c:a", "pcm_s16le", "-y", temporary,
            ], cancel)
            wav_duration_ms(temporary, cancel)
            check_cancelled(cancel)
            # Windows rename refuses an existing target and works on FAT/exFAT too.
            # POSIX rename replaces the target, so use an exclusive hard link there.
            if os.name == "nt":
                os.rename(temporary, destination)
            else:
                os.link(temporary, destination)
            return destination
        finally:
            Path(temporary).unlink(missing_ok=True)
