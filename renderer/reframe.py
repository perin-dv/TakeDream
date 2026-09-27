from dataclasses import dataclass

from renderer.formats import (
    crop_dimensions,
    even,
)


@dataclass(frozen=True)
class FocusRegion:
    x: float = 0.5
    y: float = 0.5
    source: str = "center"

    def to_dict(self):
        return {
            "x": self.x,
            "y": self.y,
            "source": self.source,
        }


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def normalize_focus_region(value):
    if isinstance(value, FocusRegion):
        return value

    if not isinstance(value, dict):
        return FocusRegion()

    try:
        x = float(value.get("x", 0.5))
        y = float(value.get("y", 0.5))
    except (TypeError, ValueError):
        return FocusRegion()

    source = str(value.get("source") or "manual").strip() or "manual"

    return FocusRegion(
        x=_clamp(x, 0.0, 1.0),
        y=_clamp(y, 0.0, 1.0),
        source=source,
    )


def smart_crop_box(
    source_width,
    source_height,
    aspect_key,
    focus_region=None,
):
    source_width = int(source_width)
    source_height = int(source_height)

    crop_width, crop_height = crop_dimensions(
        source_width,
        source_height,
        aspect_key,
    )

    focus = normalize_focus_region(
        focus_region
    )

    max_x = max(0, source_width - crop_width)
    max_y = max(0, source_height - crop_height)

    center_x = focus.x * source_width
    center_y = focus.y * source_height

    crop_x = _clamp(
        center_x - crop_width / 2,
        0,
        max_x,
    )
    crop_y = _clamp(
        center_y - crop_height / 2,
        0,
        max_y,
    )

    crop_x = even(crop_x) if max_x else 0
    crop_y = even(crop_y) if max_y else 0

    crop_x = min(crop_x, max_x)
    crop_y = min(crop_y, max_y)

    return {
        "x": int(crop_x),
        "y": int(crop_y),
        "width": int(crop_width),
        "height": int(crop_height),
        "focus": focus.to_dict(),
    }


def zoom_crop_origin(
    scaled_width,
    scaled_height,
    output_width,
    output_height,
    focus_region=None,
):
    focus = normalize_focus_region(
        focus_region
    )

    max_x = max(0, int(scaled_width) - int(output_width))
    max_y = max(0, int(scaled_height) - int(output_height))

    x = _clamp(
        focus.x * scaled_width - output_width / 2,
        0,
        max_x,
    )
    y = _clamp(
        focus.y * scaled_height - output_height / 2,
        0,
        max_y,
    )

    return int(round(x)), int(round(y))
