import hashlib
from datetime import datetime, timezone
from pathlib import Path

from core.storage import read_json, write_json


MEDIA_LIBRARY_PATH = "analysis/media_library.json"
SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
}


def _asset_fingerprint(path):
    path = Path(path).expanduser().resolve()
    stat = path.stat()
    raw = f"{path}|{stat.st_size}|{stat.st_mtime_ns}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _asset_id(path):
    path = Path(path).expanduser().resolve()
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]


def _category_from_path(path):
    text = " ".join(part.lower() for part in Path(path).parts)
    categories = (
        ("drone", ("drone", "aereo", "aéreo")),
        ("making_of_noiva", ("making noiva", "making_of_noiva", "noiva")),
        ("making_of_noivo", ("making noivo", "making_of_noivo", "noivo")),
        ("cerimonia", ("cerimonia", "cerimônia", "igreja", "votos")),
        ("casal", ("casal", "ensaio", "externa")),
        ("recepcao", ("recepcao", "recepção", "salao", "salão")),
        ("festa", ("festa", "dance", "balada")),
        ("decoracao", ("decoracao", "decoração", "detalhes", "decor")),
    )
    for category, needles in categories:
        if any(needle in text for needle in needles):
            return category
    return "nao_classificado"


def discover_media(inputs, *, recursive=True):
    discovered = []
    seen = set()

    for item in inputs or []:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            continue

        if path.is_file():
            candidates = [path]
        elif recursive:
            candidates = path.rglob("*")
        else:
            candidates = path.glob("*")

        for candidate in candidates:
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
                continue
            resolved = candidate.resolve()
            key = str(resolved).lower()
            if key in seen:
                continue
            seen.add(key)
            discovered.append(resolved)

    return sorted(discovered, key=lambda value: str(value).lower())


def asset_from_path(path):
    path = Path(path).expanduser().resolve()
    stat = path.stat()
    return {
        "id": _asset_id(path),
        "path": str(path),
        "filename": path.name,
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "fingerprint": _asset_fingerprint(path),
        "category_hint": _category_from_path(path),
        "analysis_status": "pending",
        "metadata_path": None,
        "visual_analysis_path": None,
        "scene_count": 0,
        "quality_average": None,
    }


def build_media_library(inputs, *, existing=None):
    existing = existing if isinstance(existing, dict) else {}
    existing_assets = {
        item.get("path"): item
        for item in existing.get("assets", [])
        if isinstance(item, dict) and item.get("path")
    }

    assets = []
    for path in discover_media(inputs):
        fresh = asset_from_path(path)
        previous = existing_assets.get(fresh["path"])
        if previous and previous.get("fingerprint") == fresh["fingerprint"]:
            merged = dict(fresh)
            merged.update(previous)
            merged["fingerprint"] = fresh["fingerprint"]
            merged["size_bytes"] = fresh["size_bytes"]
            merged["mtime_ns"] = fresh["mtime_ns"]
            assets.append(merged)
        else:
            assets.append(fresh)

    total_bytes = sum(item.get("size_bytes", 0) or 0 for item in assets)
    analyzed = sum(1 for item in assets if item.get("analysis_status") == "complete")

    return {
        "schema_version": "0.2",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "media_count": len(assets),
        "analyzed_count": analyzed,
        "total_bytes": total_bytes,
        "assets": assets,
    }


def load_media_library(project_dir):
    path = Path(project_dir) / MEDIA_LIBRARY_PATH
    if not path.exists():
        return None
    try:
        value = read_json(path)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def save_media_library(project_dir, library):
    path = Path(project_dir) / MEDIA_LIBRARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, library)
    return path


def merge_media_library(project_dir, inputs):
    current = load_media_library(project_dir) or {"assets": []}
    paths = [item.get("path") for item in current.get("assets", []) if item.get("path")]
    paths.extend(str(value) for value in inputs or [])
    library = build_media_library(paths, existing=current)
    save_media_library(project_dir, library)
    return library
