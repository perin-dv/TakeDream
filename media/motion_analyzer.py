import re
from pathlib import Path
from statistics import median

from core.processing import ProcessingError
from media.process import run_media_progress


PTS_TIME_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=([0-9]+(?:\.[0-9]+)?)")


def _clamp(value, low, high):
    return max(low, min(high, value))


def _percentile(values, ratio):
    values = sorted(float(item) for item in values)
    if not values:
        return 0.0
    index = int(round((len(values) - 1) * float(ratio)))
    return values[_clamp(index, 0, len(values) - 1)]


def parse_motion_samples(text):
    """Parseia pts_time + YAVG produzidos por tblend/signalstats do FFmpeg."""
    samples = []
    current_ms = None

    for line in str(text or "").splitlines():
        pts = PTS_TIME_RE.search(line)
        if pts:
            current_ms = int(round(float(pts.group(1)) * 1000))

        value = YAVG_RE.search(line)
        if value and current_ms is not None:
            samples.append(
                {
                    "time_ms": current_ms,
                    "motion": round(float(value.group(1)), 4),
                }
            )

    deduped = {}
    for sample in samples:
        deduped[int(sample["time_ms"])] = sample
    return [deduped[key] for key in sorted(deduped)]


def profile_scene_motion(
    samples,
    start_ms,
    end_ms,
    *,
    edge_window_ms=900,
    safety_pad_ms=170,
    minimum_keep_ms=650,
):
    """Detecta chicotes de borda e picos curtos dentro do take.

    Bordas ruins ainda são aparadas. Um pico curto no miolo não pode ser aparado
    sem quebrar o take; nesse caso a cena recebe `internal_whip` para que o
    seletor a descarte/penalize. Pans/gimbal contínuos permanecem preservados.
    """
    start_ms = int(start_ms)
    end_ms = int(end_ms)
    duration_ms = max(0, end_ms - start_ms)
    scene_samples = [
        item
        for item in (samples or [])
        if start_ms <= int(item.get("time_ms", -1)) <= end_ms
    ]

    result = {
        "classification": "unknown",
        "confidence": 0.0,
        "sample_count": len(scene_samples),
        "median_motion": 0.0,
        "p90_motion": 0.0,
        "peak_motion": 0.0,
        "entry_peak": 0.0,
        "exit_peak": 0.0,
        "middle_peak": 0.0,
        "internal_spike_samples": 0,
        "safe_start_ms": start_ms,
        "safe_end_ms": end_ms,
        "trim_start_ms": 0,
        "trim_end_ms": 0,
    }

    if duration_ms < minimum_keep_ms or len(scene_samples) < 3:
        return result

    values = [float(item.get("motion", 0.0) or 0.0) for item in scene_samples]
    med = float(median(values))
    p90 = _percentile(values, 0.90)
    peak = max(values)

    entry_limit = min(end_ms, start_ms + int(edge_window_ms))
    exit_limit = max(start_ms, end_ms - int(edge_window_ms))
    entry = [item for item in scene_samples if int(item["time_ms"]) <= entry_limit]
    exit_items = [item for item in scene_samples if int(item["time_ms"]) >= exit_limit]
    middle = [
        item
        for item in scene_samples
        if entry_limit < int(item["time_ms"]) < exit_limit
    ]

    entry_peak = max((float(item["motion"]) for item in entry), default=0.0)
    exit_peak = max((float(item["motion"]) for item in exit_items), default=0.0)
    middle_values = [float(item["motion"]) for item in middle]
    middle_median = float(median(middle_values)) if middle_values else med
    middle_p90 = _percentile(middle_values, 0.90) if middle_values else p90
    middle_peak = max(middle_values, default=0.0)

    # Limites relativos ao próprio take. Movimento contínuo precisa manter a
    # energia alta por boa parte do miolo; um pico isolado é tratado diferente.
    spike_threshold = max(7.0, middle_median * 1.85 + 1.6)
    continuous_motion = (
        middle_median >= 6.5
        and middle_p90 <= middle_median * 1.75 + 1.5
        and middle_peak <= middle_median * 2.15 + 2.0
    )

    entry_spike = entry_peak >= spike_threshold and entry_peak >= middle_median * 1.55
    exit_spike = exit_peak >= spike_threshold and exit_peak >= middle_median * 1.55

    internal_threshold = max(8.0, middle_median * 1.95 + 1.8)
    internal_high = [
        item
        for item in middle
        if float(item.get("motion", 0.0) or 0.0) >= internal_threshold
    ]
    internal_spike = (
        len(middle) >= 3
        and bool(internal_high)
        and middle_peak >= internal_threshold
        and middle_peak >= max(8.0, middle_median * 1.65)
        and len(internal_high) <= max(2, int(round(len(middle) * 0.24)))
    )

    if continuous_motion and entry_peak <= middle_median * 1.65 and exit_peak <= middle_median * 1.65:
        classification = "continuous_motion"
        entry_spike = False
        exit_spike = False
        internal_spike = False
    elif entry_spike and exit_spike:
        classification = "edge_whip_both"
    elif entry_spike:
        classification = "entry_whip"
    elif exit_spike:
        classification = "exit_whip"
    elif internal_spike:
        classification = "internal_whip"
    else:
        classification = "stable"

    safe_start = start_ms
    safe_end = end_ms

    if entry_spike:
        high_times = [
            int(item["time_ms"])
            for item in entry
            if float(item["motion"]) >= spike_threshold
        ]
        if high_times:
            safe_start = min(
                start_ms + 1200,
                max(high_times) + int(safety_pad_ms),
            )

    if exit_spike:
        high_times = [
            int(item["time_ms"])
            for item in exit_items
            if float(item["motion"]) >= spike_threshold
        ]
        if high_times:
            safe_end = max(
                end_ms - 1200,
                min(high_times) - int(safety_pad_ms),
            )

    # O Motion Gate nunca pode destruir um take: se a margem segura ficar curta
    # demais, reduzimos o trim ou desistimos dele.
    if safe_end - safe_start < minimum_keep_ms:
        safe_start = start_ms
        safe_end = end_ms
        classification = "unstable_preserved"

    if internal_spike and classification == "internal_whip":
        ratio = middle_peak / max(0.001, internal_threshold)
        confidence = _clamp((ratio - 1.0) / 1.15 + 0.35, 0.0, 1.0)
    elif entry_spike or exit_spike:
        ratio = max(entry_peak, exit_peak) / max(0.001, spike_threshold)
        confidence = _clamp((ratio - 1.0) / 1.4, 0.0, 1.0)
    else:
        confidence = 0.0

    result.update(
        {
            "classification": classification,
            "confidence": round(confidence, 3),
            "median_motion": round(med, 4),
            "p90_motion": round(p90, 4),
            "peak_motion": round(peak, 4),
            "entry_peak": round(entry_peak, 4),
            "exit_peak": round(exit_peak, 4),
            "middle_peak": round(middle_peak, 4),
            "internal_spike_samples": len(internal_high),
            "safe_start_ms": int(safe_start),
            "safe_end_ms": int(safe_end),
            "trim_start_ms": max(0, int(safe_start - start_ms)),
            "trim_end_ms": max(0, int(end_ms - safe_end)),
        }
    )
    return result


