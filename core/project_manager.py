import json
import re
from datetime import datetime, timezone
from pathlib import Path


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

    def create_project(self, name, source_video, profile, style):
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
            "logs",
        ):
            (project_dir / folder).mkdir(parents=True, exist_ok=True)

        project_data = {
            "schema_version": "0.1",
            "name": name,
            "profile": profile,
            "style": style,
            "status": "created",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "original_path": str(source_path),
                "filename": source_path.name,
                "extension": source_path.suffix.lower(),
            },
        }

        project_file = project_dir / "project.json"
        with project_file.open("w", encoding="utf-8") as file:
            json.dump(project_data, file, indent=2, ensure_ascii=False)

        return project_dir

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
