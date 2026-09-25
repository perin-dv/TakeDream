from copy import deepcopy

from editor.edit_plan import validate_edit_plan


MIN_SEGMENT_MS = 50


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


def _validate_index(plan, segment_index):
    validate_edit_plan(plan)

    if type(segment_index) is not int:
        raise ValueError("Índice de segmento inválido.")

    if segment_index < 0 or segment_index >= len(plan["segments"]):
        raise ValueError("Segmento fora do plano.")


def segment_index_at(plan, source_ms):
    validate_edit_plan(plan)
    source_ms = max(
        0,
        min(int(source_ms), plan["source_duration_ms"] - 1),
    )

    for index, segment in enumerate(plan["segments"]):
        if segment["start_ms"] <= source_ms < segment["end_ms"]:
            return index

    return len(plan["segments"]) - 1


def split_at(plan, source_ms):
    validate_edit_plan(plan)
    source_ms = int(source_ms)

    if source_ms <= 0 or source_ms >= plan["source_duration_ms"]:
        raise ValueError("A divisão precisa estar dentro do vídeo.")

    index = segment_index_at(plan, source_ms)
    segment = plan["segments"][index]

    if source_ms in (segment["start_ms"], segment["end_ms"]):
        return deepcopy(plan)

    if (
        source_ms - segment["start_ms"] < MIN_SEGMENT_MS
        or segment["end_ms"] - source_ms < MIN_SEGMENT_MS
    ):
        raise ValueError(
            "A divisão precisa deixar pelo menos 50 ms em cada lado."
        )

    updated = deepcopy(plan)
    original = updated["segments"][index]

    left = {
        **original,
        "end_ms": source_ms,
        "reason": (
            "manual_split"
            if original["action"] == "keep"
            else original["reason"]
        ),
    }
    right = {
        **original,
        "start_ms": source_ms,
        "reason": (
            "manual_split"
            if original["action"] == "keep"
            else original["reason"]
        ),
    }

    updated["segments"][index:index + 1] = [left, right]
    return recompute_plan(updated)


def set_segment_action(plan, segment_index, action, reason):
    _validate_index(plan, segment_index)

    if action not in ("keep", "remove"):
        raise ValueError("Ação de segmento inválida.")

    updated = deepcopy(plan)
    updated["segments"][segment_index]["action"] = action
    updated["segments"][segment_index]["reason"] = reason
    return recompute_plan(updated)


def restore_cut(plan, segment_index):
    _validate_index(plan, segment_index)

    if plan["segments"][segment_index]["action"] != "remove":
        raise ValueError("O segmento selecionado não é um corte removido.")

    return set_segment_action(
        plan,
        segment_index,
        "keep",
        "restored_by_user",
    )


def remove_segment(plan, segment_index):
    _validate_index(plan, segment_index)

    if plan["segments"][segment_index]["action"] != "keep":
        raise ValueError("O segmento selecionado já está removido.")

    return set_segment_action(
        plan,
        segment_index,
        "remove",
        "manual_remove",
    )


def remove_range(plan, start_ms, end_ms):
    validate_edit_plan(plan)
    start_ms = int(start_ms)
    end_ms = int(end_ms)

    if start_ms > end_ms:
        start_ms, end_ms = end_ms, start_ms

    start_ms = max(0, start_ms)
    end_ms = min(plan["source_duration_ms"], end_ms)

    if end_ms - start_ms < MIN_SEGMENT_MS:
        raise ValueError(
            "O intervalo manual precisa ter pelo menos 50 ms."
        )

    updated = deepcopy(plan)

    if start_ms > 0:
        updated = split_at(updated, start_ms)

    if end_ms < updated["source_duration_ms"]:
        updated = split_at(updated, end_ms)

    for segment in updated["segments"]:
        if (
            segment["start_ms"] >= start_ms
            and segment["end_ms"] <= end_ms
        ):
            segment["action"] = "remove"
            segment["reason"] = "manual_range"

    return recompute_plan(updated)


def adjust_removed_segment(
    plan,
    segment_index,
    *,
    new_start_ms=None,
    new_end_ms=None,
):
    _validate_index(plan, segment_index)

    if plan["segments"][segment_index]["action"] != "remove":
        raise ValueError("Selecione um trecho removido para ajustar.")

    updated = deepcopy(plan)
    segments = updated["segments"]
    segment = segments[segment_index]

    start = (
        segment["start_ms"]
        if new_start_ms is None
        else int(new_start_ms)
    )
    end = (
        segment["end_ms"]
        if new_end_ms is None
        else int(new_end_ms)
    )

    if end - start < MIN_SEGMENT_MS:
        raise ValueError(
            "O corte precisa manter pelo menos 50 ms de duração."
        )

    previous = segments[segment_index - 1] if segment_index > 0 else None
    following = (
        segments[segment_index + 1]
        if segment_index + 1 < len(segments)
        else None
    )

    if previous is None:
        if start != 0:
            raise ValueError(
                "Um corte no início do vídeo precisa começar em 0."
            )
    else:
        minimum_start = previous["start_ms"] + MIN_SEGMENT_MS
        maximum_start = end - MIN_SEGMENT_MS

        if not minimum_start <= start <= maximum_start:
            raise ValueError(
                "Novo início ultrapassa os limites do trecho vizinho."
            )

        previous["end_ms"] = start

    if following is None:
        if end != updated["source_duration_ms"]:
            raise ValueError(
                "Um corte no fim do vídeo precisa terminar no fim da mídia."
            )
    else:
        minimum_end = start + MIN_SEGMENT_MS
        maximum_end = following["end_ms"] - MIN_SEGMENT_MS

        if not minimum_end <= end <= maximum_end:
            raise ValueError(
                "Novo fim ultrapassa os limites do trecho vizinho."
            )

        following["start_ms"] = end

    segment["start_ms"] = start
    segment["end_ms"] = end
    segment["reason"] = "manual_adjust"

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
    source_ms = max(
        0,
        min(int(source_ms), plan["source_duration_ms"]),
    )
    cursor = 0

    for segment in plan["segments"]:
        duration = segment["end_ms"] - segment["start_ms"]

        if source_ms < segment["end_ms"]:
            if segment["action"] == "remove":
                return cursor
            return cursor + max(
                0,
                source_ms - segment["start_ms"],
            )

        if segment["action"] == "keep":
            cursor += duration

    return plan["stats"]["estimated_duration_ms"]
