from pathlib import Path

from core.batch_visual_analysis import (
    BATCH_VISUAL_ANALYSIS_PATH,
    MOTION_GATE_SCHEMA,
    BatchVisualAnalysisPipeline,
)
from core.deliverables import normalize_deliverable
from core.ending_director import EndingDirector
from core.visual_semantics import VisualSemanticsPipeline, candidate_key
from core.semantic_signals import build_semantic_director
from core.media_library import asset_from_path, load_media_library
from core.music_pipeline import MusicAnalysisPipeline
from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.reference_pipeline import ReferenceAnalysisPipeline
from core.reference_story_director import (
    arrange_candidates_by_reference,
    build_reference_story_director,
)
from core.storage import read_json, write_json
from core.wedding_story import (
    STORY_LABELS,
    STORY_ORDER,
    build_story_candidate_plan,
)
from editor.edit_plan import build_edit_plan
from editor.reference_mapping import map_reference_timing
from media.ffmpeg_tools import FFmpegTools
from profiles import get_style_preset
from renderer.multisource_renderer import MultiSourceRenderer


WEDDING_ASSEMBLY_PLAN_PATH = "decisions/wedding_assembly_plan.json"
WEDDING_ASSEMBLY_OUTPUT = "output/wedding_assembly_base.mp4"
REFERENCE_TIMING_PATH = "decisions/reference_timing.json"
REFERENCE_STORY_DIRECTOR_PATH = "decisions/reference_story_director.json"


def _max_clips(deliverable_type):
    return {
        "teaser": 60,
        "trailer": 140,
        "film": 260,
        "custom": 180,
    }.get(deliverable_type, 140)


def _base_clip_ms(deliverable):
    average = float(deliverable.get("average_shot_seconds", 2.8) or 2.8)
    multiplier = 1.8 if deliverable.get("preserve_long_form") else 1.6
    return max(1200, int(round(average * multiplier * 1000)))


def _safe_motion_bounds(candidate, raw_start, raw_end):
    safe_start = candidate.get("motion_safe_start_ms")
    safe_end = candidate.get("motion_safe_end_ms")
    try:
        safe_start = int(safe_start)
    except (TypeError, ValueError):
        safe_start = raw_start
    try:
        safe_end = int(safe_end)
    except (TypeError, ValueError):
        safe_end = raw_end

    safe_start = max(raw_start, min(safe_start, raw_end))
    safe_end = max(raw_start, min(safe_end, raw_end))
    if safe_end - safe_start < 500:
        return raw_start, raw_end
    return safe_start, safe_end


def _window(candidate, wanted_ms):
    raw_start = int(candidate.get("start_ms", 0) or 0)
    raw_end = int(candidate.get("end_ms", raw_start) or raw_start)
    safe_start, safe_end = _safe_motion_bounds(candidate, raw_start, raw_end)

    start = safe_start
    end = safe_end
    available = max(0, end - start)
    wanted = max(0, min(int(wanted_ms), available))
    if wanted <= 0:
        return None

    if wanted < available:
        offset = int((available - wanted) / 2)
        start += offset
        end = start + wanted

    trim_start_ms = max(0, safe_start - raw_start)
    trim_end_ms = max(0, raw_end - safe_end)

    return {
        "asset_id": candidate.get("asset_id"),
        "filename": candidate.get("filename"),
        "path": candidate.get("path"),
        "category_hint": candidate.get("category_hint") or "nao_classificado",
        "story_section": candidate.get("story_section") or "nao_classificado",
        "semantic_story_section": candidate.get("semantic_story_section"),
        "semantic_confidence": candidate.get("semantic_confidence", 0.0),
        "semantic_evidence": list(candidate.get("semantic_evidence") or []),
        "visual_semantics": candidate.get("visual_semantics"),
        "semantic_slot": candidate.get("semantic_slot"),
        "ending_director_selected": candidate.get("ending_director_selected", False),
        "scene_id": candidate.get("scene_id"),
        "raw_source_start_ms": raw_start,
        "raw_source_end_ms": raw_end,
        "source_start_ms": safe_start,
        "source_end_ms": safe_end,
        "start_ms": start,
        "end_ms": end,
        "duration_ms": end - start,
        "source_duration_ms": available,
        "score": float(candidate.get("score", 0) or 0),
        "quality_label": candidate.get("quality_label"),
        "audio_present": candidate.get("audio_present"),
        "motion_gate_applied": bool(trim_start_ms or trim_end_ms),
        "motion_classification": candidate.get("motion_classification"),
        "motion_confidence": float(candidate.get("motion_confidence", 0.0) or 0.0),
        "motion_trim_start_ms": trim_start_ms,
        "motion_trim_end_ms": trim_end_ms,
        "motion_trim_total_ms": trim_start_ms + trim_end_ms,
        "motion_median": candidate.get("motion_median"),
        "motion_peak": candidate.get("motion_peak"),
        "director_phase": candidate.get("director_phase"),
        "director_phase_label": candidate.get("director_phase_label"),
        "director_target_duration_ms": candidate.get("director_target_duration_ms"),
        "director_audio_intent": candidate.get("director_audio_intent"),
        "director_reference_energy": candidate.get("director_reference_energy"),
        "zoom_scale": 1.0,
    }


