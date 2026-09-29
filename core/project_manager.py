import json
import re
from datetime import datetime, timezone
from pathlib import Path

from profiles import (
    get_edit_rules,
    get_profile_definition,
    get_style_preset,
)
from renderer.audio import DEFAULT_AUDIO_SETTINGS
from renderer.formats import get_aspect_ratio
from renderer.reframe import FocusRegion

from core.deliverables import normalize_deliverable
from core.media_library import (
    MEDIA_LIBRARY_PATH,
    build_media_library,
    discover_media,
    load_media_library,
    merge_media_library,
    save_media_library,
)
from core.storage import write_json


class ProjectManager:
    ALLOWED_VIDEO_EXTENSIONS = {
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".m4v",
    }
    ALLOWED_MUSIC_EXTENSIONS = {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".mp4",
        ".mov",
        ".mkv",
    }

    def __init__(self, projects_root=None):
        if projects_root is None:
            repository_root = Path(__file__).resolve().parents[1]
            projects_root = repository_root / "projects"

        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def create_project(
        self,
        name,
        source_video=None,
        profile="YouTube",
        style="Clean",
        aspect_ratio=None,
        captions_enabled=None,
        auto_zoom=None,
        caption_style=None,
        export_quality="original",
        source_videos=None,
        deliverable_type=None,
        target_duration_seconds=None,
        reference_video=None,
        music_path=None,
    ):
        name = name.strip()

        if not name:
            raise ValueError("Informe um nome para o projeto.")

        requested_sources = []
        if source_video:
            requested_sources.append(source_video)
        if source_videos:
            requested_sources.extend(source_videos)

        if not requested_sources:
            raise ValueError("Selecione pelo menos um vídeo para o projeto.")

        for value in requested_sources:
            path = Path(value).expanduser()
            if not path.exists():
                raise ValueError(f"A mídia selecionada não existe: {path}")

        media_files = discover_media(requested_sources)
        if not media_files:
            raise ValueError("Nenhum vídeo compatível foi encontrado nas mídias selecionadas.")

        primary_candidates = discover_media([source_video]) if source_video else []
        source_path = primary_candidates[0] if primary_candidates else media_files[0]

        profile_definition = get_profile_definition(profile)
        get_edit_rules(profile, style)
        style_preset = get_style_preset(style)

        if captions_enabled is None:
            captions_enabled = style_preset.captions_enabled
        if auto_zoom is None:
            auto_zoom = style_preset.auto_zoom
        if caption_style is None:
            caption_style = style_preset.caption_style

        selected_aspect = aspect_ratio or profile_definition.aspect_ratio
        aspect_definition = get_aspect_ratio(selected_aspect)
        deliverable = normalize_deliverable(
            profile,
            deliverable_type,
            target_duration_seconds,
        )

        reference_path = None
        music_source = None

        if reference_video:
            reference_path = Path(reference_video).expanduser().resolve()
            if not reference_path.exists() or not reference_path.is_file():
                raise ValueError("O vídeo de referência selecionado não existe.")
            if reference_path.suffix.lower() not in self.ALLOWED_VIDEO_EXTENSIONS:
                raise ValueError("O arquivo de referência não é um vídeo compatível.")

        if music_path:
            music_source = Path(music_path).expanduser().resolve()
            if not music_source.exists() or not music_source.is_file():
                raise ValueError("A música selecionada não existe.")
            if music_source.suffix.lower() not in self.ALLOWED_MUSIC_EXTENSIONS:
                raise ValueError("O arquivo de música não é compatível.")

        if profile != "Casamento" and (reference_path or music_source):
            raise ValueError(
                "Vídeo de referência e música guiada estão disponíveis no perfil Casamento."
            )

        project_dir = self._create_unique_project_directory(name)

        for folder in (
            "source",
            "audio",
            "transcription",
            "analysis",
            "decisions",
            "cache",
            "output",
            "exports",
            "logs",
        ):
            (project_dir / folder).mkdir(parents=True, exist_ok=True)

        library = build_media_library(media_files)
        save_media_library(project_dir, library)

        wedding_setup = None
        if profile == "Casamento":
            wedding_setup = {
                "deliverable_type": deliverable.get("type") if deliverable else "trailer",
                "target_duration_seconds": (
                    deliverable.get("target_seconds") if deliverable else 210
                ),
                "reference_video_path": str(reference_path) if reference_path else None,
                "music_source_path": str(music_source) if music_source else None,
                "reference_enabled": bool(reference_path),
                "music_enabled": bool(music_source),
            }

        project_data = {
            "schema_version": "0.2",
            "name": name,
            "profile": profile,
            "style": style,
            "orientation": aspect_definition.orientation,
            "aspect_ratio": aspect_definition.key,
            "status": "created",
            "focus_region": FocusRegion().to_dict(),
            "media_library_path": MEDIA_LIBRARY_PATH,
            "media_count": library["media_count"],
            "deliverable": deliverable,
            "deliverable_type": deliverable.get("type") if deliverable else None,
            "target_duration_seconds": (
                deliverable.get("target_seconds") if deliverable else None
            ),
            "wedding_setup": wedding_setup,
            "reference_video_path": str(reference_path) if reference_path else None,
            "music_source_path": str(music_source) if music_source else None,
            "review_settings": {
                "aspect_ratio": aspect_definition.key,
                "captions_enabled": bool(captions_enabled),
                "caption_style": str(caption_style),
                "auto_zoom": bool(auto_zoom),
                "smart_reframe": True,
                "focus_region": FocusRegion().to_dict(),
                "audio_enhance": True,
                "audio_settings": dict(DEFAULT_AUDIO_SETTINGS),
            },
            "preferred_export_profile": str(export_quality),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "original_path": str(source_path),
                "filename": source_path.name,
                "extension": source_path.suffix.lower(),
            },
        }

        self._write_project_file(project_dir, project_data)
        return project_dir

    def load_project(self, project_path):
        path = Path(project_path).expanduser().resolve()

        if path.is_dir():
            project_file = path / "project.json"
        else:
            project_file = path
            path = project_file.parent

        if project_file.name.lower() != "project.json":
            raise ValueError("Selecione um arquivo project.json do TakeDream.")

        if not project_file.exists():
            raise ValueError("O project.json selecionado não existe.")

        try:
            with project_file.open("r", encoding="utf-8-sig") as file:
                project_data = json.load(file)
        except (OSError, ValueError) as error:
            raise ValueError(
                f"Não foi possível abrir o projeto: {error}"
            ) from error

        if not isinstance(project_data, dict):
            raise ValueError("O project.json possui formato inválido.")

        if not isinstance(project_data.get("name"), str) or not project_data["name"].strip():
            raise ValueError("O project.json não possui nome de projeto.")

        source = project_data.get("source", {})
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("original_path"), str)
            or not source["original_path"].strip()
        ):
            raise ValueError("O project.json não possui vídeo de origem.")

        return path, project_data

    def list_projects(self):
        projects = []

        if not self.projects_root.exists():
            return projects

        for project_file in self.projects_root.glob("*/project.json"):
            try:
                project_dir, data = self.load_project(project_file)
            except ValueError:
                continue

            projects.append(
                {
                    "project_dir": project_dir,
                    "name": data.get("name", project_dir.name),
                    "profile": data.get("profile", "—"),
                    "style": data.get("style", "—"),
                    "aspect_ratio": data.get("aspect_ratio", "16:9"),
                    "status": data.get("status", "created"),
                    "updated_at": data.get("updated_at", ""),
                    "created_at": data.get("created_at", ""),
                    "source_filename": data.get("source", {}).get("filename", "—"),
                    "media_count": int(data.get("media_count", 1) or 1),
                    "deliverable_type": data.get("deliverable_type"),
                    "target_duration_seconds": data.get("target_duration_seconds"),
                    "output_path": data.get("output_path"),
                }
            )

        projects.sort(
            key=lambda item: (
                item.get("updated_at")
                or item.get("created_at")
                or ""
            ),
            reverse=True,
        )
        return projects

    def list_exports(self):
        exports = []

        for project in self.list_projects():
            export_dir = project["project_dir"] / "exports"

            if not export_dir.exists():
                continue

            for file in sorted(
                export_dir.glob("*.mp4"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            ):
                try:
                    stat = file.stat()
                except OSError:
                    continue

                exports.append(
                    {
                        "path": file,
                        "project_name": project["name"],
                        "filename": file.name,
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                    }
                )

        exports.sort(
            key=lambda item: item["modified_at"],
            reverse=True,
        )
        return exports

    def load_media_library(self, project_dir):
        return load_media_library(project_dir)

    def add_media_sources(self, project_dir, sources):
        root, project_data = self.load_project(project_dir)
        library = merge_media_library(root, sources)
        current_status = project_data.get("status", "created")
        self.update_processing(
            root,
            current_status,
            media_library_path=MEDIA_LIBRARY_PATH,
            media_count=library.get("media_count", 0),
        )
        return library

    def save_media_metadata(self, project_dir, metadata):
        project_dir = Path(project_dir)
        analysis_dir = project_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = analysis_dir / "media_metadata.json"
        write_json(metadata_path, metadata)

        _, project_data = self.load_project(project_dir)
        current_status = project_data.get("status", "created")
        next_status = (
            "media_analyzed"
            if current_status in {"created", "media_analyzed"}
            else current_status
        )

        self.update_processing(
            project_dir,
            next_status,
            media_metadata_path="analysis/media_metadata.json",
        )

    def load_media_metadata(self, project_dir):
        metadata_path = Path(project_dir) / "analysis" / "media_metadata.json"

        if not metadata_path.exists():
            return None

        try:
            with metadata_path.open("r", encoding="utf-8-sig") as file:
                return json.load(file)
        except (OSError, ValueError):
            return None

    def update_processing(self, project_dir, status, **fields):
        project_dir = Path(project_dir)
        project_file = project_dir / "project.json"

        with project_file.open("r", encoding="utf-8-sig") as file:
            project_data = json.load(file)

        project_data["status"] = status
        project_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        project_data.update(fields)

        self._write_project_file(project_dir, project_data)

    def _create_unique_project_directory(self, name):
        slug = self._slugify(name)
        candidate = self.projects_root / slug
        counter = 2

        while candidate.exists():
            candidate = self.projects_root / f"{slug}-{counter}"
            counter += 1

        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    @staticmethod
    def _slugify(value):
        value = value.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")
        return value or "projeto"

    @staticmethod
    def _write_project_file(project_dir, project_data):
        project_file = Path(project_dir) / "project.json"
        write_json(project_file, project_data)
