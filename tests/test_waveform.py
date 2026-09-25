import array
import tempfile
import unittest
import wave
from pathlib import Path

from media.waveform import load_or_create_waveform


class WaveformTests(unittest.TestCase):
    def test_generates_and_reuses_waveform_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            audio_dir = project / "audio"
            audio_dir.mkdir(parents=True)

            wav_path = audio_dir / "extracted.wav"

            samples = array.array(
                "h",
                [0, 5000, -10000, 20000, -30000]
                * 400,
            )

            with wave.open(str(wav_path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(samples.tobytes())

            first = load_or_create_waveform(
                project,
                buckets=32,
            )
            second = load_or_create_waveform(
                project,
                buckets=32,
            )

            self.assertTrue(first)
            self.assertEqual(first, second)
            self.assertLessEqual(max(first), 1000)
            self.assertTrue(
                (project / "analysis" / "waveform.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
