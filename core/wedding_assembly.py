from pathlib import Path

from core.batch_visual_analysis import (
    BATCH_VISUAL_ANALYSIS_PATH,
    BatchVisualAnalysisPipeline,
)
from core.deliverables import normalize_deliverable
from core.media_library import load_media_library
from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import read_json, write_json
from editor.edit_plan import build_edit_plan
from media.ffmpeg_tools import FFmpegTools
from profiles import get_style_preset
from renderer.multisource_renderer import MultiSourceRenderer


WEDDING_ASSEMBLY_PLAN_PATH = "decisions/wedding_assembly_plan.json"
WEDDING_ASSEMBLY_OUTPUT = "output/wedding_assembly_base.mp4"


_CATEGORY_ORDER = {
    "decoracao": 0,
    "drone": 1,
    "making_of_noiva": 2,
    "making_of_noivo": 3,
    "cerimonia": 4,
    "casal": 5,
    "recepcao": 6,
    "festa": 7,
    "nao_classificado": 8,
}


def _max_clips(deliverable_type):
    return {
        "teaser": 50,
        "trailer": 110,
        "film": 180,
        "custom": 140,
    }.get(deliverable_type, 110)


def _base_clip_ms(deliverable):
    average = float(deliverable.get("average_shot_seconds", 2.8) or 2.8)
    multiplier = 1.8 if deliverable.get("preserve_long_form") else 1.6
    return max(1200, int(round(average * multiplier * 1000)))


def _candidate_key(candidate):
    return (
        str(candidate.get("asset_id", "")),
        int(candidate.get("scene_id", -1) or -1),
        int(candidate.get("start_ms", 0) or 0),
        int(candidate.get("end_ms", 0) or 0),
    )


def _window(candidate, wanted_ms):
    start = int(candidate.get("start_ms", 0) or 0)
    end = int(candidate.get("end_ms", start) or start)
    available = max(0, end - start)
    wanted = max(0, min(int(wanted_ms), available))
    if wanted <= 0:
        return None

    if wanted < available:
        offset = int((available - wanted) / 2)
        start += offset
        end = start + wanted

    return {
        "asset_id": candidate.get("asset_id"),
        "filename": candidate.get("filename"),
        "path": candidate.get("path"),
        "category_hint": candidate.get("category_hint") or "nao_classificado",
        "scene_id": candidate.get("scene_id"),
        "source_start_ms": int(candidate.get("start_ms", 0) or 0),
        "source_end_ms": int(candidate.get("end_ms", 0) or 0),
        "start_ms": start,
        "end_ms": end,
        "duration_ms": end - start,
        "source_duration_ms": available,
        "score": float(candidate.get("score", 0) or 0),
        "quality_label": candidate.get("quality_label"),
        "audio_present": candidate.get("audio_present"),
        "zoom_scale": 1.0,
    }


