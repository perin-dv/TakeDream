from copy import deepcopy

from editor.edit_plan import validate_edit_plan


MIN_MANUAL_EDIT_MS = 80


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


def split_segment_at(plan, source_ms):
    validate_edit_plan(plan)
    source_ms = int(source_ms)

    if source_ms <= 0 or source_ms >= plan["source_duration_ms"]:
        raise ValueError("Posição inválida para divisão.")

    updated = deepcopy(plan)

    for index, segment in enumerate(updated["segments"]):
        start = segment["start_ms"]
        end = segment["end_ms"]

        if source_ms == start or source_ms == end:
            raise ValueError("Já existe uma divisão nesta posição.")

        if start < source_ms < end:
            if segment["action"] != "keep":
                raise ValueError(
                    "Não é possível dividir um trecho que já está removido."
                )

            if (
                source_ms - start < MIN_MANUAL_EDIT_MS
                or end - source_ms < MIN_MANUAL_EDIT_MS
            ):
                raise ValueError(
                    "A divisão está muito próxima da borda do trecho."
                )

            left = deepcopy(segment)
            right = deepcopy(segment)

            left["end_ms"] = source_ms
            right["start_ms"] = source_ms
            right["reason"] = "manual_split"

            updated["segments"][index:index + 1] = [left, right]
            return recompute_plan(updated), index + 1

    raise ValueError("Nenhum trecho foi encontrado nessa posição.")


def remove_segment(plan, segment_index):
    validate_edit_plan(plan)

    if type(segment_index) is not int:
        raise ValueError("Índice de segmento inválido.")

    if segment_index < 0 or segment_index >= len(plan["segments"]):
        raise ValueError("Segmento fora do plano.")

    updated = deepcopy(plan)
    segment = updated["segments"][segment_index]

    if segment["action"] != "keep":
        raise ValueError("O trecho selecionado já está removido.")

    segment["action"] = "remove"
    segment["reason"] = "manual_delete"

    return recompute_plan(updated)


def remove_range(plan, start_ms, end_ms):
    validate_edit_plan(plan)

    start_ms = max(0, int(start_ms))
    end_ms = min(int(end_ms), plan["source_duration_ms"])

    if end_ms <= start_ms:
        raise ValueError("O ponto OUT precisa estar depois do ponto IN.")

    if end_ms - start_ms < MIN_MANUAL_EDIT_MS:
        raise ValueError("O intervalo selecionado é curto demais.")

    updated_segments = []

    for original in plan["segments"]:
        segment = deepcopy(original)
        seg_start = segment["start_ms"]
        seg_end = segment["end_ms"]

        if seg_end <= start_ms or seg_start >= end_ms:
            updated_segments.append(segment)
            continue

        overlap_start = max(seg_start, start_ms)
        overlap_end = min(seg_end, end_ms)

        if seg_start < overlap_start:
            left = deepcopy(segment)
            left["end_ms"] = overlap_start
            updated_segments.append(left)

        middle = deepcopy(segment)
        middle["start_ms"] = overlap_start
        middle["end_ms"] = overlap_end

        if middle["action"] == "keep":
            middle["action"] = "remove"
            middle["reason"] = "manual_range"

        updated_segments.append(middle)

        if overlap_end < seg_end:
            right = deepcopy(segment)
            right["start_ms"] = overlap_end
            updated_segments.append(right)

    updated = deepcopy(plan)
    updated["segments"] = updated_segments
    return recompute_plan(updated)


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
