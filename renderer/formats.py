from dataclasses import dataclass


@dataclass(frozen=True)
class AspectRatio:
    key: str
    label: str
    width: int
    height: int

    @property
    def value(self):
        return self.width / self.height

    @property
    def orientation(self):
        if self.width > self.height:
            return "landscape"
        if self.width < self.height:
            return "vertical"
        return "square"


ASPECT_RATIOS = (
    AspectRatio("16:9", "16:9 • Horizontal", 16, 9),
    AspectRatio("9:16", "9:16 • Vertical", 9, 16),
    AspectRatio("1:1", "1:1 • Quadrado", 1, 1),
    AspectRatio("4:5", "4:5 • Retrato", 4, 5),
)


def aspect_ratio_keys():
    return [item.key for item in ASPECT_RATIOS]


def get_aspect_ratio(key):
    normalized = str(key).strip()

    for item in ASPECT_RATIOS:
        if item.key == normalized:
            return item

    raise ValueError(f"Formato de vídeo desconhecido: {key}")


def even(value):
    value = max(2, int(round(value)))
    return value if value % 2 == 0 else value - 1


def crop_dimensions(source_width, source_height, aspect_key):
    aspect = get_aspect_ratio(aspect_key)

    source_width = int(source_width)
    source_height = int(source_height)

    if source_width <= 0 or source_height <= 0:
        raise ValueError("Dimensões de origem inválidas.")

    source_ratio = source_width / source_height
    target_ratio = aspect.value

    if abs(source_ratio - target_ratio) < 0.002:
        return even(source_width), even(source_height)

    if source_ratio > target_ratio:
        crop_height = even(source_height)
        crop_width = even(crop_height * target_ratio)
    else:
        crop_width = even(source_width)
        crop_height = even(crop_width / target_ratio)

    return crop_width, crop_height


def target_dimensions(
    source_width,
    source_height,
    aspect_key,
    short_side=None,
):
    crop_width, crop_height = crop_dimensions(
        source_width,
        source_height,
        aspect_key,
    )

    if short_side is None:
        return crop_width, crop_height

    short_side = even(short_side)
    aspect = get_aspect_ratio(aspect_key)

    if aspect.width > aspect.height:
        height = short_side
        width = even(height * aspect.value)
    elif aspect.width < aspect.height:
        width = short_side
        height = even(width / aspect.value)
    else:
        width = short_side
        height = short_side

    return width, height


def closest_aspect_ratio(width, height):
    width = int(width)
    height = int(height)

    if width <= 0 or height <= 0:
        return "16:9"

    ratio = width / height
    return min(
        ASPECT_RATIOS,
        key=lambda item: abs(item.value - ratio),
    ).key
