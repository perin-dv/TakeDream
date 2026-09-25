"""Run real media tools without a console window; cancellation kills the child."""
import subprocess
import time

from core.processing import ProcessingError, check_cancelled


def _creation_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_media(command, cancel=None, timeout=None):
    check_cancelled(cancel)
    try:
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
        ) as process:
            started = time.monotonic()
            try:
                while True:
                    check_cancelled(cancel)
                    if timeout is not None and time.monotonic() - started > timeout:
                        raise ProcessingError(
                            "A ferramenta de mídia excedeu o tempo limite."
                        )
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
        raise ProcessingError(
            f"Não foi possível executar a ferramenta de mídia: {error}"
        ) from error

    check_cancelled(cancel)

    if process.returncode:
        raise ProcessingError(
            f"Falha no processamento de mídia:\n{stderr[-4000:].strip()}"
        )

    return stdout, stderr


def run_media_progress(
    command,
    *,
    duration_ms,
    progress=lambda value: None,
    cancel=None,
    timeout=None,
):
    """Run FFmpeg with -progress pipe:1 and report a 0..100 percentage."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("duration_ms deve ser um inteiro positivo.")

    check_cancelled(cancel)

    command = list(command)
    if "-progress" not in command:
        command[1:1] = ["-progress", "pipe:1", "-nostats"]

    total_us = duration_ms * 1000
    stderr_text = ""

    try:
        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_creation_flags(),
        ) as process:
            started = time.monotonic()
            last_value = -1

            try:
                while True:
                    check_cancelled(cancel)

                    if timeout is not None and time.monotonic() - started > timeout:
                        raise ProcessingError(
                            "A ferramenta de mídia excedeu o tempo limite."
                        )

                    line = process.stdout.readline()

                    if line:
                        key, separator, value = line.strip().partition("=")
                        if separator and key == "out_time_us":
                            try:
                                current_us = max(0, int(value))
                            except ValueError:
                                current_us = 0

                            percent = max(
                                0,
                                min(99, int((current_us * 100) / total_us)),
                            )

                            if percent != last_value:
                                last_value = percent
                                progress(percent)

                    elif process.poll() is not None:
                        break
                    else:
                        time.sleep(0.05)

                stderr_text = process.stderr.read() or ""

            except BaseException:
                process.kill()
                try:
                    process.communicate(timeout=2)
                except subprocess.SubprocessError:
                    pass
                raise

            return_code = process.wait()

    except OSError as error:
        raise ProcessingError(
            f"Não foi possível executar a ferramenta de mídia: {error}"
        ) from error

    check_cancelled(cancel)

    if return_code:
        raise ProcessingError(
            f"Falha no processamento de mídia:\n"
            f"{stderr_text[-4000:].strip()}"
        )

    progress(100)
    return "", stderr_text
