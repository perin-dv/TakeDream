from dataclasses import dataclass


@dataclass(frozen=True)
class ExportProfile:
    key: str
    label: str
    height: int | None
    crf: int
    audio_bitrate: str
    preset: str = "veryfast"


EXPORT_PROFILES = (
    ExportProfile(
        key="original",
        label="Original",
        height=None,
        crf=18,
        audio_bitrate="192k",
    ),
    ExportProfile(
        key="1080p",
        label="1080p",
        height=1080,
        crf=19,
        audio_bitrate="192k",
    ),
    ExportProfile(
        key="720p",
        label="720p",
        height=720,
        crf=20,
        audio_bitrate="160k",
    ),
    ExportProfile(
        key="480p",
        label="480p",
        height=480,
        crf=21,
        audio_bitrate="128k",
    ),
)


def get_export_profile(key):
    normalized = str(key).strip().lower()

    for profile in EXPORT_PROFILES:
        if profile.key == normalized:
            return profile

    raise ValueError(f"Perfil de exportação desconhecido: {key}")
