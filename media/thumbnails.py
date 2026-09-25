import json
import math
from pathlib import Path

from core.processing import ProcessingError
from media.process import run_media


THUMBNAIL_SCHEMA = "0.1"
DEFAULT_COUNT = 24


def _manifest_path(project_dir):
    return (
        Path(project_dir)
        / "cache"
        / "thumbnails"
        / "manifest.json"
    )


def load_thumbnail_manifest(project_dir):
    manifest = _manifest_path(project_dir)

    if not manifest.exists():
        return []

    try:
        data = json.loads(
            manifest.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return []

    if data.get("schema_version") != THUMBNAIL_SCHEMA:
        return []

    paths = []
    for relative in data.get("files", []):
        candidate = (
            Path(project_dir)
            / relative
        )

        if candidate.exists():
            paths.append(str(candidate))

    return paths


def generate_thumbnails(
    *,
    project_dir,
    source,
    ffmpeg_path,
    duration_seconds,
    count=DEFAULT_COUNT,
    cancel=None,
):
    project_dir = Path(project_dir)
    source = Path(source)

    existing = load_thumbnail_manifest(
        project_dir
    )
    if existing:
        return existing

    if not ffmpeg_path:
        raise ProcessingError(
            "FFmpeg não encontrado para gerar miniaturas."
        )

    if duration_seconds <= 0:
        raise ProcessingError(
            "Duração inválida para gerar miniaturas."
        )

    target_dir = (
        project_dir
        / "cache"
        / "thumbnails"
    )
    target_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for old in target_dir.glob("thumb_*.jpg"):
        old.unlink(missing_ok=True)

    interval = max(
        duration_seconds / max(1, int(count)),
        0.5,
    )

    pattern = target_dir / "thumb_%03d.jpg"

    run_media(
        [
            ffmpeg_path,
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            (
                f"fps=1/{interval:.6f},"
                "scale=180:-2:flags=lanczos"
            ),
            "-frames:v",
            str(int(count)),
            "-q:v",
            "4",
            "-y",
            str(pattern),
        ],
        cancel=cancel,
    )

    files = sorted(
        target_dir.glob("thumb_*.jpg")
    )

    if not files:
        raise ProcessingError(
            "O FFmpeg não gerou miniaturas."
        )

    relative_files = [
        str(
            file.relative_to(project_dir)
        ).replace("\\", "/")
        for file in files
    ]

    _manifest_path(project_dir).write_text(
        json.dumps(
            {
                "schema_version": (
                    THUMBNAIL_SCHEMA
                ),
                "count": len(files),
                "interval_seconds": round(
                    interval,
                    3,
                ),
                "files": relative_files,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return [str(file) for file in files]
