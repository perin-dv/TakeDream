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

    def __init__(self, projects_root=None):
        if projects_root is None:
            repository_root = Path(__file__).resolve().parents[1]
            projects_root = repository_root / "projects"

        self.projects_root = Path(projects_root)
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def create_project(
        self,
        name,
        source_video,
        profile,
        style,
        aspect_ratio=None,
        captions_enabled=None,
        auto_zoom=None,
        caption_style=None,
        export_quality="original",
    ):
        name = name.strip()

        if not name:
            raise ValueError("Informe um nome para o projeto.")

        source_path = Path(source_video).expanduser().resolve()

        if not source_path.exists():
            raise ValueError("O vídeo selecionado não existe.")

        if not source_path.is_file():
            raise ValueError("O caminho selecionado não é um arquivo.")

        if source_path.suffix.lower() not in self.ALLOWED_VIDEO_EXTENSIONS:
            raise ValueError(
                f"Formato de vídeo não suportado: {source_path.suffix}"
            )

        profile_definition = get_profile_definition(profile)
        get_edit_rules(profile, style)
        style_preset = get_style_preset(style)

        if captions_enabled is None:
            captions_enabled = (
                style_preset.captions_enabled
            )
        if auto_zoom is None:
            auto_zoom = style_preset.auto_zoom
        if caption_style is None:
            caption_style = (
                style_preset.caption_style
            )

        selected_aspect = (
            aspect_ratio
            or profile_definition.aspect_ratio
        )
        aspect_definition = get_aspect_ratio(
            selected_aspect
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

        project_data = {
            "schema_version": "0.1",
            "name": name,
            "profile": profile,
            "style": style,
            "orientation": aspect_definition.orientation,
            "aspect_ratio": aspect_definition.key,
            "status": "created",
            "focus_region": FocusRegion().to_dict(),
            "review_settings": {
                "aspect_ratio": aspect_definition.key,
                "captions_enabled": bool(captions_enabled),
                "caption_style": str(caption_style),
                "auto_zoom": bool(auto_zoom),
                "smart_reframe": True,
                "focus_region": FocusRegion().to_dict(),
                "audio_enhance": True,
                "audio_settings": dict(
                    DEFAULT_AUDIO_SETTINGS
                ),
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
        if (not isinstance(source, dict)
                or not isinstance(source.get("original_path"), str)
                or not source["original_path"].strip()):
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
                    "source_filename": data.get(
                        "source",
                        {},
                    ).get("filename", "—"),
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

    def save_media_metadata(self, project_dir, metadata):
        project_dir = Path(project_dir)
        analysis_dir = project_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        metadata_path = analysis_dir / "media_metadata.json"
        write_json(metadata_path, metadata)

        self.update_processing(
            project_dir,
            "media_analyzed",
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
