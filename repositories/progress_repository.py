"""Persistencia do estado de execucao (checkpoint), para permitir retomar
uma varredura interrompida sem perder o trabalho ja feito - equivalente ao
progresso.json do CopiarPDFs.ps1 (PowerShell).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.pdf_record import PdfRecord, PdfStatus

logger = logging.getLogger("pdfsuite")


class ProgressRepository:
    """Le/grava progress/progresso.json (escrita atomica: arquivo temporario + rename)."""

    def __init__(self, progress_dir: Path) -> None:
        self._path = progress_dir / "progresso.json"

    def save(self, records: list[PdfRecord], arquivo_atual: str, iniciado_em: datetime) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        estado = {
            "iniciado_em": iniciado_em.isoformat(),
            "atualizado_em": datetime.now().isoformat(),
            "arquivo_atual": arquivo_atual,
            "quantidade_processada": len(records),
            "processados": [self._serialize(r) for r in records],
        }

        temp_path = self._path.with_suffix(".json.tmp")
        try:
            temp_path.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
            temp_path.replace(self._path)
        except OSError as erro:
            logger.warning("Falha ao salvar progresso: %s", erro)

    def load(self) -> Optional[list[PdfRecord]]:
        if not self._path.exists():
            return None
        try:
            estado = json.loads(self._path.read_text(encoding="utf-8"))
            return [self._deserialize(item) for item in estado["processados"]]
        except (json.JSONDecodeError, KeyError, ValueError) as erro:
            logger.warning("Arquivo de progresso corrompido, ignorando: %s", erro)
            return None

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink(missing_ok=True)

    def exists(self) -> bool:
        return self._path.exists()

    @staticmethod
    def _serialize(record: PdfRecord) -> dict:
        data = asdict(record)
        data["caminho"] = str(record.caminho)
        data["duplicado_de"] = str(record.duplicado_de) if record.duplicado_de else None
        data["modificado_em"] = record.modificado_em.isoformat()
        data["status"] = record.status.value
        return data

    @staticmethod
    def _deserialize(data: dict) -> PdfRecord:
        return PdfRecord(
            caminho=Path(data["caminho"]),
            nome=data["nome"],
            tamanho_bytes=data["tamanho_bytes"],
            modificado_em=datetime.fromisoformat(data["modificado_em"]),
            status=PdfStatus(data["status"]),
            sha256=data.get("sha256"),
            paginas=data.get("paginas"),
            livro=data.get("livro"),
            duplicado=data.get("duplicado", False),
            duplicado_de=Path(data["duplicado_de"]) if data.get("duplicado_de") else None,
            observacoes=data.get("observacoes", ""),
        )
