"""Repositorio do modulo de Separacao: grava um CSV de rastreabilidade
(qual PDF de origem gerou qual arquivo de 1 pagina, e com qual status) -
mesmo espirito do Renomeacao_<timestamp>.csv.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from models.split_plan import SplitPlanItem

logger = logging.getLogger("pdfsuite")

_COLUNAS = [
    "CaminhoOriginal", "NomeOriginal", "Livro", "PaginasTotal", "PaginaNumero",
    "NomeNovo", "CaminhoDestino", "Status", "Erro",
]


class SplitRepository:
    """Persiste o resultado de uma execucao do modulo de Separacao."""

    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir

    def save(self, plano: list[SplitPlanItem]) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = self._reports_dir / f"Separacao_{timestamp}.csv"

        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(_COLUNAS)
            for item in plano:
                escritor.writerow([
                    str(item.caminho_original),
                    item.nome_original,
                    item.livro,
                    item.paginas_total,
                    item.pagina_numero,
                    item.nome_novo,
                    str(item.caminho_destino),
                    item.status,
                    item.erro,
                ])

        logger.info("Relatorio de separacao salvo em '%s'.", destino)
        return destino
