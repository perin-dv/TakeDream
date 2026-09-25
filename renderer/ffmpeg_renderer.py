import os
import tempfile
from pathlib import Path

from core.processing import (
    ProcessingCancelled,
    ProcessingError,
    check_cancelled,
)
from editor.edit_plan import (
    kept_segments,
    validate_edit_plan,
)
from media.process import run_media_progress
from renderer.formats import (
    crop_dimensions,
    even,
    target_dimensions,
)
from renderer.hardware import (
    CPU_ENCODER,
    cpu_encoder_args,
    hardware_encoder_args,
    select_h264_encoder,
)


def _seconds(milliseconds):
    return f"{milliseconds / 1000:.6f}"


def _visual_slices(edit_plan, zoom_events=None):
    zoom_events = (
        zoom_events
        if isinstance(zoom_events, list)
        else []
    )
    slices = []

    for segment in kept_segments(edit_plan):
        start = segment["start_ms"]
        end = segment["end_ms"]
        boundaries = {start, end}

        overlapping = []

        for event in zoom_events:
            try:
                zoom_start = max(
                    start,
                    int(event["start_ms"]),
                )
                zoom_end = min(
                    end,
                    int(event["end_ms"]),
                )
                scale = float(
                    event.get("scale", 1.0)
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            if (
                zoom_end <= zoom_start
                or scale <= 1.0
            ):
                continue

            boundaries.add(zoom_start)
            boundaries.add(zoom_end)
            overlapping.append(
                (
                    zoom_start,
                    zoom_end,
                    min(scale, 1.15),
                )
            )

        ordered = sorted(boundaries)

        for index in range(len(ordered) - 1):
            part_start = ordered[index]
            part_end = ordered[index + 1]

            if part_end <= part_start:
                continue

            midpoint = int(
                (part_start + part_end) / 2
            )
            factor = 1.0

            for (
                zoom_start,
                zoom_end,
                scale,
            ) in overlapping:
                if (
                    zoom_start
                    <= midpoint
                    < zoom_end
                ):
                    factor = max(
                        factor,
                        scale,
                    )

            slices.append(
                {
                    "start_ms": part_start,
                    "end_ms": part_end,
                    "zoom": factor,
                }
            )

    return slices


def _filter_path(path):
    value = Path(path).resolve().as_posix()
    value = value.replace("\\", "/")
    value = value.replace(":", r"\:")
    value = value.replace("'", r"\'")
    return value


def build_filter_graph(
    edit_plan,
    output_height=None,
    *,
    source_width=None,
    source_height=None,
    target_aspect_ratio=None,
    output_size=None,
    zoom_events=None,
    caption_file=None,
):
    validate_edit_plan(edit_plan)

    slices = _visual_slices(
        edit_plan,
        zoom_events=zoom_events,
    )
    if not slices:
        raise ValueError(
            "O plano de edição não possui nenhum trecho para manter."
        )

    filters = []

    for index, segment in enumerate(slices):
        start = _seconds(segment["start_ms"])
        end = _seconds(segment["end_ms"])

        video_filters = [
            f"trim=start={start}:end={end}",
            "setpts=PTS-STARTPTS",
        ]

        if (
            segment["zoom"] > 1.0
            and type(source_width) is int
            and type(source_height) is int
        ):
            zoom_width = even(
                source_width
                * segment["zoom"]
            )
            zoom_height = even(
                source_height
                * segment["zoom"]
            )
            video_filters.extend(
                [
                    (
                        f"scale={zoom_width}:"
                        f"{zoom_height}:"
                        "flags=lanczos"
                    ),
                    (
                        f"crop={source_width}:"
                        f"{source_height}:"
                        f"(iw-{source_width})/2:"
                        f"(ih-{source_height})/2"
                    ),
                ]
            )

        filters.append(
            "[0:v:0]"
            + ",".join(video_filters)
            + f"[v{index}]"
        )
        filters.append(
            f"[0:a:0]atrim=start={start}:end={end},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )

    inputs = "".join(
        f"[v{index}][a{index}]"
        for index in range(len(slices))
    )

    filters.append(
        f"{inputs}concat=n={len(slices)}:"
        "v=1:a=1[joinedv][outa]"
    )

    current = "joinedv"
    stage_index = 0

    if (
        target_aspect_ratio
        and type(source_width) is int
        and type(source_height) is int
    ):
        crop_width, crop_height = crop_dimensions(
            source_width,
            source_height,
            target_aspect_ratio,
        )

        if (
            crop_width != source_width
            or crop_height != source_height
        ):
            next_label = (
                f"stagev{stage_index}"
            )
            stage_index += 1

            filters.append(
                f"[{current}]"
                f"crop={crop_width}:"
                f"{crop_height}:"
                f"(iw-{crop_width})/2:"
                f"(ih-{crop_height})/2"
                f"[{next_label}]"
            )
            current = next_label

    if output_size is not None:
        target_width, target_height = output_size
        next_label = f"stagev{stage_index}"
        stage_index += 1

        filters.append(
            f"[{current}]"
            f"scale={int(target_width)}:"
            f"{int(target_height)}:"
            "flags=lanczos"
            f"[{next_label}]"
        )
        current = next_label

    elif (
        output_height is not None
        and not target_aspect_ratio
    ):
        next_label = f"stagev{stage_index}"
        stage_index += 1

        filters.append(
            f"[{current}]"
            f"scale=-2:{int(output_height)}:"
            "flags=lanczos"
            f"[{next_label}]"
        )
        current = next_label

    if caption_file is not None:
        next_label = f"stagev{stage_index}"
        stage_index += 1
        path = _filter_path(
            caption_file
        )

        filters.append(
            f"[{current}]"
            f"ass=filename='{path}'"
            f"[{next_label}]"
        )
        current = next_label

    filters.append(
        f"[{current}]null[outv]"
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
        self.last_output_size = None

    def render(
        self,
        source,
        destination,
        edit_plan,
        cancel=None,
        *,
        output_height=None,
        target_aspect_ratio=None,
        caption_file=None,
        zoom_events=None,
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

        source = Path(
            source
        ).expanduser().resolve()
        destination = Path(
            destination
        ).expanduser().resolve()

        if not source.exists():
            raise ProcessingError(
                "O vídeo original não foi encontrado."
            )

        if destination.exists():
            raise ProcessingError(
                f"O arquivo de saída já existe: {destination.name}"
            )

        metadata = self.tools.probe(
            source,
            cancel=cancel,
        )
        if not metadata["audio"]["present"]:
            raise ProcessingError(
                "A edição automática exige vídeo com faixa de áudio."
            )

        source_width = metadata.get(
            "video",
            {},
        ).get("width")
        source_height = metadata.get(
            "video",
            {},
        ).get("height")

        if (
            type(source_width) is not int
            or type(source_height) is not int
            or source_width <= 0
            or source_height <= 0
        ):
            raise ProcessingError(
                "Não foi possível determinar a resolução do vídeo."
            )

        output_size = None

        if target_aspect_ratio:
            output_size = target_dimensions(
                source_width,
                source_height,
                target_aspect_ratio,
                short_side=output_height,
            )

        elif (
            type(output_height) is int
            and output_height > 0
            and source_height > output_height
        ):
            output_size = (
                even(
                    source_width
                    * output_height
                    / source_height
                ),
                even(output_height),
            )

        self.last_output_size = (
            output_size
            or target_dimensions(
                source_width,
                source_height,
                target_aspect_ratio,
                short_side=None,
            )
            if target_aspect_ratio
            else (
                source_width,
                source_height,
            )
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

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
        Path(temporary_output).unlink(
            missing_ok=True
        )

        expected_duration_ms = (
            edit_plan["stats"][
                "estimated_duration_ms"
            ]
        )

        try:
            Path(script_path).write_text(
                build_filter_graph(
                    edit_plan,
                    source_width=source_width,
                    source_height=source_height,
                    target_aspect_ratio=(
                        target_aspect_ratio
                    ),
                    output_size=output_size,
                    zoom_events=zoom_events,
                    caption_file=caption_file,
                ),
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
                stage(
                    "Renderizando com aceleração por GPU: "
                    f"{encoder.label}..."
                )
            else:
                encoder_args = cpu_encoder_args(
                    preset=preset,
                    quality=crf,
                )
                stage(
                    "Renderizando pela CPU..."
                )

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

                Path(
                    temporary_output
                ).unlink(
                    missing_ok=True
                )
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
                self.last_encoder = (
                    CPU_ENCODER
                )

            check_cancelled(cancel)

            if (
                not Path(
                    temporary_output
                ).exists()
                or Path(
                    temporary_output
                ).stat().st_size
                <= 0
            ):
                raise ProcessingError(
                    "O FFmpeg não produziu um vídeo de saída válido."
                )

            rendered_metadata = (
                self.tools.probe(
                    temporary_output,
                    cancel=cancel,
                )
            )
            if (
                rendered_metadata[
                    "container"
                ][
                    "duration_seconds"
                ]
                in (None, 0)
            ):
                raise ProcessingError(
                    "O vídeo renderizado possui duração inválida."
                )

            os.replace(
                temporary_output,
                destination,
            )
            return destination

        finally:
            Path(script_path).unlink(
                missing_ok=True
            )
            Path(temporary_output).unlink(
                missing_ok=True
            )
