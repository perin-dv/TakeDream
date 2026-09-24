import os
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WhisperConfig:
    model: str = "base"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str | None = None

    @classmethod
    def from_env(cls):
        return cls(
            model=os.getenv("TAKEDREAM_WHISPER_MODEL", "base").strip() or "base",
            device=os.getenv("TAKEDREAM_WHISPER_DEVICE", "cpu").strip() or "cpu",
            compute_type=os.getenv("TAKEDREAM_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8",
            language=os.getenv("TAKEDREAM_WHISPER_LANGUAGE", "").strip() or None,
        )


class Transcriber(Protocol):
    def transcribe(self, audio_path, *, cancel=None, stage, progress) -> dict: ...
