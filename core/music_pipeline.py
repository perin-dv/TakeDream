from __future__ import annotations

import hashlib
from pathlib import Path

from core.processing import ProcessingError
from core.project_manager import ProjectManager
from core.storage import read_json, write_json
from media.ffmpeg_tools import FFmpegTools
from media.music_analyzer import MusicAnalyzer


MUSIC_ANALYSIS_PATH = "analysis/music_analysis.json"
MUSIC_MANIFEST_PATH = "analysis/music_manifest.json"


def _fingerprint(path):
    path = Path(path).expanduser().resolve()
    stat = path.stat()
    raw = f"{path}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class MusicAnalysisPipeline:
    """Analyze a user-selected soundtrack once and cache its edit points."""

    def __init__(self, manager=None, tools=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()

    def run(
        self,
        project_dir,
        music_path,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
        force=False,
    ):
        root, project = self.manager.load_project(project_dir)
        music = Path(music_path).expanduser().resolve()
        if not music.exists() or not music.is_file():
            raise ProcessingError("A musica selecionada nao foi encontrada.")

        fingerprint = _fingerprint(music)
        analysis_path = root / MUSIC_ANALYSIS_PATH
        manifest_path = root / MUSIC_MANIFEST_PATH

        if not force and analysis_path.exists() and manifest_path.exists():
            try:
                manifest = read_json(manifest_path)
                analysis = read_json(analysis_path)
            except (OSError, ValueError):
                manifest = None
                analysis = None
            if (
                isinstance(manifest, dict)
                and manifest.get("fingerprint") == fingerprint
                and isinstance(analysis, dict)
            ):
                progress(100)
                stage("Musica ja analisada. Reutilizando mapa musical.")
                return {"music_analysis": analysis, "reused": True}

        analyzer = MusicAnalyzer(self.tools.ffmpeg_path)
        analysis = analyzer.analyze(
            music,
            cancel=cancel,
            stage=stage,
            progress=progress,
        )
        analysis["source_filename"] = music.name
        analysis["source_path"] = str(music)
        write_json(analysis_path, analysis)
        write_json(
            manifest_path,
            {
                "schema_version": "0.1",
                "path": str(music),
                "filename": music.name,
                "fingerprint": fingerprint,
                "size_bytes": music.stat().st_size,
                "analysis_path": MUSIC_ANALYSIS_PATH,
            },
        )

        current_status = project.get("status", "created")
        self.manager.update_processing(
            root,
            current_status,
            music_source_path=str(music),
            music_manifest_path=MUSIC_MANIFEST_PATH,
            music_analysis_path=MUSIC_ANALYSIS_PATH,
            music_fingerprint=fingerprint,
        )
        stage("Mapa musical pronto para sincronizar a montagem.")
        progress(100)
        return {"music_analysis": analysis, "reused": False}
