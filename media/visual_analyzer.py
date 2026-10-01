import re
from pathlib import Path

from core.processing import ProcessingError
from media.process import run_media, run_media_progress


PTS_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
YAVG_RE = re.compile(r"lavfi\.signalstats\.YAVG=([0-9]+(?:\.[0-9]+)?)")
BLUR_RE = re.compile(r"blur mean:\s*([0-9]+(?:\.[0-9]+)?)", re.I)


def build_scene_ranges(cut_times_ms, duration_ms, minimum_scene_ms=250):
    duration_ms = max(1, int(duration_ms))
    boundaries = [0]

    for value in sorted(set(int(item) for item in cut_times_ms)):
        if value <= 0 or value >= duration_ms:
            continue
        if value - boundaries[-1] < minimum_scene_ms:
            continue
        boundaries.append(value)

    if duration_ms - boundaries[-1] < minimum_scene_ms and len(boundaries) > 1:
        boundaries.pop()

    boundaries.append(duration_ms)

    return [
        {
            "id": index,
            "start_ms": start,
            "end_ms": end,
            "duration_ms": end - start,
        }
        for index, (start, end) in enumerate(zip(boundaries, boundaries[1:]))
        if end > start
    ]


def score_visual_sample(*, yavg=None, blur=None, duration_ms=1000):
    if yavg is None:
        exposure_score = 65.0
    else:
        exposure_score = max(0.0, 100.0 - abs(float(yavg) - 110.0) * 1.15)

    if blur is None:
        sharpness_score = 65.0
    else:
        sharpness_score = max(0.0, min(100.0, (1.0 - float(blur)) * 100.0))

    duration_score = max(25.0, min(100.0, float(duration_ms) / 25.0))
    total = (
        sharpness_score * 0.55
        + exposure_score * 0.35
        + duration_score * 0.10
    )
    total = round(max(0.0, min(100.0, total)), 1)

    if total >= 82:
        label = "excelente"
    elif total >= 68:
        label = "boa"
    elif total >= 52:
        label = "utilizavel"
    else:
        label = "fraca"

    return {
        "score": total,
        "label": label,
        "sharpness_score": round(sharpness_score, 1),
        "exposure_score": round(exposure_score, 1),
        "duration_score": round(duration_score, 1),
        "yavg": None if yavg is None else round(float(yavg), 3),
        "blur": None if blur is None else round(float(blur), 5),
    }


def _sample_indices(total, limit):
    if total <= 0:
        return []
    if total <= limit:
        return list(range(total))
    if limit <= 1:
        return [0]

    return sorted({
        int(round(index * (total - 1) / (limit - 1)))
        for index in range(limit)
    })


