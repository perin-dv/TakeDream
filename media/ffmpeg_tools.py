import json
import shutil
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path


class FFmpegNotFoundError(RuntimeError):
    pass


class MediaProbeError(RuntimeError):
    pass


class FFmpegTools:
    def __init__(self):
        self.ffmpeg_path = shutil.which("ffmpeg")
        self.ffprobe_path = shutil.which("ffprobe")

    @property
    def is_available(self):
        return bool(self.ffmpeg_path and self.ffprobe_path)

    def availability(self):
        return {
            "ffmpeg": self.ffmpeg_path,
            "ffprobe": self.ffprobe_path,
            "available": self.is_available,
        }

    def probe(self, source_video):
        if not self.ffprobe_path:
            raise FFmpegNotFoundError(
                "FFprobe não foi encontrado no sistema. Instale o FFmpeg e "
                "reinicie o terminal antes de analisar o vídeo."
            )

        source_path = Path(source_video).expanduser().resolve()

        if not source_path.exists():
            raise MediaProbeError("O arquivo de vídeo não existe.")

        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise MediaProbeError(
                f"Não foi possível executar o FFprobe: {error}"
            ) from error

        if result.returncode != 0:
            details = result.stderr.strip() or "Erro desconhecido do FFprobe."
            raise MediaProbeError(
                f"FFprobe não conseguiu analisar o vídeo.\n\n{details}"
            )

        try:
            raw = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise MediaProbeError(
                "O FFprobe retornou dados inválidos."
            ) from error

        return self._normalize_probe(source_path, raw)

    def _normalize_probe(self, source_path, raw):
        streams = raw.get("streams", [])
        format_data = raw.get("format", {})

        video_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            None,
        )
        audio_stream = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            None,
        )

        if video_stream is None:
            raise MediaProbeError(
                "Nenhuma faixa de vídeo foi encontrada no arquivo selecionado."
            )

        duration_seconds = self._to_float(format_data.get("duration"))

        if duration_seconds is None:
            duration_seconds = self._to_float(video_stream.get("duration"))

        frame_rate = self._parse_frame_rate(
            video_stream.get("avg_frame_rate")
            or video_stream.get("r_frame_rate")
        )

        width = video_stream.get("width")
        height = video_stream.get("height")

        metadata = {
            "schema_version": "0.1",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "path": str(source_path),
                "filename": source_path.name,
            },
            "container": {
                "format_name": format_data.get("format_name"),
                "format_long_name": format_data.get("format_long_name"),
                "duration_seconds": duration_seconds,
                "duration_display": self.format_duration(duration_seconds),
                "size_bytes": self._to_int(format_data.get("size")),
                "bit_rate": self._to_int(format_data.get("bit_rate")),
            },
            "video": {
                "codec": video_stream.get("codec_name"),
                "codec_long_name": video_stream.get("codec_long_name"),
                "width": width,
                "height": height,
                "resolution": (
                    f"{width}x{height}" if width and height else "Desconhecida"
                ),
                "fps": frame_rate,
                "pixel_format": video_stream.get("pix_fmt"),
            },
            "audio": {
                "present": audio_stream is not None,
                "codec": audio_stream.get("codec_name") if audio_stream else None,
                "codec_long_name": (
                    audio_stream.get("codec_long_name") if audio_stream else None
                ),
                "sample_rate": (
                    self._to_int(audio_stream.get("sample_rate"))
                    if audio_stream
                    else None
                ),
                "channels": audio_stream.get("channels") if audio_stream else None,
                "channel_layout": (
                    audio_stream.get("channel_layout") if audio_stream else None
                ),
            },
            "tools": self.availability(),
        }

        return metadata

    @staticmethod
    def format_duration(seconds):
        if seconds is None:
            return "Desconhecida"

        total_seconds = max(0, int(round(seconds)))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _parse_frame_rate(value):
        if not value or value == "0/0":
            return None

        try:
            return round(float(Fraction(value)), 3)
        except (ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
