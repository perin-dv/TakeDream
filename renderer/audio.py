DEFAULT_AUDIO_SETTINGS = {
    "enabled": True,
    "target_lufs": -16.0,
    "lra": 11.0,
    "true_peak": -1.5,
    "limiter": 0.95,
}


def normalize_audio_settings(value):
    result = dict(DEFAULT_AUDIO_SETTINGS)

    if isinstance(value, dict):
        for key in result:
            if key in value:
                result[key] = value[key]

    result["enabled"] = bool(result["enabled"])

    for key, default in (
        ("target_lufs", -16.0),
        ("lra", 11.0),
        ("true_peak", -1.5),
        ("limiter", 0.95),
    ):
        try:
            result[key] = float(result[key])
        except (TypeError, ValueError):
            result[key] = default

    result["target_lufs"] = max(-24.0, min(-10.0, result["target_lufs"]))
    result["lra"] = max(1.0, min(20.0, result["lra"]))
    result["true_peak"] = max(-9.0, min(-0.1, result["true_peak"]))
    result["limiter"] = max(0.5, min(1.0, result["limiter"]))

    return result


def audio_filter_chain(settings=None):
    if settings is None:
        return None

    settings = normalize_audio_settings(settings)

    if not settings["enabled"]:
        return None

    return (
        "loudnorm="
        f"I={settings['target_lufs']:.1f}:"
        f"LRA={settings['lra']:.1f}:"
        f"TP={settings['true_peak']:.1f},"
        f"alimiter=limit={settings['limiter']:.3f}"
    )
