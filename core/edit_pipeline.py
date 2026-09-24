from pathlib import Path

from core.processing import ProcessingError, check_cancelled
from core.project_manager import ProjectManager
from core.results import AUDIO_PATH, load_results
from core.storage import read_json, write_json
from editor.edit_plan import build_edit_plan, validate_edit_plan
from media.audio_extractor import wav_duration_ms
from media.ffmpeg_tools import FFmpegTools
from renderer.ffmpeg_renderer import FFmpegRenderer


EDIT_PLAN_PATH = "decisions/edit_plan.json"
DEFAULT_OUTPUT_NAME = "video_editado.mp4"


def _resolve_source(root, project):
    source = Path(project["source"]["original_path"])
    if not source.is_absolute():
        source = root / source
    return source


def _next_output_path(root):
    output_dir = Path(root) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate = output_dir / DEFAULT_OUTPUT_NAME
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = output_dir / f"video_editado-{counter}.mp4"
        if not candidate.exists():
            return candidate
        counter += 1


def load_edit_state(project_dir):
    root = Path(project_dir).expanduser().resolve()
    state = {
        "edit_plan": None,
        "output_path": None,
        "edit_errors": [],
    }

    plan_file = root / EDIT_PLAN_PATH
    if plan_file.exists():
        try:
            state["edit_plan"] = validate_edit_plan(read_json(plan_file))
        except ValueError as error:
            state["edit_errors"].append(
                f"{EDIT_PLAN_PATH}: {error}"
            )

    try:
        manager = ProjectManager()
        _, project = manager.load_project(root)
    except ValueError as error:
        state["edit_errors"].append(str(error))
        return state

    output_path = project.get("output_path")
    if isinstance(output_path, str) and output_path:
        candidate = root / output_path
        if candidate.exists() and candidate.is_file():
            state["output_path"] = output_path

    return state


class AutoEditPipeline:
    def __init__(self, manager=None, tools=None, renderer=None):
        self.manager = manager or ProjectManager()
        self.tools = tools or FFmpegTools()
        self.renderer = renderer or FFmpegRenderer(self.tools)

    def run(
        self,
        project_dir,
        *,
        cancel=None,
        stage=lambda text: None,
        progress=lambda value: None,
    ):
        root, project = self.manager.load_project(project_dir)

        stage("Validando transcrição e silêncios...")
        progress(-1)

        results = load_results(root, cancel)
        if results["errors"]:
            raise ProcessingError(
                "\n".join(results["errors"])
                + "\nCorrija os resultados inválidos antes de gerar a edição."
            )

        if results["transcript"] is None or results["silences"] is None:
            raise ProcessingError(
                "Processe o áudio e a transcrição antes de gerar a edição automática."
            )

        if results["audio_path"] is None:
            raise ProcessingError(
                "O áudio extraído não está disponível para calcular a timeline."
            )

        check_cancelled(cancel)

        edit_state = load_edit_state(root)
        if edit_state["edit_errors"]:
            raise ProcessingError(
                "\n".join(edit_state["edit_errors"])
                + "\nMova o edit_plan.json inválido para backup antes de tentar novamente."
            )

        plan = edit_state["edit_plan"]
        reused_plan = False

        if plan is not None:
            if (
                plan.get("profile") == project.get("profile")
                and plan.get("style") == project.get("style")
            ):
                reused_plan = True
            else:
                plan = None

        if plan is None:
            stage("Gerando plano de edição...")
            progress(10)
            audio_duration_ms = wav_duration_ms(root / AUDIO_PATH, cancel)
            duration_ms = audio_duration_ms

            metadata = self.manager.load_media_metadata(root)
            if metadata:
                source_seconds = metadata.get("container", {}).get(
                    "duration_seconds"
                )
                if isinstance(source_seconds, (int, float)) and source_seconds > 0:
                    duration_ms = min(
                        audio_duration_ms,
                        int(round(source_seconds * 1000)),
                    )

            plan = build_edit_plan(
                duration_ms,
                project.get("profile"),
                project.get("style"),
                results["silences"],
            )
            write_json(root / EDIT_PLAN_PATH, plan)
            self.manager.update_processing(
                root,
                "edit_planned",
                edit_plan_path=EDIT_PLAN_PATH,
                edit_cuts=plan["stats"]["cuts"],
                estimated_duration_ms=plan["stats"]["estimated_duration_ms"],
            )

        check_cancelled(cancel)

        if reused_plan and edit_state["output_path"]:
            progress(100)
            stage("Edição já renderizada. Reutilizando resultado existente.")
            results.update(
                {
                    "edit_plan": plan,
                    "output_path": edit_state["output_path"],
                    "edit_errors": [],
                    "reused_output": True,
                }
            )
            return results

        source = _resolve_source(root, project)
        if not source.exists():
            raise ProcessingError(
                "O vídeo original não foi encontrado para renderização."
            )

        destination = _next_output_path(root)

        stage(
            f"Renderizando {plan['stats']['cuts']} cortes automáticos..."
        )
        progress(-1)

        rendered = self.renderer.render(
            source,
            destination,
            plan,
            cancel=cancel,
        )

        check_cancelled(cancel)

        relative_output = str(rendered.relative_to(root)).replace("\\", "/")

        self.manager.update_processing(
            root,
            "rendered",
            edit_plan_path=EDIT_PLAN_PATH,
            output_path=relative_output,
            edit_cuts=plan["stats"]["cuts"],
            original_duration_ms=plan["source_duration_ms"],
            edited_duration_ms=plan["stats"]["estimated_duration_ms"],
        )

        progress(100)
        stage("Primeira edição automática concluída.")

        results.update(
            {
                "edit_plan": plan,
                "output_path": relative_output,
                "edit_errors": [],
                "reused_output": False,
            }
        )
        return results
