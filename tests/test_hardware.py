import unittest
from unittest.mock import patch

from renderer.hardware import (
    CPU_ENCODER,
    GPU_ENCODERS,
    cpu_encoder_args,
    hardware_encoder_args,
    select_h264_encoder,
)


class HardwareEncoderTests(unittest.TestCase):
    @patch("renderer.hardware._probe_encoder")
    @patch("renderer.hardware.listed_encoders")
    def test_prefers_first_working_gpu(self, listed, probe):
        listed.return_value = "h264_nvenc h264_qsv h264_amf"
        probe.return_value = True

        encoder = select_h264_encoder("ffmpeg")

        self.assertEqual(encoder.key, "nvenc")
        probe.assert_called_once()

    @patch("renderer.hardware._probe_encoder")
    @patch("renderer.hardware.listed_encoders")
    def test_falls_through_to_next_gpu(self, listed, probe):
        listed.return_value = "h264_nvenc h264_qsv"
        probe.side_effect = [False, True]

        encoder = select_h264_encoder("ffmpeg")

        self.assertEqual(encoder.key, "qsv")
        self.assertEqual(probe.call_count, 2)

    @patch("renderer.hardware.listed_encoders")
    def test_falls_back_to_cpu_without_supported_gpu(self, listed):
        listed.return_value = "libx264 libx265"

        encoder = select_h264_encoder("ffmpeg")

        self.assertEqual(encoder, CPU_ENCODER)

    def test_encoder_arguments_follow_quality(self):
        nvenc = next(item for item in GPU_ENCODERS if item.key == "nvenc")
        qsv = next(item for item in GPU_ENCODERS if item.key == "qsv")
        amf = next(item for item in GPU_ENCODERS if item.key == "amf")

        self.assertIn("18", hardware_encoder_args(nvenc, quality=18))
        self.assertIn("19", hardware_encoder_args(qsv, quality=19))
        self.assertGreaterEqual(
            hardware_encoder_args(amf, quality=21).count("21"),
            2,
        )

        cpu = cpu_encoder_args(preset="veryfast", quality=20)
        self.assertIn("libx264", cpu)
        self.assertIn("veryfast", cpu)
        self.assertIn("20", cpu)


if __name__ == "__main__":
    unittest.main()
