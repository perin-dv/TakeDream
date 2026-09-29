import os
import tempfile
from pathlib import Path

from core.processing import ProcessingCancelled, ProcessingError, check_cancelled
from media.process import run_media_progress
from renderer.audio import audio_filter_chain
from renderer.formats import target_dimensions
from renderer.hardware import (
    CPU_ENCODER,
    cpu_encoder_args,
    hardware_encoder_args,
    select_h264_encoder,
)


def _sec(milliseconds):
    return f"{max(0, int(milliseconds)) / 1000:.6f}"


def _even(value):
    value = int(round(value))
    return value if value % 2 == 0 else value - 1


class MultiSourceRenderer:
    """Render a timeline whose clips may come from different source files."""

    def __init__(self, ffmpeg_tools):
        self.tools = ffmpeg_tools
        self.last_encoder = CPU_ENCODER
        self.last_output_size = None

    def _audio_present(self, source, cache, cancel=None):
        source = str(Path(source).resolve())
        if source not in cache:
            metadata = self.tools.probe(source, cancel=cancel)
            cache[source] = bool(metadata.get("audio", {}).get("present"))
        return cache[source]

    def _first_dimensions(self, source, cancel=None):
        metadata = self.tools.probe(source, cancel=cancel)
        width = metadata.get("video", {}).get("width")
        height = metadata.get("video", {}).get("height")
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ProcessingError("Não foi possível determinar a resolução da montagem.")
        return width, height

    def _build_graph(
        self,
        clips,
        width,
        height,
        audio_presence,
        audio_settings,
        *,
        music_path=None,
    ):
        filters = []
        labels = []

        for index, clip in enumerate(clips):
            zoom = float(clip.get("zoom_scale", 1.0) or 1.0)
            video_filters = [
                f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos",
                f"crop={width}:{height}",
            ]
            if zoom > 1.0:
                zoom = min(1.12, zoom)
                zw = _even(width * zoom)
                zh = _even(height * zoom)
                video_filters.extend(
                    [
                        f"scale={zw}:{zh}:flags=lanczos",
                        f"crop={width}:{height}",
                    ]
                )
            video_filters.extend(
                [
                    "setsar=1",
                    "fps=30",
                    "format=yuv420p",
                    "setpts=PTS-STARTPTS",
                ]
            )
            filters.append(f"[{index}:v:0]" + ",".join(video_filters) + f"[v{index}]")

            duration_s = max(0.05, int(clip["duration_ms"]) / 1000)
            if audio_presence[index]:
                filters.append(
                    f"[{index}:a:0]aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"atrim=duration={duration_s:.6f},asetpts=PTS-STARTPTS[a{index}]"
                )
            else:
                filters.append(
                    f"anullsrc=r=48000:cl=stereo:d={duration_s:.6f}[a{index}]"
                )
            labels.append(f"[v{index}][a{index}]")

        audio_chain = audio_filter_chain(audio_settings)
        concat_audio_label = "joineda" if (audio_chain or music_path) else "outa"
        filters.append(
            "".join(labels)
            + f"concat=n={len(clips)}:v=1:a=1[outv][{concat_audio_label}]"
        )

        base_audio = concat_audio_label
        if audio_chain:
            treated = "treateda" if music_path else "outa"
            filters.append(f"[{base_audio}]{audio_chain}[{treated}]")
            base_audio = treated

        if music_path:
            total_seconds = sum(int(clip["duration_ms"]) for clip in clips) / 1000.0
            music_index = len(clips)
            fade_start = max(0.0, total_seconds - 1.5)
            filters.append(
                f"[{base_audio}]volume=0.68[sourcea]"
            )
            filters.append(
                f"[{music_index}:a:0]aresample=48000,"
                "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"atrim=duration={total_seconds:.6f},asetpts=PTS-STARTPTS,"
                f"volume=0.30,afade=t=out:st={fade_start:.6f}:d=1.5[musica]"
            )
            filters.append(
                "[sourcea][musica]amix=inputs=2:duration=first:"
                "dropout_transition=2:normalize=0[outa]"
            )

        return ";\n".join(filters)

    def _command(self, clips, graph_path, output_path, encoder_args, *, music_path=None):
        command = [self.tools.ffmpeg_path, "-hide_banner", "-nostdin", "-v", "error"]
        for clip in clips:
            command.extend(
                [
                    "-ss",
                    _sec(clip["start_ms"]),
                    "-t",
                    _sec(clip["duration_ms"]),
                    "-i",
                    str(Path(clip["path"]).resolve()),
                ]
            )
        if music_path:
            command.extend(["-i", str(Path(music_path).expanduser().resolve())])
        command.extend(
            [
                "-/filter_complex",
                str(graph_path),
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
                "192k",
                "-movflags",
                "+faststart",
                "-y",
                str(output_path),
            ]
        )
        return command

    def render(
        self,
        clips,
        destination,
        *,
        target_aspect_ratio="16:9",
        audio_settings=None,
        music_path=None,
        cancel=None,
        progress=lambda value: None,
        stage=lambda text: None,
        prefer_hardware=True,
    ):
        check_cancelled(cancel)
        if not self.tools.ffmpeg_path:
            raise ProcessingError("FFmpeg não encontrado para montar o casamento.")
        if not isinstance(clips, list) or not clips:
            raise ProcessingError("A montagem não possui takes selecionados.")

        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ProcessingError(f"O arquivo de saída já existe: {destination.name}")

        for clip in clips:
            path = Path(clip.get("path", "")).expanduser().resolve()
            if not path.exists():
                raise ProcessingError(f"Mídia da montagem não encontrada: {path.name}")
            if int(clip.get("duration_ms", 0) or 0) <= 0:
                raise ProcessingError("A montagem contém um take com duração inválida.")

        resolved_music = None
        if music_path:
            resolved_music = Path(music_path).expanduser().resolve()
            if not resolved_music.exists() or not resolved_music.is_file():
                raise ProcessingError("A música escolhida para a montagem não foi encontrada.")

        source_width, source_height = self._first_dimensions(clips[0]["path"], cancel)
        width, height = target_dimensions(
            source_width,
            source_height,
            target_aspect_ratio,
            short_side=None,
        )
        self.last_output_size = (width, height)

        audio_cache = {}
        audio_presence = []
        for clip in clips:
            known = clip.get("audio_present")
            if isinstance(known, bool):
                audio_presence.append(known)
            else:
                audio_presence.append(
                    self._audio_present(clip["path"], audio_cache, cancel)
                )

        graph_fd, graph_name = tempfile.mkstemp(
            suffix=".ffmpeg-filter.txt",
            prefix="takedream-wedding-",
            dir=destination.parent,
        )
        os.close(graph_fd)
        output_fd, temporary_name = tempfile.mkstemp(
            suffix=".mp4",
            prefix=".wedding-render-",
            dir=destination.parent,
        )
        os.close(output_fd)
        Path(temporary_name).unlink(missing_ok=True)
        graph_path = Path(graph_name)
        temporary_output = Path(temporary_name)

        expected_duration_ms = sum(int(clip["duration_ms"]) for clip in clips)
        graph_path.write_text(
            self._build_graph(
                clips,
                width,
                height,
                audio_presence,
                audio_settings,
                music_path=resolved_music,
            ),
            encoding="utf-8",
        )

        try:
            encoder = (
                select_h264_encoder(self.tools.ffmpeg_path, cancel=cancel)
                if prefer_hardware
                else CPU_ENCODER
            )
            if encoder.hardware:
                args = hardware_encoder_args(encoder, quality=20)
                stage(f"Montando casamento com {encoder.label}...")
            else:
                args = cpu_encoder_args(preset="veryfast", quality=20)
                stage("Montando casamento pela CPU...")

            try:
                run_media_progress(
                    self._command(
                        clips,
                        graph_path,
                        temporary_output,
                        args,
                        music_path=resolved_music,
                    ),
                    duration_ms=max(1, expected_duration_ms),
                    progress=progress,
                    cancel=cancel,
                )
                self.last_encoder = encoder
            except ProcessingCancelled:
                raise
            except ProcessingError:
                if not encoder.hardware:
                    raise
                temporary_output.unlink(missing_ok=True)
                progress(0)
                stage(f"{encoder.label} falhou. Continuando pela CPU...")
                cpu_args = cpu_encoder_args(preset="veryfast", quality=20)
                run_media_progress(
                    self._command(
                        clips,
                        graph_path,
                        temporary_output,
                        cpu_args,
                        music_path=resolved_music,
                    ),
                    duration_ms=max(1, expected_duration_ms),
                    progress=progress,
                    cancel=cancel,
                )
                self.last_encoder = CPU_ENCODER

            check_cancelled(cancel)
            if not temporary_output.exists() or temporary_output.stat().st_size <= 0:
                raise ProcessingError("O FFmpeg não gerou a montagem do casamento.")
            os.replace(temporary_output, destination)
            return destination
        finally:
            graph_path.unlink(missing_ok=True)
            temporary_output.unlink(missing_ok=True)
