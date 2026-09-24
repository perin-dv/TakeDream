from copy import deepcopy

from editor.edit_plan import validate_edit_plan


MIN_MANUAL_RANGE_MS = 80


def _merge_adjacent_segments(segments):
    merged = []

    for segment in segments:
        item = dict(segment)

        if (
            merged
            and merged[-1]["action"] == item["action"]
            and merged[-1]["end_ms"] == item["start_ms"]
        ):
            previous = merged[-1]
            previous["end_ms"] = item["end_ms"]

            if previous.get("reason") != item.get("reason"):
                previous["reason"] = (
                    "manual_edit"
                    if item["action"] == "remove"
                    else "content"
                )
        else:
            merged.append(item)

    return merged


def recompute_plan(plan):
    plan = deepcopy(plan)
    plan["segments"] = _merge_adjacent_segments(plan["segments"])
    segments = plan["segments"]

    removed_duration = sum(
        segment["end_ms"] - segment["start_ms"]
        for segment in segments
        if segment["action"] == "remove"
    )
    cuts = sum(
        1 for segment in segments if segment["action"] == "remove"
    )

    plan["stats"] = {
        "cuts": cuts,
        "removed_duration_ms": removed_duration,
        "estimated_duration_ms": (
            plan["source_duration_ms"] - removed_duration
        ),
    }
    return validate_edit_plan(plan)


def apply_action_range(plan, start_ms, end_ms, action, reason):
    validate_edit_plan(plan)

    if action not in ("keep", "remove"):
        raise ValueError("Ação de timeline inválida.")

    try:
        start_ms = int(start_ms)
        end_ms = int(end_ms)
    except (TypeError, ValueError) as error:
        raise ValueError("Intervalo de timeline inválido.") from error

    duration = plan["source_duration_ms"]
    start_ms = max(0, min(start_ms, duration))
    end_ms = max(0, min(end_ms, duration))

    if end_ms - start_ms < MIN_MANUAL_RANGE_MS:
        raise ValueError(
            f"O intervalo precisa ter pelo menos {MIN_MANUAL_RANGE_MS} ms."
        )

    updated = deepcopy(plan)
    rebuilt = []

    for segment in updated["segments"]:
        segment_start = segment["start_ms"]
        segment_end = segment["end_ms"]

        if segment_end <= start_ms or segment_start >= end_ms:
            rebuilt.append(dict(segment))
            continue

        overlap_start = max(segment_start, start_ms)
        overlap_end = min(segment_end, end_ms)

        if segment_start < overlap_start:
            rebuilt.append(
                {
                    "start_ms": segment_start,
                    "end_ms": overlap_start,
                    "action": segment["action"],
                    "reason": segment["reason"],
                }
            )

        rebuilt.append(
            {
                "start_ms": overlap_start,
                "end_ms": overlap_end,
                "action": action,
                "reason": reason,
            }
        )

        if overlap_end < segment_end:
            rebuilt.append(
                {
                    "start_ms": overlap_end,
                    "end_ms": segment_end,
                    "action": segment["action"],
                    "reason": segment["reason"],
                }
            )

    updated["segments"] = rebuilt
    return recompute_plan(updated)


def add_manual_cut(plan, start_ms, end_ms):
    if start_ms > end_ms:
        start_ms, end_ms = end_ms, start_ms

    return apply_action_range(
        plan,
        start_ms,
        end_ms,
        "remove",
        "manual_cut",
    )


def restore_cut(plan, segment_index):
    validate_edit_plan(plan)

    if type(segment_index) is not int:
        raise ValueError("Índice de segmento inválido.")

    if segment_index < 0 or segment_index >= len(plan["segments"]):
        raise ValueError("Segmento fora do plano.")

    segment = plan["segments"][segment_index]

    if segment["action"] != "remove":
        raise ValueError("O segmento selecionado não é um corte removido.")

    return apply_action_range(
        plan,
        segment["start_ms"],
        segment["end_ms"],
        "keep",
        "restored_by_user",
    )


def adjust_cut(plan, segment_index, *, start_delta_ms=0, end_delta_ms=0):
    validate_edit_plan(plan)

    if type(segment_index) is not int:
        raise ValueError("Índice de segmento inválido.")

    if segment_index < 0 or segment_index >= len(plan["segments"]):
        raise ValueError("Segmento fora do plano.")

    segment = plan["segments"][segment_index]

    if segment["action"] != "remove":
        raise ValueError("Selecione um corte removido para ajustar.")

    duration = plan["source_duration_ms"]
    new_start = max(
        0,
        min(
            duration,
            segment["start_ms"] + int(start_delta_ms),
        ),
    )
    new_end = max(
        0,
        min(
            duration,
            segment["end_ms"] + int(end_delta_ms),
        ),
    )

    if new_end - new_start < MIN_MANUAL_RANGE_MS:
        raise ValueError(
            "O ajuste deixaria o corte pequeno demais ou invertido."
        )

    restored = apply_action_range(
        plan,
        segment["start_ms"],
        segment["end_ms"],
        "keep",
        "content",
    )

    return apply_action_range(
        restored,
        new_start,
        new_end,
        "remove",
        "manual_adjustment",
    )


def edited_to_source_ms(plan, edited_ms):
    validate_edit_plan(plan)
    edited_ms = max(0, int(edited_ms))
    cursor = 0

    for segment in plan["segments"]:
        if segment["action"] != "keep":
            continue

        duration = segment["end_ms"] - segment["start_ms"]

        if edited_ms < cursor + duration:
            offset = max(0, edited_ms - cursor)
            return segment["start_ms"] + offset

        cursor += duration

    return plan["source_duration_ms"]


def source_to_edited_ms(plan, source_ms):
    validate_edit_plan(plan)
    source_ms = max(0, min(int(source_ms), plan["source_duration_ms"]))
    cursor = 0

    for segment in plan["segments"]:
        duration = segment["end_ms"] - segment["start_ms"]

        if source_ms < segment["end_ms"]:
            if segment["action"] == "remove":
                return cursor
            return cursor + max(0, source_ms - segment["start_ms"])

        if segment["action"] == "keep":
            cursor += duration

    return plan["stats"]["estimated_duration_ms"]
