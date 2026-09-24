"""Run real media tools without a console window; cancellation kills the child."""
import subprocess
import time

from core.processing import ProcessingError, check_cancelled


def run_media(command, cancel=None, timeout=None):
    check_cancelled(cancel)
    try:
        with subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ) as process:
            started = time.monotonic()
            try:
                while True:
                    check_cancelled(cancel)
                    if timeout is not None and time.monotonic() - started > timeout:
                        raise ProcessingError("A ferramenta de mídia excedeu o tempo limite.")
                    try:
                        stdout, stderr = process.communicate(timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except BaseException:
                process.kill()
                process.communicate()
                raise
    except OSError as error:
        raise ProcessingError(f"Não foi possível executar a ferramenta de mídia: {error}") from error
    check_cancelled(cancel)
    if process.returncode:
        raise ProcessingError(f"Falha no processamento de mídia:\n{stderr[-4000:].strip()}")
    return stdout, stderr
