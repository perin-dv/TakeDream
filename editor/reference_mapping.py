from __future__ import annotations


def _music_points(music_analysis):
    if not isinstance(music_analysis, dict):
        return []
    points = music_analysis.get("edit_points_ms", [])
    if not isinstance(points, list):
        return []
    valid = []
    for value in points:
        try:
            point = int(value)
        except (TypeError, ValueError):
            continue
        if point > 0:
            valid.append(point)
    return sorted(set(valid))


def _snap(point, music_points, window_ms):
    candidates = [
        value
        for value in music_points
        if abs(value - point) <= window_ms
    ]
    if not candidates:
        return point
    return min(candidates, key=lambda value: abs(value - point))


def map_reference_timing(
    reference_style,
    target_duration_ms,
    *,
    music_analysis=None,
    snap_window_ms=450,
    minimum_shot_ms=500,
):
    """Scale a reference cut pattern and optionally snap it to a new soundtrack.

    The mapping preserves relative editing rhythm rather than copying absolute
    timestamps. This allows a 3:20 reference to guide a 3:50 trailer while the
    new soundtrack determines the exact nearby edit points.
    """
    if not isinstance(reference_style, dict):
        raise ValueError("Perfil de referencia invalido.")

    source_duration = reference_style.get("duration_ms")
    try:
        source_duration = int(source_duration)
        target_duration_ms = int(target_duration_ms)
    except (TypeError, ValueError) as error:
        raise ValueError("Duracao invalida para mapear a referencia.") from error

    if source_duration <= 0 or target_duration_ms <= 0:
        raise ValueError("As duracoes devem ser positivas.")

    scenes = reference_style.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("A referencia nao possui cenas para mapear.")

    music_points = _music_points(music_analysis)
    raw_cuts = []
    for scene in scenes[:-1]:
        try:
            source_cut = int(scene["end_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        ratio = source_cut / source_duration
        mapped = int(round(target_duration_ms * ratio))
        mapped = _snap(mapped, music_points, int(snap_window_ms))
        if 0 < mapped < target_duration_ms:
            raw_cuts.append(mapped)

    cuts = []
    cursor = 0
    for value in sorted(set(raw_cuts)):
        if value - cursor < minimum_shot_ms:
            continue
        if target_duration_ms - value < minimum_shot_ms:
            continue
        cuts.append(value)
        cursor = value

    boundaries = [0, *cuts, target_duration_ms]
    shots = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        shots.append(
            {
                "index": index,
                "start_ms": start,
                "end_ms": end,
                "duration_ms": end - start,
                "snapped_to_music": (
                    start in music_points or end in music_points
                ),
            }
        )

    source_sections = reference_style.get("sections", {})
    mapped_sections = {}
    if isinstance(source_sections, dict):
        for name, section in source_sections.items():
            if not isinstance(section, dict):
                continue
            try:
                start = int(section.get("start_ms", 0))
                end = int(section.get("end_ms", source_duration))
            except (TypeError, ValueError):
                continue
            mapped_sections[name] = {
                "start_ms": int(round(target_duration_ms * start / source_duration)),
                "end_ms": int(round(target_duration_ms * end / source_duration)),
                "reference_average_shot_seconds": section.get("average_shot_seconds"),
                "reference_median_shot_seconds": section.get("median_shot_seconds"),
            }

    return {
        "schema_version": "0.1",
        "engine": "reference-mapping-v1",
        "reference_duration_ms": source_duration,
        "target_duration_ms": target_duration_ms,
        "reference_rhythm": reference_style.get("rhythm"),
        "cut_points_ms": cuts,
        "shot_count": len(shots),
        "shots": shots,
        "sections": mapped_sections,
        "music_snap_enabled": bool(music_points),
        "music_edit_points_available": len(music_points),
    }
