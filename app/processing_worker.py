from threading import Event

from PySide6.QtCore import QLockFile, QThread, Signal

from core.processing import ProcessingError
from core.results import load_results
from core.transcription_pipeline import TranscriptionPipeline


class ProcessingWorker(QThread):
    stage = Signal(str)
    progress = Signal(int)
    completed = Signal(dict)
    error = Signal(str)

    def __init__(self, project_dir, mode="process", parent=None):
        super().__init__(parent)
        self.project_dir = project_dir
        self.mode = mode
        self.cancel = Event()

    def run(self):
        lock = QLockFile(str(self.project_dir / ".processing.lock"))
        # A transcription can take hours. Only a dead owner's lock is stale.
        lock.setStaleLockTime(0)
        try:
            if not lock.tryLock(0):
                raise ProcessingError("Este projeto já está em processamento em outra janela ou instância.")
            pipeline = TranscriptionPipeline()
            if self.mode == "load":
                results = load_results(self.project_dir, self.cancel)
                self.completed.emit(results)
            elif self.mode == "analyze":
                _, project = pipeline.manager.load_project(self.project_dir)
                source = self.project_dir / project["source"]["original_path"]
                metadata = pipeline.tools.probe(source, cancel=self.cancel)
                pipeline.manager.save_media_metadata(self.project_dir, metadata)
                self.completed.emit({"metadata": metadata})
            else:
                result = pipeline.run(self.project_dir, cancel=self.cancel,
                                      stage=self.stage.emit, progress=self.progress.emit)
                self.completed.emit(result)
        except Exception as error:
            self.error.emit(str(error) or "Erro inesperado no processamento.")
        finally:
            lock.unlock()
