from dataclasses import dataclass


@dataclass(frozen=True)
class DeliverablePreset:
    key: str
    label: str
    target_seconds: int
    minimum_seconds: int
    maximum_seconds: int
    description: str
    pacing: str
    voice_ratio: float
    average_shot_seconds: float
    preserve_long_form: bool = False


WEDDING_DELIVERABLES = {
    "teaser": DeliverablePreset(
        key="teaser",
        label="Teaser",
        target_seconds=60,
        minimum_seconds=30,
        maximum_seconds=90,
        description=(
            "Peça curta e emocional com os momentos mais fortes, "
            "ritmo mais intenso e pouca fala."
        ),
        pacing="rápido",
        voice_ratio=0.14,
        average_shot_seconds=1.5,
    ),
    "trailer": DeliverablePreset(
        key="trailer",
        label="Trailer / Highlight",
        target_seconds=210,
        minimum_seconds=150,
        maximum_seconds=300,
        description=(
            "Resumo narrativo de 3–5 minutos com votos, melhores imagens, "
            "crescimento musical e clímax."
        ),
        pacing="cinematográfico",
        voice_ratio=0.28,
        average_shot_seconds=2.6,
    ),
    "film": DeliverablePreset(
        key="film",
        label="Filme completo",
        target_seconds=1200,
        minimum_seconds=900,
        maximum_seconds=1800,
        description=(
            "Filme de 15–30 minutos com narrativa completa, falas mais longas, "
            "cerimônia, casal, recepção e festa."
        ),
        pacing="narrativo",
        voice_ratio=0.42,
        average_shot_seconds=4.8,
        preserve_long_form=True,
    ),
    "custom": DeliverablePreset(
        key="custom",
        label="Personalizado",
        target_seconds=180,
        minimum_seconds=30,
        maximum_seconds=3600,
        description="Duração definida manualmente para uma entrega específica.",
        pacing="adaptativo",
        voice_ratio=0.25,
        average_shot_seconds=2.8,
    ),
}


DEFAULT_DELIVERABLE_BY_PROFILE = {
    "Casamento": "trailer",
}


def deliverables_for_profile(profile):
    if profile == "Casamento":
        return tuple(WEDDING_DELIVERABLES.values())
    return ()


def get_deliverable_preset(profile, key=None):
    if profile != "Casamento":
        return None

    selected = key or DEFAULT_DELIVERABLE_BY_PROFILE["Casamento"]
    if selected not in WEDDING_DELIVERABLES:
        raise ValueError(f"Tipo de entrega de casamento inválido: {selected}")
    return WEDDING_DELIVERABLES[selected]


def normalize_deliverable(profile, key=None, target_seconds=None):
    preset = get_deliverable_preset(profile, key)
    if preset is None:
        return None

    if target_seconds is None:
        target = preset.target_seconds
    else:
        try:
            target = int(target_seconds)
        except (TypeError, ValueError) as error:
            raise ValueError("A duração alvo deve ser informada em segundos.") from error

        if target < preset.minimum_seconds or target > preset.maximum_seconds:
            raise ValueError(
                f"{preset.label}: duração deve ficar entre "
                f"{preset.minimum_seconds}s e {preset.maximum_seconds}s."
            )

    return {
        "type": preset.key,
        "label": preset.label,
        "target_seconds": target,
        "minimum_seconds": preset.minimum_seconds,
        "maximum_seconds": preset.maximum_seconds,
        "pacing": preset.pacing,
        "voice_ratio": preset.voice_ratio,
        "average_shot_seconds": preset.average_shot_seconds,
        "preserve_long_form": preset.preserve_long_form,
        "description": preset.description,
    }
