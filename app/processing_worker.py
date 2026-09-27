from threading import Event

from PySide6.QtCore import QLockFile, QThread, Signal

from core.edit_pipeline import AutoEditPipeline, load_edit_state
from core.processing import ProcessingError
from core.results import load_results
from core.transcription_pipeline import TranscriptionPipeline
from core.visual_analysis_pipeline import VisualAnalysisPipeline


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
        lock.setStaleLockTime(0)

        try:
            if not lock.tryLock(0):
                raise ProcessingError(
                    "Este projeto já está em processamento em outra janela ou instância."
                )

            transcription_pipeline = TranscriptionPipeline()

            if self.mode == "load":
                results = load_results(self.project_dir, self.cancel)
                results.update(load_edit_state(self.project_dir))
                self.completed.emit(results)

            elif self.mode == "analyze":
                self.stage.emit("Lendo metadados do vídeo...")
                self.progress.emit(2)
                _, project = transcription_pipeline.manager.load_project(
                    self.project_dir
                )
                source = self.project_dir / project["source"]["original_path"]
                metadata = transcription_pipeline.tools.probe(
                    source,
                    cancel=self.cancel,
                )
                transcription_pipeline.manager.save_media_metadata(
                    self.project_dir,
                    metadata,
                )

                visual_analysis = VisualAnalysisPipeline(
                    manager=transcription_pipeline.manager,
                    tools=transcription_pipeline.tools,
                ).run(
                    self.project_dir,
                    metadata=metadata,
                    cancel=self.cancel,
                    stage=self.stage.emit,
                    progress=self.progress.emit,
                )
                self.completed.emit(
                    {
                        "metadata": metadata,
                        "visual_analysis": visual_analysis,
                    }
                )

            elif self.mode == "edit":
                pipeline = AutoEditPipeline()
                result = pipeline.run(
                    self.project_dir,
                    cancel=self.cancel,
                    stage=self.stage.emit,
                    progress=self.progress.emit,
                )
                self.completed.emit(result)

            else:
                result = transcription_pipeline.run(
                    self.project_dir,
                    cancel=self.cancel,
                    stage=self.stage.emit,
                    progress=self.progress.emit,
                )
                result.update(load_edit_state(self.project_dir))
                self.completed.emit(result)

        except Exception as error:
            self.error.emit(str(error) or "Erro inesperado no processamento.")
        finally:
            lock.unlock()
