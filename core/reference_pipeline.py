from __future__ import annotations

import hashlib
from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.storage import read_json, write_json
from editor.reference_style import build_reference_style_profile
from media.ffmpeg_tools import FFmpegTools
from media.music_analyzer import MusicAnalyzer
from media.visual_analyzer import VisualAnalyzer


REFERENCE_STYLE_PATH = "analysis/reference_style.json"
REFERENCE_MUSIC_PATH = "analysis/reference_music.json"
REFERENCE_MANIFEST_PATH = "analysis/reference_manifest.json"


def _fingerprint(path):
    path = Path(path).expanduser().resolve()
    stat = path.stat()
    raw = f"{path}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class ReferenceAnalysisPipeline:
    """Extract editing rhythm + audio-energy structure from a reference video."""

    def __init__(self, manager=None, tools=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()

    def run(
        self,
        project_dir,
        reference_video,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
        force=False,
    ):
        root, project = self.manager.load_project(project_dir)
        reference = Path(reference_video).expanduser().resolve()
        if not reference.exists() or not reference.is_file():
            raise ProcessingError("O video de referencia nao foi encontrado.")

        fingerprint = _fingerprint(reference)
        manifest_path = root / REFERENCE_MANIFEST_PATH
        style_path = root / REFERENCE_STYLE_PATH
        music_path = root / REFERENCE_MUSIC_PATH

        if not force and manifest_path.exists() and style_path.exists():
            try:
                manifest = read_json(manifest_path)
                cached_style = read_json(style_path)
                cached_music = read_json(music_path) if music_path.exists() else None
            except (OSError, ValueError):
                manifest = None
                cached_style = None
                cached_music = None
            if (
                isinstance(manifest, dict)
                and manifest.get("fingerprint") == fingerprint
                and isinstance(cached_style, dict)
                and cached_style.get("engine") == "reference-rhythm-v2"
            ):
                progress(100)
                stage("Referencia ja analisada. Reutilizando DNA de edicao V2.")
                return {
                    "reference_style": cached_style,
                    "reference_music": cached_music,
                    "reused": True,
                }

        if not self.tools.ffmpeg_path:
            raise ProcessingError("FFmpeg nao encontrado para analisar a referencia.")

        stage("Lendo video de referencia...")
        progress(5)
        metadata = self.tools.probe(reference, cancel=cancel)
        duration_seconds = metadata.get("container", {}).get("duration_seconds")
        if not isinstance(duration_seconds, (int, float)) or duration_seconds <= 0:
            raise ProcessingError("A referencia nao possui duracao valida.")
        duration_ms = int(round(duration_seconds * 1000))

        check_cancelled(cancel)
        stage("Aprendendo ritmo, fases e padrao de cortes da referencia...")
        progress(18)
        visual = VisualAnalyzer(self.tools.ffmpeg_path)
        cut_times = visual.detect_scene_changes(
            reference,
            duration_ms,
            threshold=0.28,
            cancel=cancel,
        )
        style_profile = build_reference_style_profile(cut_times, duration_ms)
        style_profile["source_filename"] = reference.name
        style_profile["source_path"] = str(reference)

        check_cancelled(cancel)
        stage("Mapeando energia e pontos musicais da referencia...")
        progress(58)
        music_profile = None
        try:
            music_profile = MusicAnalyzer(self.tools.ffmpeg_path).analyze(
                reference,
                cancel=cancel,
                stage=stage,
                progress=lambda value: progress(58 + int(max(0, min(100, value)) * 0.35)),
            )
        except ProcessingError as error:
            music_profile = {
                "schema_version": "0.1",
                "engine": "local-music-energy-v1",
                "available": False,
                "error": str(error),
            }

        write_json(style_path, style_profile)
        write_json(music_path, music_profile)
        manifest = {
            "schema_version": "0.2",
            "path": str(reference),
            "filename": reference.name,
            "fingerprint": fingerprint,
            "size_bytes": reference.stat().st_size,
            "style_path": REFERENCE_STYLE_PATH,
            "music_path": REFERENCE_MUSIC_PATH,
            "reference_engine": style_profile.get("engine"),
        }
        write_json(manifest_path, manifest)

        current_status = project.get("status", "created")
        self.manager.update_processing(
            root,
            current_status,
            reference_video_path=str(reference),
            reference_manifest_path=REFERENCE_MANIFEST_PATH,
            reference_style_path=REFERENCE_STYLE_PATH,
            reference_music_path=REFERENCE_MUSIC_PATH,
            reference_fingerprint=fingerprint,
        )

        progress(100)
        stage("DNA V2 da referencia pronto para o Reference Story Director.")
        return {
            "reference_style": style_profile,
            "reference_music": music_profile,
            "reused": False,
        }
