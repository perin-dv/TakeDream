from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.results import (AUDIO_PATH, TRANSCRIPT_PATH, SILENCES_PATH, load_results,
                          validate_transcript, validate_silences)
from core.storage import write_json
from media.audio_extractor import AudioExtractor
from media.ffmpeg_tools import FFmpegTools
from media.silence_detector import SilenceDetector
from transcription.base import Transcriber
from transcription.faster_whisper import FasterWhisperTranscriber


class TranscriptionPipeline:
    def __init__(self, manager=None, tools=None, transcriber: Transcriber | None = None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.transcriber = transcriber or FasterWhisperTranscriber()

    def run(self, project_dir, *, cancel=None, stage=lambda text: None, progress=lambda value: None):
        root, project = self.manager.load_project(project_dir)
        stage("Validando resultados existentes...")
        progress(-1)
        results = load_results(root, cancel)
        if results["errors"]:
            raise ProcessingError("\n".join(results["errors"]) +
                                  "\nMova o arquivo inválido para um backup antes de tentar novamente.")
        check_cancelled(cancel)
        if results["audio_path"] is None:
            # Do not mix transcripts with a newly extracted, potentially different audio.
            if results["transcript"] is not None or results["silences"] is not None:
                raise ProcessingError("Há resultados salvos, mas o WAV está ausente. Restaure o WAV "
                                      "ou mova os resultados para um backup antes de reprocessar.")
            stage("Extraindo áudio...")
            source = Path(project["source"]["original_path"])
            if not source.is_absolute():
                source = root / source
            AudioExtractor(self.tools).extract(source, root / AUDIO_PATH, cancel)
        self.manager.update_processing(root, "audio_extracted", audio_path=AUDIO_PATH)
        check_cancelled(cancel)
        if results["transcript"] is None:
            transcript = self.transcriber.transcribe(root / AUDIO_PATH, cancel=cancel, stage=stage, progress=progress)
            check_cancelled(cancel)
            stage("Salvando transcrição...")
            validate_transcript(transcript)
            write_json(root / TRANSCRIPT_PATH, transcript)
            results["transcript"] = transcript
        self.manager.update_processing(root, "transcription_ready", transcription_path=TRANSCRIPT_PATH)
        check_cancelled(cancel)
        if results["silences"] is None:
            stage("Detectando silêncios...")
            progress(-1)
            silences = SilenceDetector(self.tools).detect(root / AUDIO_PATH, cancel)
            check_cancelled(cancel)
            validate_silences(silences)
            write_json(root / SILENCES_PATH, silences)
            results["silences"] = silences
        self.manager.update_processing(root, "transcribed", silences_path=SILENCES_PATH)
        results["audio_path"] = AUDIO_PATH
        progress(100)
        stage("Concluído.")
        return results
