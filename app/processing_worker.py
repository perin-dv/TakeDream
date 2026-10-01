from pathlib import Path
from threading import Event

from PySide6.QtCore import QLockFile, QThread, Signal

from core.batch_visual_analysis import BatchVisualAnalysisPipeline
from core.edit_pipeline import AutoEditPipeline, load_edit_state
from core.processing import ProcessingCancelled, ProcessingError
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

    @staticmethod
    def _library_media_count(manager, project_dir):
        library = manager.load_media_library(project_dir)
        if not isinstance(library, dict):
            return 1
        assets = library.get("assets")
        if isinstance(assets, list):
            return max(1, len(assets))
        try:
            return max(1, int(library.get("media_count", 1) or 1))
        except (TypeError, ValueError):
            return 1

    def _should_auto_wedding(self, manager, project):
        if project.get("profile") != "Casamento":
            return False
        if project.get("output_path"):
            return False
        return self._library_media_count(manager, self.project_dir) > 1

    def _mark_parent_for_auto_review(self):
        # ProjectWindow já abre a revisão automaticamente quando o modo atual é
        # "edit". Aqui apenas sincronizamos esse estado antes de emitir o
        # resultado do fluxo automático. Nenhum widget é manipulado na thread.
        parent = self.parent()
        if parent is not None and hasattr(parent, "_current_mode"):
            parent._current_mode = "edit"

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
                manager = transcription_pipeline.manager
                _, project = manager.load_project(self.project_dir)

                # Casamento multi-vídeo segue sozinho para a primeira montagem.
                # O usuário não precisa clicar separadamente em Analisar e
                # Transcrever, porque o WeddingAssembly executa apenas as etapas
                # realmente necessárias e reaproveita cache quando disponível.
                if self._should_auto_wedding(manager, project):
                    self.stage.emit(
                        "Preparando automaticamente a biblioteca e a primeira edição..."
                    )
                    self.progress.emit(1)
                    result = AutoEditPipeline(
                        manager=manager,
                        tools=transcription_pipeline.tools,
                    ).run(
                        self.project_dir,
                        cancel=self.cancel,
                        stage=self.stage.emit,
                        progress=self.progress.emit,
                    )
                    result["auto_pipeline"] = True
                    self._mark_parent_for_auto_review()
                    self.completed.emit(result)
                else:
                    results = load_results(self.project_dir, self.cancel)
                    results.update(load_edit_state(self.project_dir))
                    self.completed.emit(results)

            elif self.mode == "analyze":
                manager = transcription_pipeline.manager
                self.stage.emit("Lendo metadados do vídeo principal...")
                self.progress.emit(2)
                _, project = manager.load_project(self.project_dir)
                source = Path(project["source"]["original_path"])
                if not source.is_absolute():
                    source = self.project_dir / source

                metadata = transcription_pipeline.tools.probe(
                    source,
                    cancel=self.cancel,
                )
                manager.save_media_metadata(
                    self.project_dir,
                    metadata,
                )

                result = {"metadata": metadata}

                try:
                    library = manager.load_media_library(self.project_dir)
                    media_count = (
                        len(library.get("assets", []))
                        if isinstance(library, dict)
                        and isinstance(library.get("assets"), list)
                        else int(library.get("media_count", 0))
                        if isinstance(library, dict)
                        else 1
                    )

                    if media_count > 1:
                        self.stage.emit(
                            f"Analisando biblioteca com {media_count} vídeos..."
                        )
                        result["batch_visual_analysis"] = (
                            BatchVisualAnalysisPipeline(
                                manager=manager,
                                tools=transcription_pipeline.tools,
                            ).run(
                                self.project_dir,
                                cancel=self.cancel,
                                stage=self.stage.emit,
                                progress=self.progress.emit,
                            )
                        )
                    else:
                        result["visual_analysis"] = (
                            VisualAnalysisPipeline(
                                manager=manager,
                                tools=transcription_pipeline.tools,
                            ).run(
                                self.project_dir,
                                metadata=metadata,
                                cancel=self.cancel,
                                stage=self.stage.emit,
                                progress=self.progress.emit,
                            )
                        )
                except ProcessingCancelled:
                    raise
                except Exception as visual_error:
                    # Metadados via FFprobe são uma etapa válida por si só. Uma
                    # falha na análise visual não deve apagar esse resultado nem
                    # fazer a UI parecer que o vídeo nunca foi analisado.
                    result["visual_analysis_error"] = (
                        str(visual_error)
                        or "Não foi possível concluir a análise visual."
                    )

                self.completed.emit(result)

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
