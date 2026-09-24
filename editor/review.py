from copy import deepcopy

from editor.edit_plan import validate_edit_plan


def recompute_plan(plan):
    plan = deepcopy(plan)
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


def restore_cut(plan, segment_index):
    validate_edit_plan(plan)

    if type(segment_index) is not int:
        raise ValueError("Índice de segmento inválido.")

    if segment_index < 0 or segment_index >= len(plan["segments"]):
        raise ValueError("Segmento fora do plano.")

    updated = deepcopy(plan)
    segment = updated["segments"][segment_index]

    if segment["action"] != "remove":
        raise ValueError("O segmento selecionado não é um corte removido.")

    segment["action"] = "keep"
    segment["reason"] = "restored_by_user"

    return recompute_plan(updated)


def edited_to_source_ms(plan, edited_ms):
    validate_edit_plan(plan)
    edited_ms = max(0, int(edited_ms))
    cursor = 0

    for segment in plan["segments"]:
        if segment["action"] != "keep":
            continue

        duration = segment["end_ms"] - segment["start_ms"]

        if edited_ms <= cursor + duration:
            offset = min(duration, max(0, edited_ms - cursor))
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
