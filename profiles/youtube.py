import unicodedata
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class YouTubeEditRules:
    profile: str
    style: str
    minimum_silence_ms: int
    edge_padding_ms: int
    minimum_cut_ms: int
    protect_start_ms: int
    protect_end_ms: int

    def to_dict(self):
        return asdict(self)


def _normalize(value):
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(character for character in text if not unicodedata.combining(character))


def get_youtube_rules(style):
    normalized = _normalize(style)

    if normalized == "dinamico":
        return YouTubeEditRules(
            profile="YouTube",
            style="Dinâmico",
            minimum_silence_ms=850,
            edge_padding_ms=140,
            minimum_cut_ms=350,
            protect_start_ms=250,
            protect_end_ms=250,
        )

    if normalized == "clean":
        return YouTubeEditRules(
            profile="YouTube",
            style="Clean",
            minimum_silence_ms=1300,
            edge_padding_ms=220,
            minimum_cut_ms=450,
            protect_start_ms=350,
            protect_end_ms=350,
        )

    raise ValueError(f"Estilo YouTube ainda não suportado: {style}")
