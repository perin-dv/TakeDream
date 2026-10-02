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
                edited_start = source_to_edited_ms(
                    plan,
                    start,
                )
                edited_end = source_to_edited_ms(
                    plan,
                    end,
                )
                if edited_end > edited_start:
                    items.append(
                        {
                            "start_ms": edited_start,
                            "end_ms": edited_end,
                            "text": segment.get(
                                "text",
                                "",
                            ).strip(),
                            "is_phrase": True,
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

            edited_start = source_to_edited_ms(
                plan,
                start,
            )
            edited_end = source_to_edited_ms(
                plan,
                end,
            )

            if edited_end <= edited_start:
                continue

            items.append(
                {
                    "start_ms": edited_start,
                    "end_ms": edited_end,
                    "text": text,
                    "is_phrase": False,
                }
            )

    return items


def _chunk_limits(style, play_res_x, play_res_y):
    vertical = play_res_y > play_res_x * 1.15

    if style == "Impacto":
        return (3 if vertical else 4), 1650

    if style == "Dinâmica":
        return (4 if vertical else 5), 2100

    return (5 if vertical else 6), 2800


def _chunks(
    transcript,
    plan,
    *,
    style,
    play_res_x,
    play_res_y,
):
    words = _caption_words(
        transcript,
        plan,
    )
    max_words, max_duration = _chunk_limits(
        style,
        play_res_x,
        play_res_y,
    )

    chunks = []
    current = []

    for item in words:
        if item.get("is_phrase"):
            if current:
                chunks.append(current)
                current = []
            chunks.append([item])
            continue

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
                len(current) >= max_words
                or gap > 450
                or duration > max_duration
            ):
                chunks.append(current)
                current = []

        current.append(item)

    if current:
        chunks.append(current)

    return [
        {
            "start_ms": chunk[0]["start_ms"],
            "end_ms": chunk[-1]["end_ms"],
            "words": chunk,
        }
        for chunk in chunks
        if chunk[-1]["end_ms"] > chunk[0]["start_ms"]
    ]


def _font_metrics(style, play_res_x, play_res_y):
    vertical = play_res_y > play_res_x * 1.15

    if vertical:
        base = max(
            46,
            int(round(play_res_y * 0.041)),
        )
        margin_v = max(
            110,
            int(round(play_res_y * 0.105)),
        )
        margin_h = max(
            42,
            int(round(play_res_x * 0.06)),
        )
    else:
        base = max(
            34,
            int(round(play_res_y * 0.052)),
        )
        margin_v = max(
            36,
            int(round(play_res_y * 0.075)),
        )
        margin_h = max(
            40,
            int(round(play_res_x * 0.025)),
        )

    if style == "Impacto":
        base = int(round(base * 1.16))
    elif style == "Dinâmica":
        base = int(round(base * 1.06))

    return base, margin_h, margin_v


def _style_line(style, play_res_x, play_res_y):
    font_size, margin_h, margin_v = _font_metrics(
        style,
        play_res_x,
        play_res_y,
    )

    if style == "Dinâmica":
        return (
            "Style: Default,Segoe UI,"
            f"{font_size},"
            "&H0000D7FF,&H00FFFFFF,"
            "&H00111118,&H70000000,"
            "-1,0,0,0,100,100,0,0,"
            "1,4,1,2,"
            f"{margin_h},{margin_h},{margin_v},1"
        )

    if style == "Impacto":
        return (
            "Style: Default,Segoe UI,"
            f"{font_size},"
            "&H00FFFFFF,&H00FF66D9,"
            "&H00100018,&H90000000,"
            "-1,0,0,0,104,104,0.8,0,"
            "3,2,1,2,"
            f"{margin_h},{margin_h},{margin_v},1"
        )

    return (
        "Style: Default,Segoe UI,"
        f"{font_size},"
        "&H00FFFFFF,&H00D8D8D8,"
        "&H00101016,&H70000000,"
        "0,0,0,0,100,100,0,0,"
        "1,3,1,2,"
        f"{margin_h},{margin_h},{margin_v},1"
    )


def _karaoke_text(chunk, style):
    words = chunk["words"]

    if (
        style == "Clean"
        or len(words) == 1
        and words[0].get("is_phrase")
    ):
        text = " ".join(
            word["text"]
            for word in words
        )
        return _escape_text(text)

    pieces = []

    for word in words:
        duration_cs = max(
            1,
            int(round(
                (
                    word["end_ms"]
                    - word["start_ms"]
                )
                / 10
            )),
        )
        text = _escape_text(
            word["text"].upper()
            if style == "Impacto"
            else word["text"]
        )
        pieces.append(
            f"{{\\kf{duration_cs}}}{text}"
        )

    prefix = (
        r"{\fad(55,85)\blur0.25}"
        if style == "Impacto"
        else r"{\fad(70,90)}"
    )
    return prefix + " ".join(pieces)


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
        style=style,
        play_res_x=int(play_res_x),
        play_res_y=int(play_res_y),
    ):
        text = _karaoke_text(
            chunk,
            style,
        )

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
        "YCbCr Matrix: TV.709",
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
            int(play_res_x),
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
