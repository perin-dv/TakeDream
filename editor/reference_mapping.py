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


def _music_phrase_points(music_analysis, target_duration_ms, minimum_gap_ms=6000):
    """Extract sparse musical phrase boundaries, not every beat.

    Strong energy transitions are preferred. Very strong peaks and coarse energy
    section boundaries are fallback candidates. A minimum gap keeps the editor
    from treating normal beats as chapter changes.
    """
    if not isinstance(music_analysis, dict):
        return []

    candidates = []
    for item in music_analysis.get("transitions", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            time_ms = int(item.get("time_ms", 0) or 0)
            strength = float(item.get("strength", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if 0 < time_ms < target_duration_ms and strength >= 0.18:
            priority = 3.0 + strength
            if item.get("direction") == "up":
                priority += 0.25
            candidates.append((time_ms, priority))

    for item in music_analysis.get("energy_peaks", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            time_ms = int(item.get("time_ms", 0) or 0)
            strength = float(item.get("strength", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        if 0 < time_ms < target_duration_ms and strength >= 0.86:
            candidates.append((time_ms, 2.0 + strength))

    for item in music_analysis.get("energy_sections", []) or []:
        if not isinstance(item, dict):
            continue
        try:
            boundary = int(item.get("start_ms", 0) or 0)
        except (TypeError, ValueError):
            continue
        if 0 < boundary < target_duration_ms:
            candidates.append((boundary, 1.0))

    selected = []
    for time_ms, priority in sorted(candidates, key=lambda row: row[1], reverse=True):
        if all(abs(time_ms - existing) >= int(minimum_gap_ms) for existing in selected):
            selected.append(time_ms)

    return sorted(selected)


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
    """Scale reference rhythm while letting the new soundtrack own exact cuts.

    Reference timestamps are proportional hints only. Nearby strong edit points
    in the new song may move individual cuts, while sparse phrase boundaries get
    a wider snap window because they are better places for narrative changes.
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
    phrase_points = _music_phrase_points(music_analysis, target_duration_ms)
    effective_minimum = max(
        int(minimum_shot_ms),
        850 if isinstance(music_analysis, dict) else int(minimum_shot_ms),
    )

    raw_cuts = []
    phrase_snapped = set()
    for scene in scenes[:-1]:
        try:
            source_cut = int(scene["end_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        ratio = source_cut / source_duration
        mapped = int(round(target_duration_ms * ratio))

        phrase_mapped = _snap(mapped, phrase_points, max(850, int(snap_window_ms) * 2))
        if phrase_mapped != mapped:
            mapped = phrase_mapped
            phrase_snapped.add(mapped)
        else:
            mapped = _snap(mapped, music_points, int(snap_window_ms))

        if 0 < mapped < target_duration_ms:
            raw_cuts.append(mapped)

    cuts = []
    cursor = 0
    for value in sorted(set(raw_cuts)):
        if value - cursor < effective_minimum:
            continue
        if target_duration_ms - value < effective_minimum:
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
                    start in music_points
                    or end in music_points
                    or start in phrase_points
                    or end in phrase_points
                ),
                "phrase_boundary_start": start in phrase_points,
                "phrase_boundary_end": end in phrase_points,
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

    phrases = []
    phrase_boundaries = [0, *phrase_points, target_duration_ms]
    for index, (start, end) in enumerate(zip(phrase_boundaries, phrase_boundaries[1:])):
        if end <= start:
            continue
        phrases.append(
            {
                "index": index,
                "start_ms": start,
                "end_ms": end,
                "duration_ms": end - start,
            }
        )

    return {
        "schema_version": "0.2",
        "engine": "reference-mapping-v2",
        "reference_duration_ms": source_duration,
        "target_duration_ms": target_duration_ms,
        "reference_rhythm": reference_style.get("rhythm"),
        "cut_points_ms": cuts,
        "shot_count": len(shots),
        "shots": shots,
        "sections": mapped_sections,
        "music_snap_enabled": bool(music_points),
        "music_edit_points_available": len(music_points),
        "music_phrase_points_ms": phrase_points,
        "music_phrase_count": len(phrases),
        "music_phrases": phrases,
        "phrase_snapped_cut_count": sum(1 for value in cuts if value in phrase_snapped),
        "minimum_shot_ms": effective_minimum,
    }
