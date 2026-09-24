"""Optional real FFmpeg checks with synthesized tones; no Whisper download."""
import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from media.audio_extractor import AudioExtractor, wav_duration_ms
from media.ffmpeg_tools import FFmpegTools, MediaProbeError
from media.process import run_media
from media.silence_detector import SilenceDetector


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe fora do PATH")
class FFmpegIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tools = FFmpegTools()

    def test_real_extraction_and_silence_at_start_middle_end(self):
        audio = self.root / "tones.wav"
        with wave.open(str(audio), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            samples = [int(12000 * math.sin(2 * math.pi * 440 * i / 16000))
                       if i // 16000 in (1, 3) else 0 for i in range(80000)]
            stream.writeframes(struct.pack("<" + "h" * len(samples), *samples))
        video = self.root / "source.mkv"
        run_media([self.tools.ffmpeg_path, "-v", "error", "-f", "lavfi", "-i", "color=s=160x90:r=10:d=5",
                   "-i", str(audio), "-c:v", "mpeg4", "-c:a", "pcm_s16le", "-shortest", str(video)])
        output = self.root / "audio" / "extracted.wav"
        AudioExtractor(self.tools).extract(video, output)
        self.assertEqual(wav_duration_ms(output), 5000)
        found = SilenceDetector(self.tools).detect(output)["silences"]
        self.assertEqual(len(found), 3)
        for interval, start, end in zip(found, (0, 2000, 4000), (1000, 3000, 5000)):
            self.assertLessEqual(abs(interval["start_ms"] - start), 2)
            self.assertLessEqual(abs(interval["end_ms"] - end), 2)

    def test_real_entire_file_silent(self):
        from tests.helpers import make_wav
        audio = self.root / "silence.wav"
        make_wav(audio, 2)
        self.assertEqual(SilenceDetector(self.tools).detect(audio)["silences"],
                         [{"start_ms": 0, "end_ms": 2000, "duration_ms": 2000}])

    def test_corrupt_video_reports_probe_error(self):
        source = self.root / "broken.mp4"
        source.write_bytes(b"corrupted video")
        with self.assertRaises(MediaProbeError):
            self.tools.probe(source)