class MotionAnalyzer:
    """Passagem leve de movimento para Motion Gate.

    Analisa o vídeo inteiro em baixa resolução. Além das bordas, agora também
    sinaliza picos curtos dentro do take para o seletor evitar chicotes internos.
    """

    def __init__(self, ffmpeg_path):
        self.ffmpeg_path = ffmpeg_path

    def analyze(
        self,
        source,
        duration_ms,
        scenes,
        *,
        cancel=None,
        progress=lambda value: None,
        stage=lambda text: None,
    ):
        if not self.ffmpeg_path:
            raise ProcessingError("FFmpeg não encontrado para analisar movimento.")

        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise ProcessingError("O vídeo não foi encontrado para analisar movimento.")

        stage("Mapeando movimento e possíveis chicotes...")
        progress(0)

        filters = (
            "fps=8,"
            "scale=160:-2:flags=fast_bilinear,"
            "tblend=all_mode=difference,"
            "signalstats,"
            "metadata=print:key=lavfi.signalstats.YAVG"
        )
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-nostdin",
            "-v",
            "info",
            "-i",
            str(source),
            "-vf",
            filters,
            "-an",
            "-sn",
            "-dn",
            "-f",
            "null",
            "-",
        ]

        stdout, stderr = run_media_progress(
            command,
            duration_ms=max(1, int(duration_ms)),
            progress=progress,
            cancel=cancel,
            timeout=300,
        )
        samples = parse_motion_samples(stdout + "\n" + stderr)

        profiles = []
        trimmed = 0
        continuous = 0
        internal_whips = 0
        for scene in scenes or []:
            try:
                start_ms = int(scene.get("start_ms", 0) or 0)
                end_ms = int(scene.get("end_ms", start_ms) or start_ms)
            except (TypeError, ValueError):
                continue
            profile = profile_scene_motion(samples, start_ms, end_ms)
            profile["scene_id"] = scene.get("id")
            profiles.append(profile)
            if profile.get("trim_start_ms") or profile.get("trim_end_ms"):
                trimmed += 1
            if profile.get("classification") == "continuous_motion":
                continuous += 1
            if profile.get("classification") == "internal_whip":
                internal_whips += 1

        progress(100)
        stage(
            f"Motion Gate: {trimmed} borda(s) ajustada(s), "
            f"{internal_whips} chicote(s) interno(s) sinalizado(s), "
            f"{continuous} movimento(s) contínuo(s) preservado(s)."
        )
        return {
            "schema_version": "0.2",
            "engine": "motion-gate-v1",
            "sample_fps": 8,
            "sample_count": len(samples),
            "trimmed_scene_count": trimmed,
            "internal_whip_scene_count": internal_whips,
            "continuous_motion_scene_count": continuous,
            "scenes": profiles,
        }
