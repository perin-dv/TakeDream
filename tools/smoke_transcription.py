"""Opt-in end-to-end Qt/FFmpeg/Whisper smoke. Never run by unittest discovery."""
import argparse
import json
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.windows.project_window import ProjectWindow
from core.project_manager import ProjectManager
from core.results import AUDIO_PATH, TRANSCRIPT_PATH, SILENCES_PATH, load_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--projects-root", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    manager = ProjectManager(args.projects_root)
    project = manager.create_project("Real pipeline smoke", args.video, "YouTube", "Clean")
    window = ProjectWindow(project)
    window.show()
    ticks = []
    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()

    def wait_worker():
        # Pump the real GUI event loop, including its deferred startup load.
        app.processEvents()
        while window.worker is not None:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()

    wait_worker()
    window.process_button.click()
    window.worker.stage.connect(print)
    failures = []
    # Avoid a modal dialog in this command-line smoke; surface errors as a failure.
    window.worker.error.disconnect(window._processing_error)
    window.worker.error.connect(failures.append)
    wait_worker()
    if failures:
        raise RuntimeError("\n".join(failures))
    results = load_results(project)
    assert not results["errors"], results["errors"]
    assert results["transcript"]["segments"], "Use a video with audible speech."
    assert all(isinstance(segment["start_ms"], int) for segment in results["transcript"]["segments"])
    assert any(segment["words"] for segment in results["transcript"]["segments"])
    assert manager.load_project(project)[1]["status"] == "transcribed"
    assert len(ticks) > 1, "Qt event loop did not stay responsive."
    paths = [project / path for path in (AUDIO_PATH, TRANSCRIPT_PATH, SILENCES_PATH)]
    before = [path.stat().st_mtime_ns for path in paths]
    window.close()
    window = ProjectWindow(project)
    window.show()
    wait_worker()
    assert "Transcrição: OK" in window.result_label.text()
    # Clicking again must also reuse valid files, without reloading Whisper.
    window.process_button.click()
    wait_worker()
    assert before == [path.stat().st_mtime_ns for path in paths]
    print(json.dumps({"project": str(project), "language": results["transcript"]["language"],
                      "segments": len(results["transcript"]["segments"]),
                      "words": sum(len(s["words"]) for s in results["transcript"]["segments"]),
                      "silences": results["silences"]["silences"],
                      "gui_timer_ticks": len(ticks), "reopen_and_reuse": "OK",
                      "text": results["transcript"]["text"]}, ensure_ascii=False, indent=2))
    timer.stop()
    window.close()


if __name__ == "__main__":
    main()
