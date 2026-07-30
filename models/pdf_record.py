"""Modelos de dominio relacionados a um unico arquivo PDF inventariado.

Camada mais interna da arquitetura (Clean Architecture): nao depende de
nenhuma outra camada do projeto.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class PdfStatus(str, Enum):
    """Classificacao de um PDF apos a inspecao (PdfInspectorService)."""

    OK = "OK"
    CORROMPIDO = "Corrompido"
    PROTEGIDO = "Protegido"
    VAZIO = "Vazio"
    ERRO_LEITURA = "ErroLeitura"


@dataclass
class PdfRecord:
    """Registro de inventario de um unico arquivo PDF."""

    caminho: Path
    nome: str
    tamanho_bytes: int
    modificado_em: datetime
    status: PdfStatus
    sha256: Optional[str] = None
    paginas: Optional[int] = None
    livro: Optional[str] = None
    duplicado: bool = False
    duplicado_de: Optional[Path] = None
    observacoes: str = ""

    @property
    def chave_cache(self) -> tuple[str, int, float]:
        """Identidade usada para decidir se o registro pode ser reaproveitado
        de uma execucao anterior do Inventario sem reabrir o arquivo:
        caminho + tamanho + data de modificacao. Se qualquer um mudar, o
        arquivo e tratado como novo/alterado e reinspecionado.
        """
        return (str(self.caminho), self.tamanho_bytes, self.modificado_em.timestamp())