def _reference_durations(reference_timing):
    if not isinstance(reference_timing, dict):
        return []
    shots = reference_timing.get("shots")
    if not isinstance(shots, list):
        return []
    values = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        try:
            duration = int(shot.get("duration_ms", 0))
        except (TypeError, ValueError):
            continue
        if duration >= 500:
            values.append(duration)
    return values


def _reference_wanted_ms(timing_durations, index, fallback_ms):
    if not timing_durations:
        return fallback_ms
    return timing_durations[index % len(timing_durations)]


def _fallback_candidates(library):
    candidates = []
    for asset in library.get("assets", []):
        seconds = asset.get("duration_seconds")
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            continue
        duration_ms = int(round(seconds * 1000))
        candidates.append(
            {
                "asset_id": asset.get("id"),
                "filename": asset.get("filename"),
                "path": asset.get("path"),
                "category_hint": asset.get("category_hint"),
                "audio_present": asset.get("audio_present"),
                "scene_id": 0,
                "start_ms": 0,
                "end_ms": duration_ms,
                "duration_ms": duration_ms,
                "score": float(asset.get("quality_average") or 60.0),
                "quality_label": "fallback",
            }
        )
    return candidates


def _valid_candidates(batch_summary, library):
    raw = batch_summary.get("best_take_candidates", []) if isinstance(batch_summary, dict) else []
    candidates = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        start = item.get("start_ms")
        end = item.get("end_ms")
        if not path or type(start) is not int or type(end) is not int or end - start < 500:
            continue
        candidates.append(dict(item))
    return candidates or _fallback_candidates(library)


def _story_section_summary(story, final_clips):
    stats = []
    source_stats = {
        item.get("key"): dict(item)
        for item in story.get("section_stats", [])
        if isinstance(item, dict) and item.get("key")
    }
    actual = {}
    counts = {}
    for clip in final_clips:
        section = clip.get("story_section") or "nao_classificado"
        actual[section] = actual.get(section, 0) + int(clip.get("duration_ms", 0) or 0)
        counts[section] = counts.get(section, 0) + 1

    for section in STORY_ORDER:
        item = source_stats.get(
            section,
            {
                "key": section,
                "label": STORY_LABELS.get(section, section),
                "budget_ms": 0,
                "candidate_count": 0,
                "selected_count": 0,
            },
        )
        item["actual_ms"] = actual.get(section, 0)
        item["clip_count"] = counts.get(section, 0)
        stats.append(item)

    if actual.get("nao_classificado", 0) > 0:
        stats.append(
            {
                "key": "nao_classificado",
                "label": STORY_LABELS["nao_classificado"],
                "budget_ms": 0,
                "estimated_ms": 0,
                "candidate_count": story.get("unclassified_candidates", 0),
                "selected_count": counts.get("nao_classificado", 0),
                "actual_ms": actual.get("nao_classificado", 0),
                "clip_count": counts.get("nao_classificado", 0),
            }
        )
    return stats


