"""Repositorio do modulo de Renomeacao: grava um CSV de rastreabilidade
(qual arquivo original virou qual arquivo novo, e com qual status) - mesmo
espirito do Inventario_<timestamp>.csv historico.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from models.rename_plan import RenamePlanItem

logger = logging.getLogger("pdfsuite")

_COLUNAS = [
    "CaminhoOriginal", "NomeOriginal", "Livro", "Pagina",
    "NomeNovo", "CaminhoDestino", "Status", "Erro",
]


class RenameRepository:
    """Persiste o resultado de uma execucao do modulo de Renomeacao."""

    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir

    def save(self, plano: list[RenamePlanItem]) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = self._reports_dir / f"Renomeacao_{timestamp}.csv"

        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(_COLUNAS)
            for item in plano:
                escritor.writerow([
                    str(item.caminho_original),
                    item.nome_original,
                    item.livro,
                    item.pagina,
                    item.nome_novo,
                    str(item.caminho_destino),
                    item.status,
                    item.erro,
                ])

        logger.info("Relatorio de renomeacao salvo em '%s'.", destino)
        return destino
