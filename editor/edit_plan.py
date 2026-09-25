from datetime import datetime, timezone

from profiles import get_edit_rules


EDIT_PLAN_SCHEMA = "0.1"


def build_edit_plan(duration_ms, profile, style, silences):
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("A duração do vídeo deve ser um inteiro positivo em milissegundos.")
    if not isinstance(silences, dict) or not isinstance(silences.get("silences"), list):
        raise ValueError("Dados de silêncio inválidos.")

    rules = get_edit_rules(profile, style)
    removals = []

    silence_items = (
        silences["silences"]
        if rules.automatic_silence_cuts
        else []
    )

    for silence in silence_items:
        try:
            silence_start = int(silence["start_ms"])
            silence_end = int(silence["end_ms"])
            silence_duration = int(silence["duration_ms"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Trecho de silêncio inválido.") from error

        if silence_duration < rules.minimum_silence_ms:
            continue

        start = max(
            silence_start + rules.edge_padding_ms,
            rules.protect_start_ms,
            0,
        )
        end = min(
            silence_end - rules.edge_padding_ms,
            duration_ms - rules.protect_end_ms,
            duration_ms,
        )

        if end - start < rules.minimum_cut_ms:
            continue

        if removals and start <= removals[-1]["end_ms"]:
            removals[-1]["end_ms"] = max(removals[-1]["end_ms"], end)
            removals[-1]["duration_ms"] = (
                removals[-1]["end_ms"] - removals[-1]["start_ms"]
            )
        else:
            removals.append(
                {
                    "start_ms": start,
                    "end_ms": end,
                    "duration_ms": end - start,
                    "reason": "long_silence",
                }
            )

    segments = []
    cursor = 0

    for removal in removals:
        if removal["start_ms"] > cursor:
            segments.append(
                {
                    "start_ms": cursor,
                    "end_ms": removal["start_ms"],
                    "action": "keep",
                    "reason": "content",
                }
            )

        segments.append(
            {
                "start_ms": removal["start_ms"],
                "end_ms": removal["end_ms"],
                "action": "remove",
                "reason": removal["reason"],
            }
        )
        cursor = removal["end_ms"]

    if cursor < duration_ms:
        segments.append(
            {
                "start_ms": cursor,
                "end_ms": duration_ms,
                "action": "keep",
                "reason": "content",
            }
        )

    if not segments:
        segments = [
            {
                "start_ms": 0,
                "end_ms": duration_ms,
                "action": "keep",
                "reason": "content",
            }
        ]

    removed_duration = sum(
        segment["end_ms"] - segment["start_ms"]
        for segment in segments
        if segment["action"] == "remove"
    )
    keep_duration = duration_ms - removed_duration
    cuts = sum(1 for segment in segments if segment["action"] == "remove")

    plan = {
        "schema_version": EDIT_PLAN_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "profile": rules.profile,
        "style": rules.style,
        "rules": rules.to_dict(),
        "source_duration_ms": duration_ms,
        "segments": segments,
        "stats": {
            "cuts": cuts,
            "removed_duration_ms": removed_duration,
            "estimated_duration_ms": keep_duration,
        },
    }

    return validate_edit_plan(plan)


def validate_edit_plan(plan):
    try:
        if not isinstance(plan, dict) or plan.get("schema_version") != EDIT_PLAN_SCHEMA:
            raise ValueError("Versão de plano inválida.")
        if not isinstance(plan.get("profile"), str) or not plan["profile"]:
            raise ValueError("Perfil ausente.")
        if not isinstance(plan.get("style"), str) or not plan["style"]:
            raise ValueError("Estilo ausente.")

        duration = plan["source_duration_ms"]
        if type(duration) is not int or duration <= 0:
            raise ValueError("Duração de origem inválida.")

        segments = plan["segments"]
        if not isinstance(segments, list) or not segments:
            raise ValueError("Plano sem segmentos.")

        cursor = 0
        removed_duration = 0
        cuts = 0

        for segment in segments:
            if not isinstance(segment, dict):
                raise ValueError("Segmento inválido.")

            start = segment.get("start_ms")
            end = segment.get("end_ms")
            action = segment.get("action")

            if type(start) is not int or type(end) is not int:
                raise ValueError("Timestamp inválido.")
            if start != cursor or end <= start or end > duration:
                raise ValueError("Segmentos devem ser contínuos, ordenados e válidos.")
            if action not in ("keep", "remove"):
                raise ValueError("Ação de edição inválida.")
            if not isinstance(segment.get("reason"), str) or not segment["reason"]:
                raise ValueError("Motivo da decisão ausente.")

            if action == "remove":
                removed_duration += end - start
                cuts += 1

            cursor = end

        if cursor != duration:
            raise ValueError("O plano não cobre toda a duração da mídia.")

        stats = plan.get("stats")
        if not isinstance(stats, dict):
            raise ValueError("Estatísticas ausentes.")
        if stats.get("cuts") != cuts:
            raise ValueError("Quantidade de cortes inconsistente.")
        if stats.get("removed_duration_ms") != removed_duration:
            raise ValueError("Duração removida inconsistente.")
        if stats.get("estimated_duration_ms") != duration - removed_duration:
            raise ValueError("Duração estimada inconsistente.")

        rules = plan.get("rules")
        if not isinstance(rules, dict):
            raise ValueError("Regras do perfil ausentes.")

    except (KeyError, TypeError) as error:
        raise ValueError("edit_plan.json possui estrutura inválida.") from error

    return plan


def kept_segments(plan):
    validate_edit_plan(plan)
    return [
        segment
        for segment in plan["segments"]
        if segment["action"] == "keep"
    ]