def _director_phase_summary(director, final_clips):
    if not isinstance(director, dict):
        return []
    totals = {}
    counts = {}
    for clip in final_clips:
        key = clip.get("director_phase") or "sem_fase"
        totals[key] = totals.get(key, 0) + int(clip.get("duration_ms", 0) or 0)
        counts[key] = counts.get(key, 0) + 1
    result = []
    for phase in director.get("phases", []) or []:
        key = phase.get("key")
        result.append(
            {
                "key": key,
                "label": phase.get("label"),
                "budget_ms": phase.get("budget_ms", 0),
                "actual_ms": totals.get(key, 0),
                "clip_count": counts.get(key, 0),
                "target_shot_ms": phase.get("target_shot_ms"),
                "reference_energy": phase.get("reference_energy"),
            }
        )
    if totals.get("chronology_fill"):
        result.append(
            {
                "key": "chronology_fill",
                "label": "Complemento cronológico",
                "budget_ms": 0,
                "actual_ms": totals["chronology_fill"],
                "clip_count": counts.get("chronology_fill", 0),
            }
        )
    return result


def _apply_source_audio_policy(clips, project):
    """Só deixa a trilha abaixar quando existe evidência real de fala."""
    has_music = bool(project.get("music_source_path"))
    for clip in clips:
        if not has_music:
            clip["source_audio_gain"] = 1.0
            clip["source_audio_role"] = "original"
            continue

        section = clip.get("story_section") or "nao_classificado"
        evidence = " ".join(
            str(item).lower() for item in (clip.get("semantic_evidence") or [])
        )
        has_speech_evidence = (
            "fala/transcrição" in evidence
            or "fala/transcricao" in evidence
            or section == "votos_falas"
        )
        if has_speech_evidence:
            clip["source_audio_gain"] = 1.0
            clip["source_audio_role"] = "dialogue"
        else:
            clip["source_audio_gain"] = 0.0
            clip["source_audio_role"] = "music_priority"


def _expand_selected_clips(selected, target_ms, director_applied):
    accumulated = sum(int(clip["duration_ms"]) for clip in selected)
    if accumulated >= target_ms:
        return accumulated

    remaining = target_ms - accumulated
    for clip in selected:
        available_extra = max(0, clip["source_duration_ms"] - clip["duration_ms"])
        if available_extra <= 0:
            continue

        if director_applied:
            target = int(clip.get("director_target_duration_ms", 0) or clip["duration_ms"])
            max_duration = min(
                clip["source_duration_ms"],
                max(clip["duration_ms"], int(target * 1.35)),
            )
            available_extra = min(
                available_extra,
                max(0, max_duration - clip["duration_ms"]),
            )
            if available_extra <= 0:
                continue

        extra = min(available_extra, remaining)
        source_start = clip["source_start_ms"]
        source_end = clip["source_end_ms"]
        wanted = clip["duration_ms"] + extra
        offset = max(0, int((clip["source_duration_ms"] - wanted) / 2))
        clip["start_ms"] = source_start + offset
        clip["end_ms"] = min(source_end, clip["start_ms"] + wanted)
        actual_extra = (clip["end_ms"] - clip["start_ms"]) - clip["duration_ms"]
        clip["duration_ms"] = clip["end_ms"] - clip["start_ms"]
        accumulated += max(0, actual_extra)
        remaining = max(0, target_ms - accumulated)
        if remaining <= 0:
            break
    return accumulated


