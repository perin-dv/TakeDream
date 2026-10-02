import unicodedata
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EditRules:
    profile: str
    style: str
    minimum_silence_ms: int
    edge_padding_ms: int
    minimum_cut_ms: int
    protect_start_ms: int
    protect_end_ms: int
    automatic_silence_cuts: bool = True

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class StylePreset:
    name: str
    description: str
    icon: str
    accent: str
    captions_enabled: bool
    caption_style: str
    auto_zoom: bool
    zoom_gap_ms: int
    zoom_scale: float
    broll_gap_ms: int
    broll_enabled: bool = True
    zoom_enabled: bool = True

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    styles: tuple[str, ...]
    description: str
    orientation: str = "landscape"
    aspect_ratio: str = "16:9"


PROFILE_DEFINITIONS = (
    ProfileDefinition(
        "YouTube",
        (
            "Dinâmico",
            "Clean",
            "Premium",
            "Highlights",
            "Storytelling",
        ),
        "Vídeo falado para YouTube com opções de ritmo, retenção e acabamento.",
    ),
    ProfileDefinition(
        "Shorts / Reels / TikTok",
        (
            "Dinâmico",
            "Impacto",
            "Clean",
            "Highlights",
        ),
        "Conteúdo curto com presets mais rápidos e formatos verticais.",
        orientation="vertical",
        aspect_ratio="9:16",
    ),
    ProfileDefinition(
        "Podcast",
        (
            "Conversa",
            "Clean",
            "Premium",
        ),
        "Conversa longa, preservando respiração, naturalidade e clareza.",
    ),
    ProfileDefinition(
        "Gaming",
        (
            "Dinâmico",
            "Highlights",
            "Clean",
        ),
        "Gameplay com ritmo rápido, cortes e destaque de momentos.",
    ),
    ProfileDefinition(
        "Curso",
        (
            "Didático",
            "Clean",
            "Premium",
        ),
        "Aulas e tutoriais com cortes conservadores e leitura clara.",
    ),
    ProfileDefinition(
        "VSL",
        (
            "Conversão",
            "Dinâmico",
            "Clean",
        ),
        "Vídeo de vendas com ritmo firme e foco em retenção.",
    ),
    ProfileDefinition(
        "Institucional",
        (
            "Premium",
            "Clean",
            "Storytelling",
        ),
        "Vídeo corporativo com acabamento limpo e ritmo controlado.",
    ),
    ProfileDefinition(
        "Casamento",
        (
            "Highlight",
            "Cinematográfico",
            "Emocional",
        ),
        "Eventos com cortes por silêncio desativados e ritmo mais preservado.",
    ),
)


STYLE_PRESETS = (
    StylePreset(
        "Clean",
        "Limpo, natural e discreto",
        "clean",
        "#38BDF8",
        False,
        "Clean",
        False,
        16000,
        1.035,
        18000,
    ),
    StylePreset(
        "Dinâmico",
        "Ritmo acelerado e mais movimento",
        "dynamic",
        "#D946EF",
        True,
        "Dinâmica",
        True,
        8000,
        1.070,
        12000,
    ),
    StylePreset(
        "Premium",
        "Sutil, elegante e sofisticado",
        "premium",
        "#D4A54A",
        False,
        "Clean",
        True,
        18000,
        1.035,
        22000,
    ),
    StylePreset(
        "Highlights",
        "Cortes rápidos e momentos fortes",
        "highlights",
        "#A855F7",
        True,
        "Impacto",
        True,
        6500,
        1.090,
        10000,
    ),
    StylePreset(
        "Storytelling",
        "Ritmo narrativo com respiro",
        "star",
        "#8B5CF6",
        True,
        "Clean",
        True,
        13000,
        1.045,
        14000,
    ),
    StylePreset(
        "Impacto",
        "Máxima energia para conteúdo curto",
        "dynamic",
        "#F43F5E",
        True,
        "Impacto",
        True,
        5000,
        1.100,
        9000,
    ),
    StylePreset(
        "Conversa",
        "Preserva a fala e a naturalidade",
        "podcast",
        "#6366F1",
        False,
        "Clean",
        False,
        22000,
        1.030,
        30000,
    ),
    StylePreset(
        "Didático",
        "Clareza e ritmo confortável",
        "course",
        "#3B82F6",
        True,
        "Clean",
        False,
        18000,
        1.035,
        16000,
    ),
    StylePreset(
        "Conversão",
        "Ritmo firme com foco em retenção",
        "vsl",
        "#EC4899",
        True,
        "Impacto",
        True,
        7000,
        1.080,
        11000,
    ),
    StylePreset(
        "Highlight",
        "Resumo emocional preservando o evento",
        "highlights",
        "#C084FC",
        False,
        "Clean",
        False,
        24000,
        1.030,
        30000,
        broll_enabled=False,
        zoom_enabled=False,
    ),
    StylePreset(
        "Cinematográfico",
        "Mais respiro e menos intervenção automática",
        "star",
        "#E879F9",
        False,
        "Clean",
        False,
        30000,
        1.025,
        35000,
        broll_enabled=False,
        zoom_enabled=False,
    ),
    StylePreset(
        "Emocional",
        "Edição suave para momentos afetivos",
        "wedding",
        "#D99A4E",
        False,
        "Clean",
        False,
        28000,
        1.025,
        32000,
        broll_enabled=False,
        zoom_enabled=False,
    ),
)


