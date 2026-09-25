import os
import tempfile
from pathlib import Path

from core.processing import ProcessingCancelled, ProcessingError, check_cancelled
from editor.edit_plan import kept_segments, validate_edit_plan
from media.process import run_media_progress
from renderer.hardware import (
    CPU_ENCODER,
    cpu_encoder_args,
    hardware_encoder_args,
    select_h264_encoder,
)


def _seconds(milliseconds):
    return f"{milliseconds / 1000:.6f}"


def build_filter_graph(edit_plan, output_height=None):
    keep = kept_segments(edit_plan)
    if not keep:
        raise ValueError("O plano de edição não possui nenhum trecho para manter.")

    filters = []

    for index, segment in enumerate(keep):
        start = _seconds(segment["start_ms"])
        end = _seconds(segment["end_ms"])

        filters.append(
            f"[0:v:0]trim=start={start}:end={end},"
            f"setpts=PTS-STARTPTS[v{index}]"
        )
        filters.append(
            f"[0:a:0]atrim=start={start}:end={end},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )

    inputs = "".join(
        f"[v{index}][a{index}]"
        for index in range(len(keep))
    )

    if output_height is None:
        filters.append(
            f"{inputs}concat=n={len(keep)}:v=1:a=1[outv][outa]"
        )
    else:
        filters.append(
            f"{inputs}concat=n={len(keep)}:v=1:a=1[joinedv][outa]"
        )
        filters.append(
            f"[joinedv]scale=-2:{int(output_height)}:flags=lanczos[outv]"
        )

    return ";\n".join(filters)


def _render_command(
    ffmpeg_path,
    source,
    script_path,
    output_path,
    *,
    encoder_args,
    audio_bitrate,
):
    return [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(source),
        "-/filter_complex",
        str(script_path),
        "-map",
        "[outv]",
        "-map",
        "[outa]",
        *encoder_args,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        str(audio_bitrate),
        "-movflags",
        "+faststart",
        "-y",
        str(output_path),
    ]


class FFmpegRenderer:
    def __init__(self, ffmpeg_tools):
        self.tools = ffmpeg_tools
        self.last_encoder = CPU_ENCODER

    def render(
        self,
        source,
        destination,
        edit_plan,
        cancel=None,
        *,
        output_height=None,
        crf=20,
        audio_bitrate="192k",
        preset="veryfast",
        progress=lambda value: None,
        stage=lambda text: None,
        prefer_hardware=True,
    ):
        validate_edit_plan(edit_plan)
        check_cancelled(cancel)

        if not self.tools.ffmpeg_path:
            raise ProcessingError(
                "FFmpeg não encontrado. Instale o FFmpeg e adicione-o ao PATH."
            )

        source = Path(source).expanduser().resolve()
        destination = Path(destination).expanduser().resolve()

        if not source.exists():
            raise ProcessingError("O vídeo original não foi encontrado.")

        if destination.exists():
            raise ProcessingError(
                f"O arquivo de saída já existe: {destination.name}"
            )

        metadata = self.tools.probe(source, cancel=cancel)
        if not metadata["audio"]["present"]:
            raise ProcessingError(
                "A edição automática exige vídeo com faixa de áudio."
            )

        source_height = metadata.get("video", {}).get("height")
        effective_height = None
        if (
            type(output_height) is int
            and output_height > 0
            and type(source_height) is int
            and source_height > output_height
        ):
            effective_height = output_height

        destination.parent.mkdir(parents=True, exist_ok=True)

        script_fd, script_path = tempfile.mkstemp(
            suffix=".ffmpeg-filter.txt",
            prefix="takedream-",
            dir=destination.parent,
        )
        os.close(script_fd)

        output_fd, temporary_output = tempfile.mkstemp(
            suffix=".mp4",
            prefix=".render-",
            dir=destination.parent,
        )
        os.close(output_fd)
        Path(temporary_output).unlink(missing_ok=True)

        expected_duration_ms = edit_plan["stats"]["estimated_duration_ms"]

        try:
            Path(script_path).write_text(
                build_filter_graph(edit_plan, effective_height),
                encoding="utf-8",
            )

            encoder = (
                select_h264_encoder(
                    self.tools.ffmpeg_path,
                    cancel=cancel,
                )
                if prefer_hardware
                else CPU_ENCODER
            )

            if encoder.hardware:
                encoder_args = hardware_encoder_args(
                    encoder,
                    quality=crf,
                )
                stage(f"Renderizando com aceleração por GPU: {encoder.label}...")
            else:
                encoder_args = cpu_encoder_args(
                    preset=preset,
                    quality=crf,
                )
                stage("Renderizando pela CPU...")

            command = _render_command(
                self.tools.ffmpeg_path,
                source,
                script_path,
                temporary_output,
                encoder_args=encoder_args,
                audio_bitrate=audio_bitrate,
            )

            try:
                run_media_progress(
                    command,
                    duration_ms=expected_duration_ms,
                    progress=progress,
                    cancel=cancel,
                )
                self.last_encoder = encoder

            except ProcessingCancelled:
                raise

            except ProcessingError:
                if not encoder.hardware:
                    raise

                Path(temporary_output).unlink(missing_ok=True)
                progress(0)
                stage(
                    f"{encoder.label} falhou neste vídeo. "
                    "Continuando automaticamente pela CPU..."
                )

                cpu_args = cpu_encoder_args(
                    preset=preset,
                    quality=crf,
                )
                fallback_command = _render_command(
                    self.tools.ffmpeg_path,
                    source,
                    script_path,
                    temporary_output,
                    encoder_args=cpu_args,
                    audio_bitrate=audio_bitrate,
                )

                run_media_progress(
                    fallback_command,
                    duration_ms=expected_duration_ms,
                    progress=progress,
                    cancel=cancel,
                )
                self.last_encoder = CPU_ENCODER

            check_cancelled(cancel)

            if (
                not Path(temporary_output).exists()
                or Path(temporary_output).stat().st_size <= 0
            ):
                raise ProcessingError(
                    "O FFmpeg não produziu um vídeo de saída válido."
                )

            rendered_metadata = self.tools.probe(
                temporary_output,
                cancel=cancel,
            )
            if rendered_metadata["container"]["duration_seconds"] in (None, 0):
                raise ProcessingError(
                    "O vídeo renderizado possui duração inválida."
                )

            os.replace(temporary_output, destination)
            return destination

        finally:
            Path(script_path).unlink(missing_ok=True)
            Path(temporary_output).unlink(missing_ok=True)
