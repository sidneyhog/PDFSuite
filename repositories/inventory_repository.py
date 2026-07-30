"""Repositorio de inventario: persiste o resultado final (CSV + JSON) e
carrega o inventario da execucao anterior para servir de cache (permite
pular re-hash/re-inspecao de arquivos que nao mudaram - o "inventario
permanente" da visao do produto: nenhum outro modulo precisa reescanear).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.pdf_record import PdfRecord, PdfStatus
from repositories.report_writer import CsvReportWriter, JsonReportWriter, ReportWriter

logger = logging.getLogger("pdfsuite")

_NOME_BASE = "Inventario"


class InventoryRepository:
    """Escreve reports/Inventario.csv + .json e le o ultimo Inventario.json
    salvo para servir de cache entre execucoes (Repository pattern - o
    InventoryService nao sabe como/onde os dados sao persistidos).
    """

    def __init__(self, reports_dir: Path, writers: Optional[list[ReportWriter]] = None) -> None:
        self._reports_dir = reports_dir
        self._writers = writers if writers is not None else [CsvReportWriter(), JsonReportWriter()]
        self._json_path = reports_dir / f"{_NOME_BASE}.json"

    def save(self, records: list[PdfRecord]) -> list[Path]:
        """Grava o inventario em todos os formatos configurados (Strategy) e
        mantem uma copia historica com timestamp do CSV, para auditoria.
        """
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        caminhos_gerados: list[Path] = []

        for writer in self._writers:
            destino = self._reports_dir / f"{_NOME_BASE}{writer.extension}"
            writer.write(records, destino)
            caminhos_gerados.append(destino)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        historico = self._reports_dir / f"{_NOME_BASE}_{timestamp}.csv"
        CsvReportWriter().write(records, historico)

        logger.info("Inventario salvo: %s", ", ".join(str(c) for c in caminhos_gerados))
        return caminhos_gerados

    def load_cache(self) -> dict[tuple[str, int, float], PdfRecord]:
        """Carrega o ultimo Inventario.json salvo e o indexa pela chave de
        cache (caminho + tamanho + mtime) de cada registro, para que o
        InventoryService possa reaproveitar arquivos que nao mudaram desde a
        ultima execucao, sem reabri-los. Duplicidade e sempre recalculada a
        cada execucao (nao faz sentido em um registro de cache isolado).
        """
        registros = self._load_registros(resetar_duplicidade=True)
        return {registro.chave_cache: registro for registro in registros}

    def load_all(self) -> list[PdfRecord]:
        """Carrega o ultimo Inventario.json salvo como uma lista simples, na
        ordem em que foi gravado - usado por outros modulos (ex: Renomeacao)
        que precisam apenas dos dados, sem reescanear nada (o "inventario
        permanente" da visao do produto).
        """
        return self._load_registros(resetar_duplicidade=False)

    def _load_registros(self, *, resetar_duplicidade: bool) -> list[PdfRecord]:
        if not self._json_path.exists():
            return []

        try:
            dados = json.loads(self._json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as erro:
            logger.warning("Falha ao ler inventario anterior '%s': %s", self._json_path, erro)
            return []

        registros: list[PdfRecord] = []
        for item in dados:
            try:
                registros.append(PdfRecord(
                    caminho=Path(item["caminho"]),
                    nome=item["nome"],
                    tamanho_bytes=item["tamanho_bytes"],
                    modificado_em=datetime.fromisoformat(item["modificado_em"]),
                    status=PdfStatus(item["status"]),
                    sha256=item.get("sha256"),
                    paginas=item.get("paginas"),
                    livro=item.get("livro"),
                    duplicado=False if resetar_duplicidade else bool(item.get("duplicado", False)),
                    duplicado_de=None if resetar_duplicidade or not item.get("duplicado_de") else Path(item["duplicado_de"]),
                    observacoes=item.get("observacoes", ""),
                ))
            except (KeyError, ValueError) as erro:
                logger.debug("Registro invalido no inventario anterior, ignorado: %s", erro)
                continue

        return registros
