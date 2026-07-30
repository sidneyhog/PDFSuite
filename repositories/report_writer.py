"""Escrita de relatorios de inventario (padrao Strategy): trocar ou
adicionar um formato de saida nao exige tocar no InventoryService nem no
InventoryRepository - basta implementar o Protocol ReportWriter. O mesmo
mecanismo sera reaproveitado depois para templates de renomeacao.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Protocol

from models.pdf_record import PdfRecord


class ReportWriter(Protocol):
    """Estrategia de escrita de um relatorio de inventario em disco."""

    extension: str

    def write(self, records: list[PdfRecord], path: Path) -> None: ...


class CsvReportWriter:
    """Grava o inventario em CSV (delimitador ';', UTF-8 com BOM - compativel com Excel pt-BR)."""

    extension = ".csv"

    _COLUNAS = [
        "Nome", "Caminho", "TamanhoBytes", "TamanhoMB", "ModificadoEm",
        "SHA256", "Paginas", "Livro", "Duplicado", "DuplicadoDe", "Status", "Observacoes",
    ]

    def write(self, records: list[PdfRecord], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(self._COLUNAS)
            for registro in records:
                escritor.writerow([
                    registro.nome,
                    str(registro.caminho),
                    registro.tamanho_bytes,
                    round(registro.tamanho_bytes / (1024 * 1024), 3),
                    registro.modificado_em.strftime("%Y-%m-%d %H:%M:%S"),
                    registro.sha256 or "",
                    registro.paginas if registro.paginas is not None else "",
                    registro.livro or "",
                    "Sim" if registro.duplicado else "Nao",
                    str(registro.duplicado_de) if registro.duplicado_de else "",
                    registro.status.value,
                    registro.observacoes,
                ])


class JsonReportWriter:
    """Grava o inventario em JSON (para integracao com outros modulos/scripts futuros)."""

    extension = ".json"

    def write(self, records: list[PdfRecord], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        dados = [
            {
                "nome": r.nome,
                "caminho": str(r.caminho),
                "tamanho_bytes": r.tamanho_bytes,
                "modificado_em": r.modificado_em.isoformat(),
                "sha256": r.sha256,
                "paginas": r.paginas,
                "livro": r.livro,
                "duplicado": r.duplicado,
                "duplicado_de": str(r.duplicado_de) if r.duplicado_de else None,
                "status": r.status.value,
                "observacoes": r.observacoes,
            }
            for r in records
        ]
        path.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
