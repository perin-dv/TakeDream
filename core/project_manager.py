import json
import re
from datetime import datetime, timezone
from pathlib import Path

from profiles import get_profile_definition
from renderer.formats import get_aspect_ratio

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

        profile_definition = get_profile_definition(profile)
        selected_aspect = (
            aspect_ratio
            or profile_definition.aspect_ratio
        )
        aspect_definition = get_aspect_ratio(
            selected_aspect
        )

        project_data = {
            "schema_version": "0.1",
            "name": name,
            "profile": profile,
            "style": style,
            "orientation": aspect_definition.orientation,
            "aspect_ratio": aspect_definition.key,
            "status": "created",
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

    def save_media_metadata(self, project_dir, metadata):
        project_dir = Path(project_dir).expanduser().resolve()
        analysis_dir = project_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        metadata_file = analysis_dir / "media_metadata.json"

        write_json(metadata_file, metadata)

        _, project_data = self.load_project(project_dir)
        if project_data.get("status") in ("created", "media_analyzed"):
            project_data["status"] = "media_analyzed"
        project_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        project_data["media_metadata"] = str(
            metadata_file.relative_to(project_dir)
        )

        self._write_project_file(project_dir, project_data)
        return metadata_file

    def load_media_metadata(self, project_dir):
        project_dir = Path(project_dir).expanduser().resolve()
        metadata_file = project_dir / "analysis" / "media_metadata.json"

        if not metadata_file.exists():
            return None

        try:
            with metadata_file.open("r", encoding="utf-8-sig") as file:
                return json.load(file)
        except (OSError, ValueError):
            return None

    def _write_project_file(self, project_dir, project_data):
        project_file = Path(project_dir) / "project.json"

        write_json(project_file, project_data)

    def update_processing(self, project_dir, status, **fields):
        _, project_data = self.load_project(project_dir)
        project_data.update(fields)
        project_data["status"] = status
        project_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_project_file(project_dir, project_data)
        return project_data

    def _create_unique_project_directory(self, project_name):
        folder_name = self._safe_folder_name(project_name) or "projeto"
        candidate = self.projects_root / folder_name
        counter = 2

        while candidate.exists():
            candidate = self.projects_root / f"{folder_name}-{counter}"
            counter += 1

        candidate.mkdir(parents=True)
        return candidate

    @staticmethod
    def _safe_folder_name(value):
        value = value.strip()
        value = re.sub(r'[<>:"/\\|?*]', "", value)
        value = re.sub(r"\s+", "-", value)
        return value.lower()
