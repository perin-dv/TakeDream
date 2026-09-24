import os
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.processing import ProcessingCancelled, ProcessingError, seconds_to_ms
from core.project_manager import ProjectManager
from core.results import (AUDIO_PATH, TRANSCRIPT_PATH, SILENCES_PATH, load_results,
                          validate_transcript, validate_silences)
from core.storage import read_json, write_json
from core.transcription_pipeline import TranscriptionPipeline
from media.audio_extractor import AudioExtractor, wav_duration_ms
from media.ffmpeg_tools import FFmpegTools, FFmpegNotFoundError
from media.process import run_media
from media.silence_detector import parse_silencedetect
from transcription.base import WhisperConfig
from transcription.faster_whisper import FasterWhisperTranscriber, serialize_segment
from tests.helpers import make_wav, segment, transcript, silences


class TimestampTests(unittest.TestCase):
    def test_rounding_and_integers(self):
        for seconds, expected in [(0, 0), (1.2345, 1235), ("0.0005", 1), (12.3, 12300)]:
            self.assertEqual(seconds_to_ms(seconds), expected)
            self.assertIs(type(seconds_to_ms(seconds)), int)

    def test_invalid(self):
        for value in [-1, float("nan"), float("inf"), None, "bad"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                seconds_to_ms(value)

    def test_segment_and_words(self):
        data = serialize_segment(segment())
        self.assertEqual(data["start_ms"], 125)
        self.assertEqual(data["words"][0]["end_ms"], 900)
        self.assertEqual(data["text"], "Olá!")


class SilenceTests(unittest.TestCase):
    def test_beginning_middle_and_open_end(self):
        output = "silence_start: 0\nsilence_end: 1\nsilence_start: 2.25\nsilence_end: 3\nsilence_start: 4"
        self.assertEqual(parse_silencedetect(output, 5000), [
            {"start_ms": 0, "end_ms": 1000, "duration_ms": 1000},
            {"start_ms": 2250, "end_ms": 3000, "duration_ms": 750},
            {"start_ms": 4000, "end_ms": 5000, "duration_ms": 1000}])

    def test_end_event_clamped_to_audio_duration(self):
        self.assertEqual(parse_silencedetect("silence_start: 0\nsilence_end: 5.00006", 5000)[0]["end_ms"], 5000)

    def test_no_silence_and_entire_silence(self):
        self.assertEqual(parse_silencedetect("unrelated ffmpeg output", 5000), [])
        self.assertEqual(parse_silencedetect("silence_start: 0", 5000)[0]["duration_ms"], 5000)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "video.mp4"
        self.source.write_bytes(b"test fixture, never used for real processing")
        self.manager = ProjectManager(self.root / "projects")
        self.project = self.manager.create_project("Teste", self.source, "YouTube", "Clean")

    def save_results(self):
        make_wav(self.project / AUDIO_PATH)
        write_json(self.project / TRANSCRIPT_PATH, transcript())
        write_json(self.project / SILENCES_PATH, silences())

    def test_persistence_and_relative_paths(self):
        self.manager.update_processing(self.project, "transcribed", audio_path=AUDIO_PATH,
                                       transcription_path=TRANSCRIPT_PATH, silences_path=SILENCES_PATH)
        _, saved = self.manager.load_project(self.project)
        self.assertEqual(saved["status"], "transcribed")
        self.assertEqual(saved["audio_path"], AUDIO_PATH)
        self.assertEqual(saved["source"]["original_path"], str(self.source.resolve()))

    def test_metadata_does_not_regress_pipeline_status(self):
        self.manager.update_processing(self.project, "transcribed")
        self.manager.save_media_metadata(self.project, {"video": {}})
        self.assertEqual(self.manager.load_project(self.project)[1]["status"], "transcribed")

    def test_reload_results_and_unicode_json(self):
        self.save_results()
        loaded = load_results(self.project)
        self.assertEqual(loaded["transcript"], transcript())
        self.assertEqual(loaded["silences"], silences())
        self.assertEqual(loaded["errors"], [])
        self.assertIn("Olá", (self.project / TRANSCRIPT_PATH).read_text(encoding="utf-8"))

    def test_invalid_json_reported_and_preserved(self):
        path = self.project / TRANSCRIPT_PATH
        path.write_text("{broken", encoding="utf-8")
        self.assertTrue(load_results(self.project)["errors"])
        with self.assertRaisesRegex(ProcessingError, "backup"):
            TranscriptionPipeline(self.manager).run(self.project)
        self.assertEqual(path.read_text(), "{broken")

    def test_invalid_project_source(self):
        write_json(self.project / "project.json", {"name": "x", "source": []})
        with self.assertRaises(ValueError):
            self.manager.load_project(self.project)

    def test_invalid_result_contracts(self):
        for value in [[], {}, None, {"schema_version": "0.1", "segments": []}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_transcript(value)
        data = transcript()
        data["segments"][0]["start_ms"] = 0.125
        with self.assertRaises(ValueError):
            validate_transcript(data)
        data = silences()
        data["silences"][0]["duration_ms"] = 2
        with self.assertRaises(ValueError):
            validate_silences(data)

    def test_atomic_write_failure_keeps_previous(self):
        path = self.project / TRANSCRIPT_PATH
        write_json(path, transcript())
        with patch("core.storage.os.replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                write_json(path, {})
        self.assertEqual(read_json(path), transcript())
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_full_cache_does_not_call_engines_or_require_source(self):
        self.save_results()
        self.source.unlink()
        engine = Mock()
        with patch("core.transcription_pipeline.AudioExtractor") as extractor, patch("core.transcription_pipeline.SilenceDetector") as detector:
            result = TranscriptionPipeline(self.manager, transcriber=engine).run(self.project)
        engine.transcribe.assert_not_called()
        extractor.assert_not_called()
        detector.assert_not_called()
        self.assertEqual(result["transcript"], transcript())
        self.assertEqual(self.manager.load_project(self.project)[1]["status"], "transcribed")

    def test_resume_wav_and_save_transcription_before_silence_failure(self):
        make_wav(self.project / AUDIO_PATH)
        engine = Mock()
        engine.transcribe.return_value = transcript()
        with patch("core.transcription_pipeline.SilenceDetector") as detector:
            detector.return_value.detect.side_effect = ProcessingError("failed silence")
            with self.assertRaises(ProcessingError):
                TranscriptionPipeline(self.manager, transcriber=engine).run(self.project)
        self.assertEqual(read_json(self.project / TRANSCRIPT_PATH), transcript())
        self.assertEqual(self.manager.load_project(self.project)[1]["status"], "transcription_ready")
        with patch("core.transcription_pipeline.SilenceDetector") as detector:
            detector.return_value.detect.return_value = silences()
            TranscriptionPipeline(self.manager, transcriber=engine).run(self.project)
        engine.transcribe.assert_called_once()

    def test_cancel_before_processing(self):
        event = Event()
        event.set()
        with self.assertRaises(ProcessingCancelled):
            TranscriptionPipeline(self.manager).run(self.project, cancel=event)

    def test_cancel_after_transcribing_does_not_publish_partial_result(self):
        make_wav(self.project / AUDIO_PATH)
        event = Event()
        engine = Mock()
        def finish(*args, **kwargs):
            event.set()
            return transcript()
        engine.transcribe.side_effect = finish
        with self.assertRaises(ProcessingCancelled):
            TranscriptionPipeline(self.manager, transcriber=engine).run(self.project, cancel=event)
        self.assertFalse((self.project / TRANSCRIPT_PATH).exists())
        self.assertEqual(wav_duration_ms(self.project / AUDIO_PATH), 1000)

    def test_invalid_project_json_is_reported(self):
        (self.project / "project.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Não foi possível abrir"):
            self.manager.load_project(self.project)

    def test_orphan_results_are_not_mixed_with_new_audio(self):
        write_json(self.project / TRANSCRIPT_PATH, transcript())
        with self.assertRaisesRegex(ProcessingError, "WAV está ausente"):
            TranscriptionPipeline(self.manager).run(self.project)

    def test_wav_format_and_truncation(self):
        path = self.project / AUDIO_PATH
        make_wav(path)
        self.assertEqual(wav_duration_ms(path), 1000)
        path.write_bytes(path.read_bytes()[:100])
        with self.assertRaisesRegex(ProcessingError, "truncado"):
            wav_duration_ms(path)

    def test_existing_invalid_audio_is_not_overwritten(self):
        path = self.project / AUDIO_PATH
        path.write_bytes(b"broken")
        with self.assertRaises(ProcessingError):
            AudioExtractor(Mock()).extract(self.source, path)
        self.assertEqual(path.read_bytes(), b"broken")

    def test_missing_ffmpeg_ffprobe_and_audio(self):
        tools = FFmpegTools()
        tools.ffmpeg_path = None
        with self.assertRaisesRegex(ProcessingError, "FFmpeg"):
            AudioExtractor(tools).extract(self.source, self.project / AUDIO_PATH)
        tools.ffprobe_path = None
        with self.assertRaises(FFmpegNotFoundError):
            tools.probe(self.source)
        tools = Mock(ffmpeg_path="ffmpeg")
        tools.probe.return_value = {"audio": {"present": False}}
        with self.assertRaisesRegex(ProcessingError, "não possui faixa"):
            AudioExtractor(tools).extract(self.source, self.project / AUDIO_PATH)

    def test_failed_extraction_cleans_temporary_and_does_not_publish(self):
        tools = Mock(ffmpeg_path="ffmpeg")
        tools.probe.return_value = {"audio": {"present": True}}
        with patch("media.audio_extractor.run_media", side_effect=ProcessingError("failed")):
            with self.assertRaises(ProcessingError):
                AudioExtractor(tools).extract(self.source, self.project / AUDIO_PATH)
        self.assertEqual(list((self.project / "audio").iterdir()), [])


class EngineTests(unittest.TestCase):
    def test_environment_defaults_and_language(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(WhisperConfig.from_env(), WhisperConfig())
        with patch.dict(os.environ, {"TAKEDREAM_WHISPER_LANGUAGE": " pt "}):
            self.assertEqual(WhisperConfig.from_env().language, "pt")

    def test_adapter_consumes_lazy_segments(self):
        factory = Mock()
        factory.return_value.transcribe.return_value = (iter([segment()]), SimpleNamespace(duration=1, language="pt", language_probability=0.98))
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
            result = FasterWhisperTranscriber().transcribe("test.wav", stage=Mock(), progress=Mock())
        self.assertEqual(result, transcript())
        factory.assert_called_once_with("base", device="cpu", compute_type="int8")
        factory.return_value.transcribe.assert_called_once_with("test.wav", language=None, word_timestamps=True)

    def test_model_load_and_lazy_transcription_errors(self):
        factory = Mock(side_effect=OSError("offline"))
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
            with self.assertRaisesRegex(ProcessingError, "carregar ou baixar"):
                FasterWhisperTranscriber().transcribe("test.wav", stage=Mock(), progress=Mock())
        def broken_segments():
            yield segment()
            raise RuntimeError("decode failed")
        factory = Mock()
        factory.return_value.transcribe.return_value = (broken_segments(), SimpleNamespace(duration=1))
        with patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=factory)}):
            with self.assertRaisesRegex(ProcessingError, "Falha na transcrição"):
                FasterWhisperTranscriber().transcribe("test.wav", stage=Mock(), progress=Mock())

    def test_process_error_and_cancellation(self):
        with self.assertRaisesRegex(ProcessingError, "test failure"):
            run_media([sys.executable, "-c", "import sys; sys.stderr.write('test failure'); sys.exit(1)"])
        event = Event()
        from threading import Timer
        timer = Timer(0.3, event.set)
        timer.start()
        try:
            with self.assertRaises(ProcessingCancelled):
                run_media([sys.executable, "-c", "import time; time.sleep(20)"], event)
        finally:
            timer.join()


if __name__ == "__main__":
    unittest.main()
