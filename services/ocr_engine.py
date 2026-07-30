"""Interface (Protocol) para um motor de OCR futuro.

Nao ha implementacao real ainda - apenas o contrato que qualquer modulo
futuro (ex: renomeacao automatica a partir do conteudo lido) podera
programar contra, sem acoplamento a uma biblioteca especifica de OCR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class OcrEngine(Protocol):
    """Contrato de um motor de OCR: le um PDF e extrai texto por pagina."""

    def extract_text(self, path: Path) -> list[str]:
        """Retorna uma lista com o texto extraido de cada pagina do PDF."""
        ...


class UnavailableOcrEngine:
    """Implementacao stub: qualquer chamada informa que o recurso ainda nao
    foi implementado, em vez de falhar silenciosamente ou com um traceback
    confuso. Sera substituida por um motor real quando o OCR for priorizado.
    """

    def extract_text(self, path: Path) -> list[str]:
        raise NotImplementedError(
            "OCR ainda nao foi implementado no PDFSuite. Esta interface existe "
            "para que modulos futuros ja possam ser programados contra ela."
        )
