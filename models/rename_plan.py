"""Modelo de dominio do plano de renomeacao: um item por arquivo a ser
copiado com um novo nome para o destino configurado.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class RenamePlanItem:
    """Um item planejado do modulo de Renomeacao."""

    caminho_original: Path
    nome_original: str
    livro: str
    pagina: int
    nome_novo: str
    caminho_destino: Path
    status: str = "Pendente"  # Pendente / Copiado / ErroCopia
    erro: str = ""
