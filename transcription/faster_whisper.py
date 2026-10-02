from core.processing import ProcessingCancelled, ProcessingError, check_cancelled, seconds_to_ms
from transcription.base import WhisperConfig


def serialize_segment(segment):
    return {
        "id": segment.id,
        "start_ms": seconds_to_ms(segment.start),
        "end_ms": seconds_to_ms(segment.end),
        "text": segment.text.strip(),
        "words": [{"start_ms": seconds_to_ms(word.start), "end_ms": seconds_to_ms(word.end),
                   "word": word.word, "probability": float(word.probability)}
                  for word in (segment.words or [])],
    }


class FasterWhisperTranscriber:
    def __init__(self, config=None):
        self.config = config or WhisperConfig.from_env()
        self._model = None

    def _load_model(self, *, cancel=None, stage=lambda text: None, progress=lambda value: None):
        check_cancelled(cancel)
        if self._model is not None:
            return self._model

        config = self.config
        stage("Carregando modelo Whisper (o primeiro uso pode baixar o modelo)...")
        progress(-1)
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                config.model,
                device=config.device,
                compute_type=config.compute_type,
            )
        except Exception as error:
            raise ProcessingError(
                "Não foi possível carregar ou baixar o modelo Whisper. Verifique a conexão, "
                f"o espaço em disco e a configuração do modelo/dispositivo.\n{error}"
            ) from error
        check_cancelled(cancel)
        return self._model

    def transcribe(self, audio_path, *, cancel=None, stage, progress):
        check_cancelled(cancel)
        config = self.config
        model = self._load_model(
            cancel=cancel,
            stage=stage,
            progress=progress,
        )
        check_cancelled(cancel)
        stage("Transcrevendo...")
        progress(0)
        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=config.language,
                word_timestamps=True,
            )
            saved = []
            for segment in segments:
                check_cancelled(cancel)
                saved.append(serialize_segment(segment))
                if info.duration > 0:
                    progress(min(99, int(segment.end / info.duration * 100)))
            check_cancelled(cancel)
            return {
                "schema_version": "0.1",
                "model": {
                    "name": config.model,
                    "device": config.device,
                    "compute_type": config.compute_type,
                },
                "language": {
                    "detected": info.language,
                    "probability": float(info.language_probability),
                },
                "text": " ".join(segment["text"] for segment in saved),
                "segments": saved,
            }
        except ProcessingCancelled:
            raise
        except Exception as error:
            raise ProcessingError(f"Falha na transcrição do áudio: {error}") from error
