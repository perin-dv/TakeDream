from threading import Event

from PySide6.QtCore import QLockFile, QThread, Signal

from core.export_pipeline import ExportPipeline
from core.processing import ProcessingError
from core.review_pipeline import ReviewRenderPipeline


class ReviewWorker(QThread):
    stage = Signal(str)
    progress = Signal(int)
    completed = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        project_dir,
        mode,
        *,
        edit_plan=None,
        export_key=None,
        parent=None,
    ):
        super().__init__(parent)
        self.project_dir = project_dir
        self.mode = mode
        self.edit_plan = edit_plan
        self.export_key = export_key
        self.cancel = Event()

    def run(self):
        lock = QLockFile(str(self.project_dir / ".processing.lock"))
        lock.setStaleLockTime(0)

        try:
            if not lock.tryLock(0):
                raise ProcessingError(
                    "Este projeto já está sendo processado em outra janela."
                )

            if self.mode == "rerender":
                if self.edit_plan is None:
                    raise ProcessingError(
                        "Nenhum plano de edição foi informado."
                    )

                result = ReviewRenderPipeline().run(
                    self.project_dir,
                    self.edit_plan,
                    cancel=self.cancel,
                    stage=self.stage.emit,
                    progress=self.progress.emit,
                )
                self.completed.emit(result)

            elif self.mode == "export":
                if not self.export_key:
                    raise ProcessingError(
                        "Nenhum perfil de exportação foi selecionado."
                    )

                result = ExportPipeline().run(
                    self.project_dir,
                    self.export_key,
                    cancel=self.cancel,
                    stage=self.stage.emit,
                    progress=self.progress.emit,
                )
                self.completed.emit(result)

            else:
                raise ProcessingError(
                    f"Modo de revisão desconhecido: {self.mode}"
                )

        except Exception as error:
            self.error.emit(str(error) or "Erro inesperado na revisão.")
        finally:
            lock.unlock()
