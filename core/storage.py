"""Atomic JSON persistence: interrupted writes never replace a valid result."""
import json
import os
import tempfile
from pathlib import Path


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path):
    try:
        with Path(path).open(encoding="utf-8-sig") as stream:
            return json.load(stream)
    except (OSError, ValueError) as error:
        raise ValueError(f"Não foi possível ler {Path(path).name}: {error}") from error
