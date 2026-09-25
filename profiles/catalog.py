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
class ProfileDefinition:
    name: str
    styles: tuple[str, ...]
    description: str
    orientation: str = "landscape"


PROFILE_DEFINITIONS = (
    ProfileDefinition(
        "YouTube",
        ("Dinâmico", "Clean"),
        "Vídeo falado para YouTube, com cortes de pausas e ritmo ajustável.",
    ),
    ProfileDefinition(
        "Shorts / Reels / TikTok",
        ("Dinâmico", "Clean"),
        "Conteúdo curto e acelerado. Estrutura pronta para reframing vertical.",
        orientation="vertical",
    ),
    ProfileDefinition(
        "Podcast",
        ("Conversa", "Clean"),
        "Conversa longa, preservando respiração e naturalidade.",
    ),
    ProfileDefinition(
        "Gaming",
        ("Dinâmico", "Highlights"),
        "Gameplay com ritmo mais rápido e preparação para highlights.",
    ),
    ProfileDefinition(
        "Curso",
        ("Didático", "Clean"),
        "Aulas e tutoriais com cortes mais conservadores.",
    ),
    ProfileDefinition(
        "VSL",
        ("Conversão", "Clean"),
        "Vídeo de vendas com ritmo firme e foco futuro em retenção.",
    ),
    ProfileDefinition(
        "Institucional",
        ("Premium", "Clean"),
        "Vídeo corporativo com ritmo conservador e acabamento limpo.",
    ),
    ProfileDefinition(
        "Casamento",
        ("Highlight", "Cinematográfico"),
        "Estrutura para eventos e multicâmera. Cortes por silêncio ficam desativados.",
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


_RULES = {
    ("youtube", "dinamico"): EditRules(
        "YouTube", "Dinâmico", 850, 140, 350, 250, 250
    ),
    ("youtube", "clean"): EditRules(
        "YouTube", "Clean", 1300, 220, 450, 350, 350
    ),
    ("shorts / reels / tiktok", "dinamico"): EditRules(
        "Shorts / Reels / TikTok", "Dinâmico", 550, 90, 220, 180, 180
    ),
    ("shorts / reels / tiktok", "clean"): EditRules(
        "Shorts / Reels / TikTok", "Clean", 850, 140, 300, 220, 220
    ),
    ("podcast", "conversa"): EditRules(
        "Podcast", "Conversa", 1300, 220, 450, 350, 350
    ),
    ("podcast", "clean"): EditRules(
        "Podcast", "Clean", 1700, 280, 550, 450, 450
    ),
    ("gaming", "dinamico"): EditRules(
        "Gaming", "Dinâmico", 650, 100, 250, 180, 180
    ),
    ("gaming", "highlights"): EditRules(
        "Gaming", "Highlights", 800, 120, 300, 220, 220
    ),
    ("curso", "didatico"): EditRules(
        "Curso", "Didático", 1500, 240, 500, 400, 400
    ),
    ("curso", "clean"): EditRules(
        "Curso", "Clean", 1900, 300, 650, 500, 500
    ),
    ("vsl", "conversao"): EditRules(
        "VSL", "Conversão", 700, 110, 280, 220, 220
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
}


def get_edit_rules(profile, style):
    key = (_normalize(profile), _normalize(style))

    try:
        return _RULES[key]
    except KeyError as error:
        raise ValueError(
            f"Combinação de perfil/estilo ainda não suportada: {profile} / {style}"
        ) from error
