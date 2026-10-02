from __future__ import annotations

from statistics import median


def _percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, float(fraction))) * (len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _scene_ranges(cut_times_ms, duration_ms):
    duration_ms = max(1, int(duration_ms))
    boundaries = [0]
    for value in sorted({int(item) for item in cut_times_ms or []}):
        if 0 < value < duration_ms:
            boundaries.append(value)
    boundaries.append(duration_ms)
    return [
        {
            "start_ms": start,
            "end_ms": end,
            "duration_ms": end - start,
        }
        for start, end in zip(boundaries, boundaries[1:])
        if end > start
    ]


def _rhythm_label(cuts_per_minute, median_shot_seconds):
    if cuts_per_minute >= 30 or median_shot_seconds <= 2.0:
        return "rapido"
    if cuts_per_minute >= 16 or median_shot_seconds <= 4.0:
        return "moderado"
    return "lento"


def _section_profile(scenes, start_ms, end_ms):
    durations = []
    for scene in scenes:
        overlap_start = max(start_ms, scene["start_ms"])
        overlap_end = min(end_ms, scene["end_ms"])
        if overlap_end > overlap_start:
            durations.append(overlap_end - overlap_start)

    if not durations:
        return {
            "scene_count": 0,
            "average_shot_seconds": 0.0,
            "median_shot_seconds": 0.0,
            "cuts_per_minute": 0.0,
            "rhythm": "lento",
        }

    window_seconds = max(0.001, (end_ms - start_ms) / 1000.0)
    cut_count = max(0, len(durations) - 1)
    cuts_per_minute = cut_count * 60.0 / window_seconds
    median_seconds = median(durations) / 1000.0
    return {
        "scene_count": len(durations),
        "average_shot_seconds": round(sum(durations) / len(durations) / 1000.0, 3),
        "median_shot_seconds": round(median_seconds, 3),
        "cuts_per_minute": round(cuts_per_minute, 3),
        "rhythm": _rhythm_label(cuts_per_minute, median_seconds),
    }


def _pacing_windows(scenes, duration_ms, count=12):
    windows = []
    count = max(4, int(count))
    for index in range(count):
        start = int(round(duration_ms * index / count))
        end = int(round(duration_ms * (index + 1) / count))
        profile = _section_profile(scenes, start, end)
        windows.append(
            {
                "index": index,
                "start_ms": start,
                "end_ms": end,
                "start_ratio": round(index / count, 4),
                "end_ratio": round((index + 1) / count, 4),
                **profile,
            }
        )
    return windows


def build_reference_style_profile(cut_times_ms, duration_ms):
    """Build a deterministic editing-rhythm profile from detected cut points.

    This layer learns timing/rhythm only. Story meaning is handled separately by
    the Reference Story Director; keeping those responsibilities separate makes
    it explicit when the program is measuring versus inferring narrative form.
    """
    duration_ms = int(duration_ms)
    if duration_ms <= 0:
        raise ValueError("A duracao da referencia deve ser positiva.")

    scenes = _scene_ranges(cut_times_ms, duration_ms)
    shot_ms = [item["duration_ms"] for item in scenes]
    duration_minutes = duration_ms / 60000.0
    cuts = max(0, len(scenes) - 1)
    cuts_per_minute = cuts / duration_minutes if duration_minutes > 0 else 0.0
    median_seconds = median(shot_ms) / 1000.0 if shot_ms else 0.0

    section_ranges = {
        "intro": (0.00, 0.15),
        "build": (0.15, 0.55),
        "climax": (0.55, 0.85),
        "finale": (0.85, 1.00),
    }
    sections = {}
    for name, (start_ratio, end_ratio) in section_ranges.items():
        start = int(round(duration_ms * start_ratio))
        end = int(round(duration_ms * end_ratio))
        sections[name] = _section_profile(scenes, start, end)
        sections[name]["start_ms"] = start
        sections[name]["end_ms"] = end

    return {
        "schema_version": "0.2",
        "engine": "reference-rhythm-v2",
        "duration_ms": duration_ms,
        "scene_count": len(scenes),
        "cut_count": cuts,
        "cuts_per_minute": round(cuts_per_minute, 3),
        "average_shot_seconds": round(sum(shot_ms) / len(shot_ms) / 1000.0, 3),
        "median_shot_seconds": round(median_seconds, 3),
        "shot_p25_seconds": round(_percentile(shot_ms, 0.25) / 1000.0, 3),
        "shot_p75_seconds": round(_percentile(shot_ms, 0.75) / 1000.0, 3),
        "shortest_shot_seconds": round(min(shot_ms) / 1000.0, 3),
        "longest_shot_seconds": round(max(shot_ms) / 1000.0, 3),
        "rhythm": _rhythm_label(cuts_per_minute, median_seconds),
        "sections": sections,
        "pacing_windows": _pacing_windows(scenes, duration_ms, 12),
        "scenes": scenes,
    }
