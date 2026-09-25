from pathlib import Path

from editor.edit_plan import validate_edit_plan
from editor.review import (
    segment_index_at,
    source_to_edited_ms,
)


CAPTION_STYLES = (
    "Clean",
    "Dinâmica",
    "Impacto",
)


def _ass_time(milliseconds):
    total_cs = max(
        0,
        int(round(milliseconds / 10)),
    )
    hours, remainder = divmod(
        total_cs,
        360000,
    )
    minutes, remainder = divmod(
        remainder,
        6000,
    )
    seconds, centiseconds = divmod(
        remainder,
        100,
    )
    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{seconds:02d}."
        f"{centiseconds:02d}"
    )


def _escape_text(text):
    return (
        str(text)
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
        .strip()
    )


def _kept(plan, source_ms):
    if source_ms >= plan["source_duration_ms"]:
        source_ms = plan["source_duration_ms"] - 1

    index = segment_index_at(
        plan,
        max(0, source_ms),
    )
    return (
        plan["segments"][index]["action"]
        == "keep"
    )


def _caption_words(transcript, plan):
    items = []

    for segment in transcript.get(
        "segments",
        [],
    ):
        words = segment.get("words") or []

        if not words:
            start = segment.get(
                "start_ms",
                0,
            )
            end = segment.get(
                "end_ms",
                start,
            )
            midpoint = int(
                (start + end) / 2
            )

            if (
                end > start
                and _kept(plan, midpoint)
            ):
                items.append(
                    {
                        "start_ms": start,
                        "end_ms": end,
                        "text": segment.get(
                            "text",
                            "",
                        ).strip(),
                    }
                )
            continue

        for word in words:
            start = word.get("start_ms")
            end = word.get("end_ms")

            if (
                type(start) is not int
                or type(end) is not int
                or end <= start
            ):
                continue

            midpoint = int(
                (start + end) / 2
            )

            if not _kept(plan, midpoint):
                continue

            text = str(
                word.get("word", "")
            ).strip()

            if not text:
                continue

            items.append(
                {
                    "start_ms": start,
                    "end_ms": end,
                    "text": text,
                }
            )

    return items


def _chunks(transcript, plan):
    words = _caption_words(
        transcript,
        plan,
    )

    chunks = []
    current = []

    for item in words:
        if current:
            gap = (
                item["start_ms"]
                - current[-1]["end_ms"]
            )
            duration = (
                item["end_ms"]
                - current[0]["start_ms"]
            )

            if (
                len(current) >= 5
                or gap > 500
                or duration > 2400
            ):
                chunks.append(current)
                current = []

        current.append(item)

    if current:
        chunks.append(current)

    output = []

    for chunk in chunks:
        source_start = chunk[0]["start_ms"]
        source_end = chunk[-1]["end_ms"]

        edited_start = source_to_edited_ms(
            plan,
            source_start,
        )
        edited_end = source_to_edited_ms(
            plan,
            source_end,
        )

        if edited_end <= edited_start:
            continue

        output.append(
            {
                "start_ms": edited_start,
                "end_ms": edited_end,
                "text": " ".join(
                    item["text"]
                    for item in chunk
                ),
            }
        )

    return output


def _style_line(style, play_res_y):
    font_size = max(
        34,
        int(round(play_res_y * 0.052)),
    )
    margin_v = max(
        36,
        int(round(play_res_y * 0.075)),
    )

    if style == "Dinâmica":
        return (
            "Style: Default,Arial,"
            f"{font_size},"
            "&H0000FFFF,&H0000FFFF,"
            "&H00000000,&H00000000,"
            "-1,0,0,0,100,100,0,0,"
            "1,4,1,2,"
            f"40,40,{margin_v},1"
        )

    if style == "Impacto":
        return (
            "Style: Default,Arial,"
            f"{font_size},"
            "&H00FFFFFF,&H00FFFFFF,"
            "&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,"
            "3,1,0,2,"
            f"48,48,{margin_v},1"
        )

    return (
        "Style: Default,Arial,"
        f"{font_size},"
        "&H00FFFFFF,&H00FFFFFF,"
        "&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,"
        "1,3,1,2,"
        f"40,40,{margin_v},1"
    )


def write_ass_captions(
    transcript,
    edit_plan,
    destination,
    *,
    style="Clean",
    play_res_x=1920,
    play_res_y=1080,
):
    validate_edit_plan(edit_plan)

    if style not in CAPTION_STYLES:
        raise ValueError(
            f"Estilo de legenda desconhecido: {style}"
        )

    destination = Path(destination)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    events = []

    for chunk in _chunks(
        transcript,
        edit_plan,
    ):
        text = _escape_text(
            chunk["text"]
        )

        if style == "Impacto":
            text = text.upper()

        events.append(
            "Dialogue: 0,"
            f"{_ass_time(chunk['start_ms'])},"
            f"{_ass_time(chunk['end_ms'])},"
            "Default,,0,0,0,,"
            f"{text}"
        )

    body = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(play_res_x)}",
        f"PlayResY: {int(play_res_y)}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, "
            "PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, "
            "MarginV, Encoding"
        ),
        _style_line(
            style,
            int(play_res_y),
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text"
        ),
        *events,
        "",
    ]

    destination.write_text(
        "\n".join(body),
        encoding="utf-8-sig",
    )

    return destination