def _normalize(value):
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )


def profile_names():
    return [profile.name for profile in PROFILE_DEFINITIONS]


def get_profile_definition(profile_name):
    normalized = _normalize(profile_name)

    for definition in PROFILE_DEFINITIONS:
        if _normalize(definition.name) == normalized:
            return definition

    raise ValueError(f"Perfil ainda não suportado: {profile_name}")


def styles_for_profile(profile_name):
    return list(get_profile_definition(profile_name).styles)


def get_style_preset(style_name):
    normalized = _normalize(style_name)

    for preset in STYLE_PRESETS:
        if _normalize(preset.name) == normalized:
            return preset

    raise ValueError(f"Estilo ainda não suportado: {style_name}")


_RULES = {
    ("youtube", "dinamico"): EditRules(
        "YouTube", "Dinâmico", 850, 140, 350, 250, 250
    ),
    ("youtube", "clean"): EditRules(
        "YouTube", "Clean", 1300, 220, 450, 350, 350
    ),
    ("youtube", "premium"): EditRules(
        "YouTube", "Premium", 1500, 260, 500, 400, 400
    ),
    ("youtube", "highlights"): EditRules(
        "YouTube", "Highlights", 700, 100, 280, 200, 200
    ),
    ("youtube", "storytelling"): EditRules(
        "YouTube", "Storytelling", 1150, 190, 420, 300, 300
    ),
    ("shorts / reels / tiktok", "dinamico"): EditRules(
        "Shorts / Reels / TikTok", "Dinâmico", 550, 90, 220, 180, 180
    ),
    ("shorts / reels / tiktok", "impacto"): EditRules(
        "Shorts / Reels / TikTok", "Impacto", 420, 70, 180, 140, 140
    ),
    ("shorts / reels / tiktok", "clean"): EditRules(
        "Shorts / Reels / TikTok", "Clean", 850, 140, 300, 220, 220
    ),
    ("shorts / reels / tiktok", "highlights"): EditRules(
        "Shorts / Reels / TikTok", "Highlights", 500, 80, 200, 150, 150
    ),
    ("podcast", "conversa"): EditRules(
        "Podcast", "Conversa", 1300, 220, 450, 350, 350
    ),
    ("podcast", "clean"): EditRules(
        "Podcast", "Clean", 1700, 280, 550, 450, 450
    ),
    ("podcast", "premium"): EditRules(
        "Podcast", "Premium", 1900, 300, 600, 500, 500
    ),
    ("gaming", "dinamico"): EditRules(
        "Gaming", "Dinâmico", 650, 100, 250, 180, 180
    ),
    ("gaming", "highlights"): EditRules(
        "Gaming", "Highlights", 800, 120, 300, 220, 220
    ),
    ("gaming", "clean"): EditRules(
        "Gaming", "Clean", 1100, 180, 350, 280, 280
    ),
    ("curso", "didatico"): EditRules(
        "Curso", "Didático", 1500, 240, 500, 400, 400
    ),
    ("curso", "clean"): EditRules(
        "Curso", "Clean", 1900, 300, 650, 500, 500
    ),
    ("curso", "premium"): EditRules(
        "Curso", "Premium", 2100, 340, 700, 550, 550
    ),
    ("vsl", "conversao"): EditRules(
        "VSL", "Conversão", 700, 110, 280, 220, 220
    ),
    ("vsl", "dinamico"): EditRules(
        "VSL", "Dinâmico", 600, 90, 240, 180, 180
    ),
    ("vsl", "clean"): EditRules(
        "VSL", "Clean", 1050, 170, 350, 280, 280
    ),
    ("institucional", "premium"): EditRules(
        "Institucional", "Premium", 1700, 280, 600, 500, 500
    ),
    ("institucional", "clean"): EditRules(
        "Institucional", "Clean", 2000, 320, 700, 550, 550
    ),
    ("institucional", "storytelling"): EditRules(
        "Institucional", "Storytelling", 1500, 240, 550, 450, 450
    ),
    ("casamento", "highlight"): EditRules(
        "Casamento",
        "Highlight",
        2500,
        350,
        900,
        800,
        800,
        automatic_silence_cuts=False,
    ),
    ("casamento", "cinematografico"): EditRules(
        "Casamento",
        "Cinematográfico",
        3000,
        400,
        1000,
        1000,
        1000,
        automatic_silence_cuts=False,
    ),
    ("casamento", "emocional"): EditRules(
        "Casamento",
        "Emocional",
        2800,
        380,
        950,
        900,
        900,
        automatic_silence_cuts=False,
    ),
}


def get_edit_rules(profile, style):
    key = (_normalize(profile), _normalize(style))

    try:
        return _RULES[key]
    except KeyError as error:
        raise ValueError(
            f"Combinação de perfil/estilo ainda não suportada: {profile} / {style}"
        ) from error
