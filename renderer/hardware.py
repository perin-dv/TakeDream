from dataclasses import dataclass

from core.processing import ProcessingError
from media.process import run_media


@dataclass(frozen=True)
class H264Encoder:
    key: str
    label: str
    codec: str
    quality_args: tuple[str, ...]
    hardware: bool


CPU_ENCODER = H264Encoder(
    key="cpu",
    label="CPU / libx264",
    codec="libx264",
    quality_args=(),
    hardware=False,
)

GPU_ENCODERS = (
    H264Encoder(
        key="nvenc",
        label="NVIDIA NVENC",
        codec="h264_nvenc",
        quality_args=("-preset", "p4", "-rc", "vbr", "-cq", "20", "-b:v", "0"),
        hardware=True,
    ),
    H264Encoder(
        key="qsv",
        label="Intel Quick Sync",
        codec="h264_qsv",
        quality_args=("-preset", "veryfast", "-global_quality", "20"),
        hardware=True,
    ),
    H264Encoder(
        key="amf",
        label="AMD AMF",
        codec="h264_amf",
        quality_args=("-quality", "speed", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"),
        hardware=True,
    ),
)


def listed_encoders(ffmpeg_path, cancel=None):
    stdout, stderr = run_media(
        [
            ffmpeg_path,
            "-hide_banner",
            "-encoders",
        ],
        cancel=cancel,
        timeout=20,
    )
    return (stdout or "") + "\n" + (stderr or "")


def _probe_encoder(ffmpeg_path, encoder, cancel=None):
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=128x72:r=30:d=0.2",
        "-frames:v",
        "2",
        "-an",
        "-c:v",
        encoder.codec,
        "-f",
        "null",
        "-",
    ]

    try:
        run_media(command, cancel=cancel, timeout=15)
    except ProcessingError:
        return False

    return True


def select_h264_encoder(ffmpeg_path, cancel=None):
    """Choose a working GPU H.264 encoder, otherwise return libx264."""
    if not ffmpeg_path:
        return CPU_ENCODER

    try:
        encoders_text = listed_encoders(ffmpeg_path, cancel=cancel)
    except ProcessingError:
        return CPU_ENCODER

    for encoder in GPU_ENCODERS:
        if encoder.codec not in encoders_text:
            continue

        if _probe_encoder(ffmpeg_path, encoder, cancel=cancel):
            return encoder

    return CPU_ENCODER


def cpu_encoder_args(*, preset, crf):
    return [
        "-c:v",
        CPU_ENCODER.codec,
        "-preset",
        str(preset),
        "-crf",
        str(int(crf)),
    ]


def hardware_encoder_args(encoder):
    if not encoder.hardware:
        raise ValueError("Encoder informado não é de hardware.")

    return [
        "-c:v",
        encoder.codec,
        *encoder.quality_args,
    ]