def build_wedding_assembly_plan(
    project,
    library,
    batch_summary,
    reference_timing=None,
    reference_story_director=None,
):
    deliverable = project.get("deliverable")
    if not isinstance(deliverable, dict):
        deliverable = normalize_deliverable(
            "Casamento",
            project.get("deliverable_type"),
            project.get("target_duration_seconds"),
        )

    target_ms = max(1000, int(deliverable["target_seconds"]) * 1000)
    deliverable_type = deliverable.get("type", "trailer")
    base_clip_ms = _base_clip_ms(deliverable)
    max_clips = _max_clips(deliverable_type)
    timing_durations = _reference_durations(reference_timing)

    candidates = _valid_candidates(batch_summary, library)
    if not candidates:
        raise ProcessingError("Não há takes utilizáveis para montar o casamento.")

    selection_clip_ms = base_clip_ms
    if timing_durations:
        reference_average = max(
            500,
            int(round(sum(timing_durations) / len(timing_durations))),
        )
        selection_clip_ms = min(
            reference_average,
            max(base_clip_ms, int(base_clip_ms * 1.35)),
        )

    story = build_story_candidate_plan(
        candidates,
        library.get("assets", []),
        deliverable,
        target_ms=target_ms,
        base_clip_ms=selection_clip_ms,
        max_clips=max_clips,
    )

    director_applied = isinstance(reference_story_director, dict)
    if director_applied:
        selected_candidates = arrange_candidates_by_reference(
            candidates,
            library.get("assets", []),
            reference_story_director,
            max_clips,
        )
    elif any(item.get("visual_semantics") for item in candidates):
        selected_candidates = arrange_candidates_by_reference(
            candidates,
            library.get("assets", []),
            build_semantic_director(target_ms),
            max_clips,
        )
    else:
        selected_candidates = story.get("selected_candidates", [])[:max_clips]

    ending = EndingDirector().choose(candidates)
    closing_candidate = ending.get("candidate")
    closing_clip = None
    body_target_ms = target_ms
    if closing_candidate:
        selected_candidates = [
            item
            for item in selected_candidates
            if candidate_key(item) != candidate_key(closing_candidate)
        ]
        hold_ms = min(int(ending["hold_ms"]), target_ms)
        if isinstance(reference_timing, dict):
            phrases = reference_timing.get("music_phrases") or []
            if phrases:
                hold_ms = min(
                    hold_ms,
                    max(1500, int(phrases[-1].get("duration_ms", hold_ms))),
                )
        closing_clip = _window(closing_candidate, hold_ms)
        body_target_ms -= closing_clip["duration_ms"]

    selected = []
    for index, candidate in enumerate(selected_candidates):
        director_target = candidate.get("director_target_duration_ms")
        if director_target:
            wanted = int(director_target)
        else:
            wanted = _reference_wanted_ms(timing_durations, index, base_clip_ms)
        duration = int(candidate.get("duration_ms", 0) or 0)
        clip = _window(candidate, min(wanted, duration))
        if clip is not None:
            selected.append(clip)

    if not selected and not closing_clip:
        raise ProcessingError("O Wedding Story Builder não encontrou takes suficientes.")

    _expand_selected_clips(selected, body_target_ms, director_applied)

    timeline_ms = 0
    final_clips = []
    for clip in selected:
        if timeline_ms >= body_target_ms:
            break
        remaining = body_target_ms - timeline_ms
        if clip["duration_ms"] > remaining and remaining >= 500:
            clip = dict(clip)
            clip["duration_ms"] = remaining
            clip["end_ms"] = clip["start_ms"] + remaining
        elif remaining < 500:
            break
        clip["timeline_start_ms"] = timeline_ms
        timeline_ms += clip["duration_ms"]
        clip["timeline_end_ms"] = timeline_ms
        final_clips.append(clip)

    if closing_clip:
        closing_clip["timeline_start_ms"] = timeline_ms
        timeline_ms += closing_clip["duration_ms"]
        closing_clip["timeline_end_ms"] = timeline_ms
        final_clips.append(closing_clip)

    if not final_clips:
        raise ProcessingError("A seleção automática não encontrou takes suficientes.")

    _apply_source_audio_policy(final_clips, project)

    settings = project.get("review_settings") if isinstance(project.get("review_settings"), dict) else {}
    if settings.get("auto_zoom"):
        preset = get_style_preset(project.get("style", "Highlight"))
        zoom_scale = max(1.025, float(preset.zoom_scale))
        zoom_gap_ms = max(8000, min(int(preset.zoom_gap_ms), 24000))
        next_zoom_ms = 0
        for clip in final_clips:
            if clip["timeline_start_ms"] >= next_zoom_ms:
                clip["zoom_scale"] = zoom_scale
                next_zoom_ms = clip["timeline_start_ms"] + zoom_gap_ms

    motion_trimmed = [clip for clip in final_clips if clip.get("motion_gate_applied")]
    motion_trimmed_ms = sum(
        int(clip.get("motion_trim_total_ms", 0) or 0) for clip in motion_trimmed
    )
    continuous_motion = sum(
        1
        for clip in final_clips
        if clip.get("motion_classification") == "continuous_motion"
    )

    return {
        "schema_version": "0.7",
        "ending_director": {key: value for key, value in ending.items() if key != "candidate"},
        "visual_semantics_applied": any(clip.get("visual_semantics") for clip in final_clips),
        "profile": "Casamento",
        "style": project.get("style", "Highlight"),
        "deliverable": deliverable,
        "target_duration_ms": target_ms,
        "estimated_duration_ms": timeline_ms,
        "duration_shortfall_ms": max(0, target_ms - timeline_ms),
        "media_count": len({clip.get("asset_id") for clip in final_clips}),
        "clip_count": len(final_clips),
        "story_builder": story.get("engine", "wedding-story-builder-v1"),
        "story_builder_applied": True,
        "story_order": story.get("story_order", list(STORY_ORDER)),
        "story_sections": _story_section_summary(story, final_clips),
        "classified_candidates": story.get("classified_candidates", 0),
        "unclassified_candidates": story.get("unclassified_candidates", 0),
        "reference_story_director": (
            reference_story_director.get("engine") if director_applied else None
        ),
        "reference_story_director_applied": director_applied,
        "reference_story_phases": _director_phase_summary(
            reference_story_director,
            final_clips,
        ),
        "cold_open_applied": bool(
            director_applied
            and any(clip.get("director_phase") == "cold_open" for clip in final_clips)
        ),
        "motion_gate_engine": "motion-gate-v1",
        "motion_gate_schema": MOTION_GATE_SCHEMA,
        "motion_gate_applied": bool(motion_trimmed),
        "motion_trimmed_clip_count": len(motion_trimmed),
        "motion_trimmed_total_ms": motion_trimmed_ms,
        "continuous_motion_preserved_count": continuous_motion,
        "reference_timing_applied": bool(timing_durations),
        "reference_rhythm": (
            reference_timing.get("reference_rhythm")
            if isinstance(reference_timing, dict)
            else None
        ),
        "music_snap_enabled": bool(
            isinstance(reference_timing, dict)
            and reference_timing.get("music_snap_enabled")
        ),
        "reference_audio_used": False,
        "source_audio_policy": (
            "dialogue_only_with_music"
            if project.get("music_source_path")
            else "original_audio"
        ),
        "clips": final_clips,
    }