def build_wedding_assembly_plan(project, library, batch_summary):
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

    raw_candidates = batch_summary.get("best_take_candidates", [])
    candidates = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        start = item.get("start_ms")
        end = item.get("end_ms")
        if not path or type(start) is not int or type(end) is not int or end - start < 500:
            continue
        candidates.append(dict(item))

    if not candidates:
        for asset in library.get("assets", []):
            seconds = asset.get("duration_seconds")
            if not isinstance(seconds, (int, float)) or seconds <= 0:
                continue
            candidates.append(
                {
                    "asset_id": asset.get("id"),
                    "filename": asset.get("filename"),
                    "path": asset.get("path"),
                    "category_hint": asset.get("category_hint"),
                    "audio_present": asset.get("audio_present"),
                    "scene_id": 0,
                    "start_ms": 0,
                    "end_ms": int(round(seconds * 1000)),
                    "duration_ms": int(round(seconds * 1000)),
                    "score": float(asset.get("quality_average") or 60.0),
                    "quality_label": "fallback",
                }
            )

    if not candidates:
        raise ProcessingError("Não há takes utilizáveis para montar o casamento.")

    asset_order = {
        asset.get("id"): index
        for index, asset in enumerate(library.get("assets", []))
    }

    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item.get("score", 0) or 0),
            int(item.get("duration_ms", 0) or 0),
        ),
        reverse=True,
    )

    selected = []
    selected_keys = set()
    accumulated = 0

    for asset in library.get("assets", []):
        asset_id = asset.get("id")
        best = next((item for item in ranked if item.get("asset_id") == asset_id), None)
        if best is None:
            continue
        clip = _window(best, min(base_clip_ms, int(best.get("duration_ms", 0) or 0)))
        if clip is None:
            continue
        selected.append(clip)
        selected_keys.add(_candidate_key(best))
        accumulated += clip["duration_ms"]
        if accumulated >= target_ms or len(selected) >= max_clips:
            break

    if accumulated < target_ms and len(selected) < max_clips:
        for candidate in ranked:
            key = _candidate_key(candidate)
            if key in selected_keys:
                continue
            duration = int(candidate.get("duration_ms", 0) or 0)
            clip = _window(candidate, min(base_clip_ms, duration))
            if clip is None:
                continue
            selected.append(clip)
            selected_keys.add(key)
            accumulated += clip["duration_ms"]
            if accumulated >= target_ms or len(selected) >= max_clips:
                break

    if accumulated < target_ms:
        remaining = target_ms - accumulated
        for clip in selected:
            available_extra = max(0, clip["source_duration_ms"] - clip["duration_ms"])
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

    selected.sort(
        key=lambda clip: (
            _CATEGORY_ORDER.get(clip.get("category_hint"), 8),
            asset_order.get(clip.get("asset_id"), 999999),
            clip.get("source_start_ms", 0),
        )
    )

    timeline_ms = 0
    final_clips = []
    for clip in selected:
        if timeline_ms >= target_ms:
            break
        remaining = target_ms - timeline_ms
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

    if not final_clips:
        raise ProcessingError("A seleção automática não encontrou takes suficientes.")

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

    return {
        "schema_version": "0.1",
        "profile": "Casamento",
        "style": project.get("style", "Highlight"),
        "deliverable": deliverable,
        "target_duration_ms": target_ms,
        "estimated_duration_ms": timeline_ms,
        "media_count": len({clip.get("asset_id") for clip in final_clips}),
        "clip_count": len(final_clips),
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

        if not isinstance(batch_summary, dict):
            stage("Fazendo análise rápida da biblioteca antes da montagem...")
            batch_summary = BatchVisualAnalysisPipeline(
                manager=self.manager,
                tools=self.tools,
            ).run(
                root,
                cancel=cancel,
                stage=stage,
                progress=lambda value: progress(int(max(0, min(100, value)) * 0.35)),
            )

        check_cancelled(cancel)
        stage("Escolhendo os melhores takes para a duração desejada...")
        progress(38)
        library = load_media_library(root) or library
        plan = build_wedding_assembly_plan(project, library, batch_summary)
        write_json(root / WEDDING_ASSEMBLY_PLAN_PATH, plan)

        destination = root / WEDDING_ASSEMBLY_OUTPUT
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)

        stage(f"Montando {plan['clip_count']} takes de {plan['media_count']} mídias...")
        rendered = self.renderer.render(
            plan["clips"],
            destination,
            target_aspect_ratio=project.get("aspect_ratio", "16:9"),
            audio_settings=(project.get("review_settings") or {}).get("audio_settings"),
            cancel=cancel,
            progress=lambda value: progress(40 + int(max(0, min(100, value)) * 0.60)),
            stage=stage,
        )

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
        original_media_source = project.get("original_media_source")
        if not isinstance(original_media_source, dict):
            original_media_source = dict(project.get("source") or {})

        review_settings = dict(project.get("review_settings") or {})
        # A transcrição antiga pertence apenas ao primeiro arquivo bruto. Para
        # não queimar legendas erradas sobre a montagem multi-source, elas ficam
        # aguardando uma nova transcrição da montagem.
        review_settings["captions_enabled"] = False

        assembly_source = {
            "original_path": relative_output,
            "filename": rendered.name,
            "extension": rendered.suffix.lower(),
            "generated_from_media_bin": True,
        }

        self.manager.update_processing(
            root,
            "rendered",
            source=assembly_source,
            original_media_source=original_media_source,
            edit_plan_path="decisions/edit_plan.json",
            output_path=relative_output,
            review_source_path=relative_output,
            wedding_assembly_plan_path=WEDDING_ASSEMBLY_PLAN_PATH,
            wedding_assembly_clip_count=plan["clip_count"],
            wedding_assembly_media_count=plan["media_count"],
            wedding_assembly_duration_ms=duration_ms,
            assembly_transcription_required=True,
            review_settings=review_settings,
            edited_duration_ms=duration_ms,
            original_duration_ms=duration_ms,
            render_encoder=getattr(
                getattr(self.renderer, "last_encoder", None),
                "label",
                "Desconhecido",
            ),
        )

        progress(100)
        stage(
            f"Rough cut de casamento pronto: {plan['clip_count']} takes, "
            f"{duration_ms / 1000:.1f}s."
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
            "review_settings": review_settings,
        }
