"""Shared cancellation and integer timestamp contract, independent of Qt."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class ProcessingError(RuntimeError):
    pass


class ProcessingCancelled(ProcessingError):
    pass


def check_cancelled(cancel=None):
    if cancel is not None and cancel.is_set():
        raise ProcessingCancelled("Processamento interrompido. As etapas concluídas foram preservadas.")


def seconds_to_ms(seconds):
    try:
        value = Decimal(str(seconds))
        if not value.is_finite() or value < 0:
            raise ValueError("O tempo deve ser finito e não negativo.")
        return int((value * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError) as error:
        raise ValueError("Tempo inválido.") from error