class WeddingAssemblyPipeline:
    def __init__(self, manager=None, tools=None, renderer=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.renderer = renderer or MultiSourceRenderer(self.tools)

    def run(
        self,
        project_dir,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(project_dir)
        library = load_media_library(root)
        if not library or len(library.get("assets", [])) <= 1:
            raise ProcessingError("A montagem multi-vídeo exige pelo menos duas mídias.")

        batch_path = root / BATCH_VISUAL_ANALYSIS_PATH
        batch_summary = None
        if batch_path.exists():
            try:
                batch_summary = read_json(batch_path)
            except (OSError, ValueError):
                batch_summary = None

        source_changed = any(
            Path(asset.get("path", "")).is_file()
            and asset_from_path(asset["path"])["fingerprint"] != asset.get("fingerprint")
            for asset in library.get("assets", [])
        )
        motion_cache_stale = (
            project.get("profile") == "Casamento"
            and isinstance(batch_summary, dict)
            and str(batch_summary.get("motion_gate_schema") or "") != MOTION_GATE_SCHEMA
        )
        if not isinstance(batch_summary, dict) or source_changed or motion_cache_stale:
            if motion_cache_stale and not source_changed:
                stage("Atualizando Motion Gate para localizar chicotes internos...")
            else:
                stage("Fazendo análise rápida da biblioteca antes da montagem...")
            batch_summary = BatchVisualAnalysisPipeline(
                manager=self.manager,
                tools=self.tools,
            ).run(
                root,
                cancel=cancel,
                stage=stage,
                progress=lambda value: progress(int(max(0, min(100, value)) * 0.28)),
            )

        check_cancelled(cancel)
        semantic_result = VisualSemanticsPipeline(manager=self.manager, tools=self.tools).run(
            root,
            _valid_candidates(batch_summary, library),
            cancel=cancel,
            stage=stage,
            progress=lambda value: progress(28 + int(value * 0.04)),
        )
        batch_summary = {
            **batch_summary,
            "best_take_candidates": semantic_result["candidates"],
        }
        reference_style = None
        reference_music = None
        music_analysis = None
        reference_video = project.get("reference_video_path")
        music_source = project.get("music_source_path")

        if reference_video:
            stage("Aprendendo estrutura, ritmo e energia do casamento de referência...")
            result = ReferenceAnalysisPipeline(
                manager=self.manager,
                tools=self.tools,
            ).run(
                root,
                reference_video,
                cancel=cancel,
                stage=stage,
                progress=lambda value: progress(32 + int(max(0, min(100, value)) * 0.06)),
            )
            reference_style = result.get("reference_style")
            reference_music = result.get("reference_music")

        if music_source:
            stage("Analisando a nova trilha e seus pontos fortes...")
            result = MusicAnalysisPipeline(
                manager=self.manager,
                tools=self.tools,
            ).run(
                root,
                music_source,
                cancel=cancel,
                stage=stage,
                progress=lambda value: progress(38 + int(max(0, min(100, value)) * 0.06)),
            )
            music_analysis = result.get("music_analysis")

        reference_timing = None
        reference_story_director = None
        if isinstance(reference_style, dict):
            deliverable = project.get("deliverable")
            if not isinstance(deliverable, dict):
                deliverable = normalize_deliverable(
                    "Casamento",
                    project.get("deliverable_type"),
                    project.get("target_duration_seconds"),
                )
            target_ms = int(deliverable["target_seconds"]) * 1000
            reference_story_director = build_reference_story_director(
                reference_style,
                reference_music,
                target_ms,
            )
            write_json(root / REFERENCE_STORY_DIRECTOR_PATH, reference_story_director)
            reference_timing = map_reference_timing(
                reference_style,
                target_ms,
                music_analysis=music_analysis,
            )
            write_json(root / REFERENCE_TIMING_PATH, reference_timing)

        check_cancelled(cancel)
        stage("Dirigindo a história pelo trailer de referência e aplicando Motion Gate...")
        progress(45)
        library = load_media_library(root) or library
        plan = build_wedding_assembly_plan(
            project,
            library,
            batch_summary,
            reference_timing=reference_timing,
            reference_story_director=reference_story_director,
        )
        write_json(root / WEDDING_ASSEMBLY_PLAN_PATH, plan)

        destination = root / WEDDING_ASSEMBLY_OUTPUT
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)

        stage(
            f"Montando {plan['clip_count']} takes de {plan['media_count']} mídias "
            "na estrutura aprendida da referência..."
        )
        rendered = self.renderer.render(
            plan["clips"],
            destination,
            target_aspect_ratio=project.get("aspect_ratio", "16:9"),
            audio_settings=(project.get("review_settings") or {}).get("audio_settings"),
            music_path=music_source,
            cancel=cancel,
            progress=lambda value: progress(48 + int(max(0, min(100, value)) * 0.52)),
            stage=stage,
        )

        # Renderer pode centralizar um take no trecho exato de votos. Regrava o
        # plano depois do render para Review/cache refletirem o que saiu no MP4.
        plan["slow_motion_count"] = int(
            getattr(self.renderer, "last_slow_motion_count", 0) or 0
        )
        plan["dialogue_focus_count"] = int(
            getattr(self.renderer, "last_dialogue_focus_count", 0) or 0
        )
        plan["dialogue_focus_text"] = getattr(
            self.renderer,
            "last_dialogue_text",
            None,
        )
        plan["dialogue_director_reason"] = getattr(
            self.renderer,
            "last_dialogue_director_reason",
            None,
        )
        write_json(root / WEDDING_ASSEMBLY_PLAN_PATH, plan)

        check_cancelled(cancel)
        duration_ms = int(plan["estimated_duration_ms"])
        edit_plan = build_edit_plan(
            duration_ms,
            "Casamento",
            project.get("style", "Highlight"),
            {"silences": []},
        )
        write_json(root / "decisions/edit_plan.json", edit_plan)

        relative_output = str(rendered.relative_to(root)).replace("\\", "/")
        self.manager.update_processing(
            root,
            "rendered",
            edit_plan_path="decisions/edit_plan.json",
            output_path=relative_output,
            review_source_path=relative_output,
            wedding_assembly_plan_path=WEDDING_ASSEMBLY_PLAN_PATH,
            wedding_assembly_clip_count=plan["clip_count"],
            wedding_assembly_media_count=plan["media_count"],
            wedding_assembly_duration_ms=duration_ms,
            wedding_story_builder=plan["story_builder"],
            wedding_story_sections=plan["story_sections"],
            wedding_source_audio_policy=plan["source_audio_policy"],
            wedding_motion_gate=plan.get("motion_gate_engine"),
            wedding_motion_gate_schema=plan.get("motion_gate_schema"),
            wedding_motion_trimmed_clip_count=plan.get("motion_trimmed_clip_count", 0),
            wedding_motion_trimmed_total_ms=plan.get("motion_trimmed_total_ms", 0),
            wedding_slow_motion_count=plan.get("slow_motion_count", 0),
            wedding_dialogue_focus_count=plan.get("dialogue_focus_count", 0),
            wedding_dialogue_focus_text=plan.get("dialogue_focus_text"),
            wedding_dialogue_director_reason=plan.get("dialogue_director_reason"),
            reference_story_director_path=(
                REFERENCE_STORY_DIRECTOR_PATH if reference_story_director else None
            ),
            reference_story_director_applied=plan.get(
                "reference_story_director_applied",
                False,
            ),
            reference_story_phases=plan.get("reference_story_phases", []),
            reference_audio_used=False,
            reference_timing_path=(REFERENCE_TIMING_PATH if reference_timing else None),
            reference_timing_applied=plan["reference_timing_applied"],
            music_snap_enabled=plan["music_snap_enabled"],
            edited_duration_ms=duration_ms,
            original_duration_ms=duration_ms,
            render_encoder=getattr(
                getattr(self.renderer, "last_encoder", None),
                "label",
                "Desconhecido",
            ),
        )

        progress(100)
        shortfall = int(plan.get("duration_shortfall_ms", 0) or 0)
        motion_count = int(plan.get("motion_trimmed_clip_count", 0) or 0)
        slow_count = int(plan.get("slow_motion_count", 0) or 0)
        voice_count = int(plan.get("dialogue_focus_count", 0) or 0)
        director_text = (
            " • Story Director ativo"
            if plan.get("reference_story_director_applied")
            else ""
        )
        emotion_text = ""
        if slow_count:
            emotion_text += f" • {slow_count} slow motion(s)"
        if voice_count:
            emotion_text += f" • {voice_count} momento(s) de voz"
        if shortfall > 1500:
            stage(
                f"História pronta com {plan['clip_count']} takes. "
                f"Motion Gate ajustou {motion_count} borda(s){director_text}{emotion_text}. "
                f"Faltaram {shortfall / 1000:.1f}s para a duração alvo."
            )
        else:
            stage(
                f"História pronta: {plan['clip_count']} takes, "
                f"{duration_ms / 1000:.1f}s{director_text}{emotion_text}."
            )
        return {
            "audio_path": None,
            "transcript": None,
            "silences": None,
            "errors": [],
            "edit_errors": [],
            "edit_plan": edit_plan,
            "output_path": relative_output,
            "reused_output": False,
            "render_encoder": getattr(
                getattr(self.renderer, "last_encoder", None),
                "label",
                "Desconhecido",
            ),
            "wedding_assembly": plan,
            "reference_timing": reference_timing,
            "reference_story_director": reference_story_director,
            "music_analysis": music_analysis,
            "review_settings": project.get("review_settings", {}),
        }
