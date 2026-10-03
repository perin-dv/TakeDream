"""Shot-level semantic inference, resumable cache and project integration."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.semantic_signals import COUPLE, DETAILS, PREPARATION, BAD_ENDING, strongest
from core.storage import read_json, write_json
from media.ffmpeg_tools import FFmpegTools
from media.process import run_media
from media.semantic_vision import CLIPVisionModel, TAG_PROMPTS


VISUAL_SEMANTICS_PATH = "analysis/visual_semantics.json"
SCHEMA_VERSION = "0.2"
SAMPLING_VERSION = "three-safe-frames-v2"
SCORING_VERSION = "roles-composition-gate-v2"
COMPOSITION_BAD_TAGS = (
    "low_value_frame",
    "accidental_floor",
    "accidental_ceiling",
    "camera_reposition",
    "operator_transition",
)


def candidate_key(item):
    return (
        str(item.get("asset_id", "")),
        item.get("scene_id"),
        int(item.get("start_ms", 0)),
        int(item.get("end_ms", 0)),
    )


def _cache_key(item, identity):
    source = Path(item["path"]).resolve()
    stat = source.stat()
    payload = [
        str(source),
        stat.st_size,
        stat.st_mtime_ns,
        candidate_key(item),
        identity,
        SAMPLING_VERSION,
        SCORING_VERSION,
        TAG_PROMPTS,
        item.get("motion_classification"),
        item.get("motion_confidence"),
        item.get("motion_safe_start_ms"),
        item.get("motion_safe_end_ms"),
        item.get("sharpness_score"),
        item.get("quality_sampled"),
        item.get("score"),
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def extract_frames(item, directory, ffmpeg_path, *, cancel=None):
    start = max(
        int(item["start_ms"]),
        int(item.get("motion_safe_start_ms") or item["start_ms"]),
    )
    end = min(
        int(item["end_ms"]),
        int(item.get("motion_safe_end_ms") or item["end_ms"]),
    )
    if end <= start:
        raise ProcessingError("Trecho inválido para visão semântica.")

    paths, times = [], []
    # Três amostras reduzem muito a chance de um trecho de chão/teto/reposição
    # ficar escondido entre apenas dois frames sem multiplicar demais o custo CLIP.
    for index, fraction in enumerate((0.18, 0.50, 0.82)):
        check_cancelled(cancel)
        time_ms = min(end - 1, start + int((end - start) * fraction))
        destination = Path(directory) / f"frame-{index}.jpg"
        run_media(
            [
                str(ffmpeg_path),
                "-hide_banner",
                "-nostdin",
                "-v",
                "error",
                "-ss",
                f"{time_ms/1000:.3f}",
                "-i",
                str(item["path"]),
                "-frames:v",
                "1",
                "-vf",
                "scale=384:-2",
                "-q:v",
                "3",
                "-y",
                str(destination),
            ],
            cancel=cancel,
            timeout=60,
        )
        if not destination.exists():
            raise ProcessingError("Não foi possível extrair um frame representativo.")
        paths.append(destination)
        times.append(time_ms)
    return paths, times


def _safe_score_map(value):
    return {
        name: max(0.0, min(1.0, float((value or {}).get(name, 0.0) or 0.0)))
        for name in TAG_PROMPTS
    }


def _build_record(item, result, key):
    values = _safe_score_map(result.get("scores", {}))
    peaks = _safe_score_map(result.get("peak_scores", result.get("scores", {})))
    raw_scores = list(result.get("scores", {}).values()) + list(
        result.get("peak_scores", {}).values()
    )
    if not all(math.isfinite(float(value)) for value in raw_scores):
        raise ProcessingError("O modelo visual retornou scores inválidos.")

    motion = str(item.get("motion_classification") or "unknown")
    confidence = float(item.get("motion_confidence", 0) or 0)
    whip = max(
        values["whip_pan"],
        peaks["whip_pan"],
        confidence if "spike" in motion or "whip" in motion else 0,
    )
    shake = max(
        values["shaky_camera"],
        peaks["shaky_camera"],
        confidence if "unstable" in motion else 0,
    )
    blur = max(values["motion_blur"], peaks["motion_blur"])
    if item.get("quality_sampled") and item.get("sharpness_score") is not None:
        blur = max(blur, 1.0 - float(item["sharpness_score"]) / 100.0)

    composition_risk = max(peaks[name] for name in COMPOSITION_BAD_TAGS)
    background_score = max(0.0, min(1.0, float(result.get("background_score", 0) or 0)))
    # Background é sinal auxiliar; só pesa forte quando também não há assunto claro.
    composition_risk = max(composition_risk, max(0.0, background_score - 0.18))

    risk = max(shake, whip, blur, composition_risk)
    couple = strongest(values, COUPLE)
    symbol = strongest(
        values,
        ("ring_detail", "holding_hands", "ceremony_exit", "bouquet_detail"),
    )
    bad = strongest(values, BAD_ENDING)
    opening = max(
        strongest(values, DETAILS + PREPARATION + ("ceremony_wide",)),
        couple,
        values["strong_opening_candidate"],
    )
    roles = {
        "opening_score": max(0.0, opening * (1 - risk) - bad * 0.35),
        "highlight_score": max(
            couple,
            values["emotional_reaction"],
            values["kiss"],
        ) * (1 - risk),
        "closing_score": max(0.0, max(couple, symbol) * (1 - risk) - bad * 0.70),
        "hero_score": couple * (1 - risk),
    }
    return {
        "shot_id": f"{item.get('asset_id')}:{item.get('scene_id')}",
        "asset_id": item.get("asset_id"),
        "scene_id": item.get("scene_id"),
        "source_file": str(item["path"]),
        "start_ms": item["start_ms"],
        "end_ms": item["end_ms"],
        "cache_key": key,
        "tags": [
            {"name": name, "score": score}
            for name, score in sorted(values.items(), key=lambda pair: pair[1], reverse=True)
        ],
        "peak_tags": [
            {"name": name, "score": score}
            for name, score in sorted(peaks.items(), key=lambda pair: pair[1], reverse=True)
        ],
        "quality": {
            "shake_score": round(shake, 4),
            "motion_blur_score": round(blur, 4),
            "whip_score": round(whip, 4),
            "composition_risk_score": round(composition_risk, 4),
            "accidental_floor_score": round(peaks["accidental_floor"], 4),
            "accidental_ceiling_score": round(peaks["accidental_ceiling"], 4),
            "camera_reposition_score": round(peaks["camera_reposition"], 4),
            "operator_transition_score": round(peaks["operator_transition"], 4),
            "motion_gate_classification": motion,
        },
        "roles": {name: round(value, 4) for name, value in roles.items()},
        "embedding": result.get("embedding", []),
        "background_score": background_score,
        "resolved_revision": result.get("resolved_revision"),
    }


class VisualSemanticsPipeline:
    def __init__(self, manager=None, tools=None, model=None, frame_extractor=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.model = model or CLIPVisionModel()
        self.frame_extractor = frame_extractor or extract_frames

    def run(
        self,
        project_dir,
        candidates,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, _ = self.manager.load_project(project_dir)
        identity = self.model.identity
        path = root / VISUAL_SEMANTICS_PATH
        try:
            cached = read_json(path)
        except (OSError, ValueError):
            cached = {}
        if not isinstance(cached, dict):
            cached = {}
        existing = (
            {
                item.get("cache_key"): item
                for item in cached.get("shots", [])
                if isinstance(item, dict)
            }
            if cached.get("schema_version") == SCHEMA_VERSION
            and cached.get("model") == identity
            else {}
        )
        document = {
            "schema_version": SCHEMA_VERSION,
            "engine": "clip-shot-semantics-v2",
            "model": identity,
            "sampling": SAMPLING_VERSION,
            "score_interpretation": "relative prompt support; not calibrated probabilities",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "shots": [],
            "complete": False,
        }
        enriched, reused = [], 0
        for index, item in enumerate(candidates):
            check_cancelled(cancel)
            key = _cache_key(item, identity)
            record = existing.get(key)
            if record is not None and (
                not isinstance(record.get("tags"), list)
                or not isinstance(record.get("roles"), dict)
                or not isinstance((record.get("quality") or {}).get("composition_risk_score"), (int, float))
            ):
                record = None
            if record is None:
                stage(
                    f"Visão semântica {index+1}/{len(candidates)}: "
                    f"{Path(item['path']).name}"
                )
                with TemporaryDirectory(prefix="takedream-vision-") as temporary:
                    frames, times = self.frame_extractor(
                        item,
                        temporary,
                        self.tools.ffmpeg_path,
                        cancel=cancel,
                    )
                    result = self.model.analyze(frames, cancel=cancel)
                check_cancelled(cancel)
                record = _build_record(item, result, key)
                record["sample_times_ms"] = times
            else:
                reused += 1
            document["shots"].append(record)
            enriched.append(
                {
                    **item,
                    "visual_semantics": record,
                    "vision_tags": [
                        tag["name"]
                        for tag in record["tags"]
                        if tag["score"] >= 0.30
                    ],
                }
            )
            write_json(path, document)
            progress(int((index + 1) / max(1, len(candidates)) * 100))

        # Derived repetition evidence is recomputed for the current shot set.
        for index, record in enumerate(document["shots"]):
            check_cancelled(cancel)
            embedding = record.get("embedding") or []
            similarity = 0.0
            for previous in document["shots"][:index]:
                other = previous.get("embedding") or []
                if embedding and len(embedding) == len(other):
                    norm = math.sqrt(
                        sum(value * value for value in embedding)
                        * sum(value * value for value in other)
                    )
                    similarity = max(
                        similarity,
                        sum(a * b for a, b in zip(embedding, other)) / norm if norm else 0,
                    )
            record["tags"] = [
                tag for tag in record["tags"] if tag["name"] != "repeated_visual"
            ]
            record["tags"].append(
                {
                    "name": "repeated_visual",
                    "score": round(max(0.0, (similarity - 0.85) / 0.15), 4),
                }
            )
        document.update(
            complete=True,
            reused_from_cache=reused,
            analyzed_now=len(enriched) - reused,
        )
        write_json(path, document)

        # Reload status: analysis must not regress a rendered/reviewed/exported project.
        _, current = self.manager.load_project(root)
        self.manager.update_processing(
            root,
            current.get("status", "created"),
            visual_semantics_path=VISUAL_SEMANTICS_PATH,
            visual_semantics_model=identity,
            visual_semantics_shot_count=len(enriched),
        )
        stage(
            f"Visão semântica pronta: {len(enriched)} trechos, "
            f"{reused} reutilizados do cache."
        )
        progress(100)
        return {"analysis": document, "candidates": enriched}