class VisualAnalyzer:
    def __init__(self, ffmpeg_path, runner=run_media):
        self.ffmpeg_path = ffmpeg_path
        self.runner = runner

    def analyze(
        self,
        source,
        duration_ms,
        *,
        cancel=None,
        scene_threshold=0.30,
        max_quality_samples=36,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        if not self.ffmpeg_path:
            raise ProcessingError("FFmpeg não encontrado para análise visual.")

        source = Path(source).expanduser().resolve()
        if not source.exists():
            raise ProcessingError("O vídeo não foi encontrado para análise visual.")

        stage("Detectando mudanças de cena... 0%")
        progress(5)

        last_scene_percent = {-1}

        def scene_progress(value):
            value = max(0, min(100, int(value)))
            progress(5 + int(value * 0.55))
            bucket = int(value / 2) * 2
            if bucket not in last_scene_percent:
                last_scene_percent.clear()
                last_scene_percent.add(bucket)
                stage(f"Detectando mudanças de cena... {value}%")

        cuts = self.detect_scene_changes(
            source,
            duration_ms,
            threshold=scene_threshold,
            cancel=cancel,
            progress=scene_progress,
        )
        scenes = build_scene_ranges(cuts, duration_ms)

        stage("Avaliando qualidade dos takes... 0%")
        progress(60)
        sample_indices = _sample_indices(len(scenes), max_quality_samples)
        sampled_indices = set(sample_indices)
        sampled = 0

        for position, scene_index in enumerate(sample_indices):
            scene = scenes[scene_index]
            scene["sample_ms"] = int((scene["start_ms"] + scene["end_ms"]) / 2)
            try:
                metrics = self.sample_quality(
                    source,
                    scene["sample_ms"],
                    scene["duration_ms"],
                    cancel=cancel,
                )
            except ProcessingError:
                metrics = score_visual_sample(duration_ms=scene["duration_ms"])
                metrics["degraded"] = True

            metrics["sampled"] = True
            scene["quality"] = metrics
            sampled += 1
            quality_percent = int((position + 1) * 100 / max(1, len(sample_indices)))
            progress(60 + int(quality_percent * 0.35))
            stage(
                f"Avaliando qualidade dos takes... {quality_percent}% "
                f"({position + 1}/{len(sample_indices)})"
            )

        for index, scene in enumerate(scenes):
            if index in sampled_indices:
                continue
            metrics = score_visual_sample(duration_ms=scene["duration_ms"])
            metrics["sampled"] = False
            metrics["estimated"] = True
            scene["sample_ms"] = int((scene["start_ms"] + scene["end_ms"]) / 2)
            scene["quality"] = metrics

        ranked = sorted(
            (scene for scene in scenes if isinstance(scene.get("quality"), dict)),
            key=lambda item: item["quality"]["score"],
            reverse=True,
        )
        average = (
            round(sum(item["quality"]["score"] for item in ranked) / len(ranked), 1)
            if ranked
            else None
        )

        progress(100)
        stage("Análise visual concluída • 100%")
        return {
            "schema_version": "0.1",
            "scene_threshold": float(scene_threshold),
            "scenes": scenes,
            "summary": {
                "scene_count": len(scenes),
                "quality_samples": sampled,
                "estimated_quality_scenes": max(0, len(scenes) - sampled),
                "average_quality": average,
                "best_scene_ids": [item["id"] for item in ranked[:12]],
            },
        }

    def detect_scene_changes(
        self,
        source,
        duration_ms,
        *,
        threshold=0.30,
        cancel=None,
        progress=lambda value: None,
    ):
        filter_expr = (
            "scale=320:-2:flags=fast_bilinear,"
            f"select=gt(scene\\,{float(threshold):.3f}),showinfo"
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
            filter_expr,
            "-an",
            "-sn",
            "-dn",
            "-f",
            "null",
            "-",
        ]

        if self.runner is run_media:
            _, stderr = run_media_progress(
                command,
                duration_ms=max(1, int(duration_ms)),
                progress=progress,
                cancel=cancel,
                timeout=300,
            )
        else:
            progress(5)
            _, stderr = self.runner(command, cancel=cancel, timeout=300)
            progress(100)

        values = []
        for match in PTS_RE.finditer(stderr):
            milliseconds = int(round(float(match.group(1)) * 1000))
            if 0 < milliseconds < int(duration_ms):
                values.append(milliseconds)
        return sorted(set(values))

    def sample_quality(self, source, sample_ms, duration_ms, *, cancel=None):
        seconds = max(0.0, float(sample_ms) / 1000.0)
        filters = (
            "scale=320:-2:flags=bilinear,"
            "signalstats,"
            "metadata=print:key=lavfi.signalstats.YAVG,"
            "blurdetect=block_width=32:block_height=32:block_pct=80"
        )
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-nostdin",
            "-v",
            "info",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            filters,
            "-an",
            "-f",
            "null",
            "-",
        ]
        stdout, stderr = self.runner(command, cancel=cancel, timeout=60)
        text = stdout + "\n" + stderr

        yavg_match = YAVG_RE.search(text)
        blur_match = BLUR_RE.search(text)
        yavg = float(yavg_match.group(1)) if yavg_match else None
        blur = float(blur_match.group(1)) if blur_match else None

        return score_visual_sample(
            yavg=yavg,
            blur=blur,
            duration_ms=duration_ms,
        )
