import os
import tempfile
from pathlib import Path

from core.processing import ProcessingCancelled, ProcessingError, check_cancelled
from core.wedding_dialogue_director import WeddingDialogueDirector
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


def _semantic_tag_scores(clip):
    semantics = clip.get("visual_semantics") if isinstance(clip, dict) else None
    tags = semantics.get("tags") if isinstance(semantics, dict) else None
    if not isinstance(tags, list):
        return {}
    result = {}
    for item in tags:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        try:
            result[str(item["name"])] = max(
                0.0,
                min(1.0, float(item.get("score", 0.0) or 0.0)),
            )
        except (TypeError, ValueError):
            continue
    return result


def _visual_risk(clip):
    semantics = clip.get("visual_semantics") if isinstance(clip, dict) else None
    quality = semantics.get("quality") if isinstance(semantics, dict) else None
    if not isinstance(quality, dict):
        return 0.0
    values = []
    for key in ("whip_score", "shake_score", "motion_blur_score"):
        try:
            values.append(max(0.0, min(1.0, float(quality.get(key, 0.0) or 0.0))))
        except (TypeError, ValueError):
            values.append(0.0)
    return max(values, default=0.0)


def _timeline_midpoints(clips):
    cursor = 0
    result = []
    for clip in clips:
        duration = max(0, int(clip.get("duration_ms", 0) or 0))
        result.append(cursor + duration // 2)
        cursor += duration
    return result


def _dialogue_focus_indexes(clips, audio_presence, max_focus=2):
    """Fallback visual para voz quando o Whisper não encontra frase útil."""
    midpoints = _timeline_midpoints(clips)
    ranked = []
    for index, clip in enumerate(clips):
        if index >= len(audio_presence) or not audio_presence[index]:
            continue
        duration = int(clip.get("duration_ms", 0) or 0)
        if duration < 1800 or duration > 8000:
            continue

        tags = _semantic_tag_scores(clip)
        vows = tags.get("vows", 0.0)
        section = str(
            clip.get("semantic_story_section")
            or clip.get("story_section")
            or ""
        )
        phase = str(clip.get("director_phase") or "")
        role = str(clip.get("source_audio_role") or "")
        risk = _visual_risk(clip)
        if risk >= 0.62:
            continue

        explicit = role == "dialogue" or section == "votos_falas"
        if not explicit and vows < 0.18:
            continue

        score = vows * 2.2
        if explicit:
            score += 1.1
        if section == "votos_falas":
            score += 0.55
        if phase == "vows_couple":
            score += 0.30
        if 2600 <= duration <= 6000:
            score += 0.18
        score -= risk * 0.9
        ranked.append((score, index))

    ranked.sort(reverse=True)
    selected = []
    for _score, index in ranked:
        if any(abs(midpoints[index] - midpoints[other]) < 28000 for other in selected):
            continue
        selected.append(index)
        if len(selected) >= max(1, int(max_focus)):
            break
    return set(selected)


def _slow_motion_score(clip):
    if not isinstance(clip, dict):
        return 0.0
    if clip.get("ending_director_selected"):
        return 0.0
    if str(clip.get("source_audio_role") or "") == "dialogue":
        return 0.0
    section = str(
        clip.get("semantic_story_section")
        or clip.get("story_section")
        or ""
    )
    if section == "votos_falas":
        return 0.0

    duration = int(clip.get("duration_ms", 0) or 0)
    if duration < 1800 or duration > 7000:
        return 0.0

    tags = _semantic_tag_scores(clip)
    if tags.get("vows", 0.0) >= 0.22:
        return 0.0
    hero = max(
        tags.get("kiss", 0.0),
        tags.get("couple_portrait", 0.0),
        tags.get("couple_closeup", 0.0),
        tags.get("embrace", 0.0),
        tags.get("holding_hands", 0.0),
        tags.get("bride_entrance", 0.0),
        tags.get("ring_exchange", 0.0),
        tags.get("ceremony_exit", 0.0),
        tags.get("emotional_reaction", 0.0),
        tags.get("hero_shot_candidate", 0.0),
        tags.get("strong_closing_candidate", 0.0),
    )
    semantics = clip.get("visual_semantics")
    roles = semantics.get("roles") if isinstance(semantics, dict) else {}
    try:
        hero = max(hero, float((roles or {}).get("hero_score", 0.0) or 0.0))
        highlight = float((roles or {}).get("highlight_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        highlight = 0.0

    risk = _visual_risk(clip)
    if risk >= 0.42:
        return 0.0
    return max(0.0, hero * 1.65 + highlight * 0.55 - risk * 1.15)


def _slow_rate_for_fps(fps):
    try:
        fps = float(fps)
    except (TypeError, ValueError):
        return 1.0
    if fps >= 100.0:
        return 0.50
    if fps >= 59.0:
        return 0.60
    if fps >= 49.0:
        return 0.72
    if fps >= 47.0:
        return 0.80
    return 1.0


def _select_slow_motion_rates(clips, fps_values):
    """Marca poucos hero shots para câmera lenta sem alterar a duração final."""
    rates = [1.0 for _ in clips]
    if not clips:
        return rates

    max_count = 1
    if len(clips) >= 35:
        max_count = 2
    if len(clips) >= 60:
        max_count = 3
    if len(clips) >= 95:
        max_count = 4

    midpoints = _timeline_midpoints(clips)
    ranked = []
    for index, clip in enumerate(clips):
        fps = fps_values[index] if index < len(fps_values) else None
        rate = _slow_rate_for_fps(fps)
        if rate >= 0.999:
            continue
        score = _slow_motion_score(clip)
        if score < 0.30:
            continue
        ranked.append((score, index, rate))

    ranked.sort(reverse=True)
    selected = []
    for _score, index, rate in ranked:
        if any(abs(midpoints[index] - midpoints[other]) < 18000 for other in selected):
            continue
        rates[index] = rate
        selected.append(index)
        if len(selected) >= max_count:
            break
    return rates


def _input_window(clip, playback_rate):
    """Centraliza a parte fonte usada no slow mantendo a duração da timeline."""
    start_ms = int(clip["start_ms"])
    output_ms = max(1, int(clip["duration_ms"]))
    rate = max(0.40, min(1.0, float(playback_rate or 1.0)))
    if rate >= 0.999:
        return start_ms, output_ms

    source_ms = max(250, min(output_ms, int(round(output_ms * rate))))
    offset = max(0, (output_ms - source_ms) // 2)
    return start_ms + offset, source_ms


def _source_audio_gain(clip):
    try:
        gain = float(clip.get("source_audio_gain", 1.0))
    except (TypeError, ValueError):
        gain = 1.0

    section = str(clip.get("story_section") or "nao_classificado")
    role = str(clip.get("source_audio_role") or "")

    if gain <= 0.001 and role == "music_only":
        if section == "cerimonia":
            gain = 0.42
        elif section == "finale":
            gain = 0.38
        elif section == "recepcao":
            gain = 0.18

    return max(0.0, min(gain, 1.5))


class MultiSourceRenderer:
    """Render a timeline whose clips may come from different source files."""

    def __init__(self, ffmpeg_tools):
        self.tools = ffmpeg_tools
        self.last_encoder = CPU_ENCODER
        self.last_output_size = None
        self.last_music_ducking = False
        self.last_slow_motion_count = 0
        self.last_dialogue_focus_count = 0
        self.last_dialogue_text = None
        self.last_dialogue_director_reason = None

    def _source_metadata(self, source, cache, cancel=None):
        source = str(Path(source).resolve())
        if source not in cache:
            cache[source] = self.tools.probe(source, cancel=cancel)
        return cache[source]

    def _audio_present(self, source, cache, cancel=None):
        return bool(
            self._source_metadata(source, cache, cancel)
            .get("audio", {})
            .get("present")
        )

    def _source_fps(self, source, cache, cancel=None):
        value = self._source_metadata(source, cache, cancel).get("video", {}).get("fps")
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

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
        music_ducking=True,
        slow_motion_rates=None,
        dialogue_focus_indexes=None,
    ):
        filters = []
        labels = []
        slow_motion_rates = slow_motion_rates or [1.0 for _ in clips]
        dialogue_focus_indexes = set(dialogue_focus_indexes or [])

        for index, clip in enumerate(clips):
            zoom = float(clip.get("zoom_scale", 1.0) or 1.0)
            rate = (
                float(slow_motion_rates[index])
                if index < len(slow_motion_rates)
                else 1.0
            )
            rate = max(0.40, min(1.0, rate))
            duration_s = max(0.05, int(clip["duration_ms"]) / 1000)

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
            video_filters.append("setsar=1")
            if rate < 0.999:
                video_filters.append(f"setpts=(PTS-STARTPTS)/{rate:.6f}")
            else:
                video_filters.append("setpts=PTS-STARTPTS")
            video_filters.extend(
                [
                    "fps=30",
                    f"trim=duration={duration_s:.6f}",
                    "setpts=PTS-STARTPTS",
                    "format=yuv420p",
                ]
            )
            filters.append(f"[{index}:v:0]" + ",".join(video_filters) + f"[v{index}]")

            gain = _source_audio_gain(clip)
            if music_path:
                if index in dialogue_focus_indexes:
                    gain = max(gain, 1.05)
                elif str(clip.get("source_audio_role") or "") == "dialogue":
                    gain = 0.0
            if rate < 0.999:
                gain = 0.0

            if audio_presence[index] and gain > 0.001:
                filters.append(
                    f"[{index}:a:0]aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"atrim=duration={duration_s:.6f},asetpts=PTS-STARTPTS,"
                    f"volume={gain:.3f}[a{index}]"
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

            if music_ducking:
                filters.append(
                    f"[{base_audio}]volume=0.90,asplit=2[sourcea][duckkey]"
                )
                filters.append(
                    f"[{music_index}:a:0]aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"atrim=duration={total_seconds:.6f},asetpts=PTS-STARTPTS,"
                    f"volume=0.40,afade=t=out:st={fade_start:.6f}:d=1.5[musicraw]"
                )
                filters.append(
                    "[musicraw][duckkey]sidechaincompress="
                    "threshold=0.018:ratio=10:attack=18:release=520[musica]"
                )
            else:
                filters.append(
                    f"[{base_audio}]volume=0.82[sourcea]"
                )
                filters.append(
                    f"[{music_index}:a:0]aresample=48000,"
                    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"atrim=duration={total_seconds:.6f},asetpts=PTS-STARTPTS,"
                    f"volume=0.34,afade=t=out:st={fade_start:.6f}:d=1.5[musica]"
                )

            filters.append(
                "[sourcea][musica]amix=inputs=2:duration=first:"
                "dropout_transition=2:normalize=0[outa]"
            )

        return ";\n".join(filters)

    def _command(
        self,
        clips,
        graph_path,
        output_path,
        encoder_args,
        *,
        music_path=None,
        slow_motion_rates=None,
    ):
        command = [self.tools.ffmpeg_path, "-hide_banner", "-nostdin", "-v", "error"]
        slow_motion_rates = slow_motion_rates or [1.0 for _ in clips]
        for index, clip in enumerate(clips):
            rate = slow_motion_rates[index] if index < len(slow_motion_rates) else 1.0
            source_start_ms, source_duration_ms = _input_window(clip, rate)
            command.extend(
                [
                    "-ss",
                    _sec(source_start_ms),
                    "-t",
                    _sec(source_duration_ms),
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

        metadata_cache = {}
        audio_presence = []
        fps_values = []
        for clip in clips:
            known = clip.get("audio_present")
            if isinstance(known, bool):
                audio_presence.append(known)
            else:
                audio_presence.append(
                    self._audio_present(clip["path"], metadata_cache, cancel)
                )
            fps_values.append(
                self._source_fps(clip["path"], metadata_cache, cancel)
            )

        dialogue_result = None
        dialogue_focus = set()
        self.last_dialogue_text = None
        self.last_dialogue_director_reason = None
        if resolved_music:
            try:
                project_root = destination.parent.parent
                dialogue_result = WeddingDialogueDirector(self.tools).apply(
                    project_root,
                    clips,
                    audio_presence,
                    cancel=cancel,
                    stage=stage,
                )
            except ProcessingCancelled:
                raise
            except Exception as error:
                dialogue_result = {
                    "selected_index": None,
                    "reason": "director_error",
                    "error": str(error),
                }

            self.last_dialogue_director_reason = dialogue_result.get("reason")
            self.last_dialogue_text = dialogue_result.get("dialogue_text")
            selected_index = dialogue_result.get("selected_index")
            if isinstance(selected_index, int) and 0 <= selected_index < len(clips):
                dialogue_focus = {selected_index}
            else:
                dialogue_focus = _dialogue_focus_indexes(clips, audio_presence)

        # O diretor de voz roda primeiro. Assim um take escolhido para votos nunca
        # é transformado em slow motion, e os dois efeitos não brigam pelo áudio.
        slow_motion_rates = _select_slow_motion_rates(clips, fps_values)
        self.last_slow_motion_count = sum(1 for rate in slow_motion_rates if rate < 0.999)
        self.last_dialogue_focus_count = len(dialogue_focus)

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
        ducking_enabled = bool(resolved_music)

        def write_graph(use_ducking):
            graph_path.write_text(
                self._build_graph(
                    clips,
                    width,
                    height,
                    audio_presence,
                    audio_settings,
                    music_path=resolved_music,
                    music_ducking=use_ducking,
                    slow_motion_rates=slow_motion_rates,
                    dialogue_focus_indexes=dialogue_focus,
                ),
                encoding="utf-8",
            )

        write_graph(ducking_enabled)

        slow_text = (
            f" • {self.last_slow_motion_count} slow motion(s)"
            if self.last_slow_motion_count
            else ""
        )
        voice_text = (
            f" • {self.last_dialogue_focus_count} momento(s) de votos/voz"
            if self.last_dialogue_focus_count
            else ""
        )

        try:
            encoder = (
                select_h264_encoder(self.tools.ffmpeg_path, cancel=cancel)
                if prefer_hardware
                else CPU_ENCODER
            )
            if encoder.hardware:
                args = hardware_encoder_args(encoder, quality=20)
                stage(f"Montando casamento com {encoder.label}{slow_text}{voice_text}...")
            else:
                args = cpu_encoder_args(preset="veryfast", quality=20)
                stage(f"Montando casamento pela CPU{slow_text}{voice_text}...")

            def run_current_graph(current_args):
                run_media_progress(
                    self._command(
                        clips,
                        graph_path,
                        temporary_output,
                        current_args,
                        music_path=resolved_music,
                        slow_motion_rates=slow_motion_rates,
                    ),
                    duration_ms=max(1, expected_duration_ms),
                    progress=progress,
                    cancel=cancel,
                )

            try:
                run_current_graph(args)
                self.last_encoder = encoder
                self.last_music_ducking = ducking_enabled
            except ProcessingCancelled:
                raise
            except ProcessingError:
                if encoder.hardware:
                    temporary_output.unlink(missing_ok=True)
                    progress(0)
                    stage(f"{encoder.label} falhou. Continuando pela CPU...")
                    cpu_args = cpu_encoder_args(preset="veryfast", quality=20)
                    try:
                        run_current_graph(cpu_args)
                        self.last_encoder = CPU_ENCODER
                        self.last_music_ducking = ducking_enabled
                    except ProcessingCancelled:
                        raise
                    except ProcessingError:
                        if not ducking_enabled:
                            raise
                        temporary_output.unlink(missing_ok=True)
                        progress(0)
                        stage(
                            "Ducking automático indisponível. "
                            "Continuando com mix musical simples..."
                        )
                        write_graph(False)
                        run_current_graph(cpu_args)
                        self.last_encoder = CPU_ENCODER
                        self.last_music_ducking = False
                else:
                    if not ducking_enabled:
                        raise
                    temporary_output.unlink(missing_ok=True)
                    progress(0)
                    stage(
                        "Ducking automático indisponível. "
                        "Continuando com mix musical simples..."
                    )
                    write_graph(False)
                    cpu_args = cpu_encoder_args(preset="veryfast", quality=20)
                    run_current_graph(cpu_args)
                    self.last_encoder = CPU_ENCODER
                    self.last_music_ducking = False

            check_cancelled(cancel)
            if not temporary_output.exists() or temporary_output.stat().st_size <= 0:
                raise ProcessingError("O FFmpeg não gerou a montagem do casamento.")
            os.replace(temporary_output, destination)
            return destination
        finally:
            graph_path.unlink(missing_ok=True)
            temporary_output.unlink(missing_ok=True)
