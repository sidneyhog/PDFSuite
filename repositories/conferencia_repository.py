"""Persistencia do modulo de Conferencia: CSV de-para por livro (o que
cada pasta era e para onde foi) + um CSV-resumo da execucao.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

from models.conferencia import ConferenciaLivro

logger = logging.getLogger("pdfsuite")

_COLUNAS_LIVRO = [
    "Livro", "PastaOrigem", "Arquivo", "Classe", "LivroLido", "FolhaLida",
    "FolhaDestino", "Acao", "CaminhoDestino",
]
_COLUNAS_RESUMO = [
    "Livro", "DiagAntes", "DiagDepois", "Aplicada", "FolhasReais", "Duplicadas",
    "SemCodigo", "OutroLivro", "Faltando", "MovidoPara", "Avisos",
]


class ConferenciaRepository:
    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir

    def salvar_livro(self, res: ConferenciaLivro, timestamp: str) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        destino = self._reports_dir / f"Conferencia_livro{res.numero}_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            w = csv.writer(arquivo, delimiter=";")
            w.writerow(_COLUNAS_LIVRO)
            for it in res.itens:
                w.writerow([
                    res.numero, it.pasta_atual, it.caminho_atual.name, it.classe,
                    it.livro_lido or "", it.folha_lida or "", it.destino_folha or "",
                    it.acao, str(it.caminho_destino) if it.caminho_destino else "",
                ])
        return destino

    def salvar_resumo(self, resultados: list[ConferenciaLivro], timestamp: str) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        destino = self._reports_dir / f"Conferencia_resumo_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            w = csv.writer(arquivo, delimiter=";")
            w.writerow(_COLUNAS_RESUMO)
            for r in resultados:
                w.writerow([
                    r.numero, r.diagnostico_antes, r.diagnostico_depois,
                    "nao" if r.abortado_guard else "sim",
                    len(r.folhas_reais), sum(r.duplicadas.values()), r.sem_codigo,
                    r.outro_livro, len(r.faltando),
                    str(r.movido_para) if r.movido_para else "",
                    " | ".join(r.avisos),
                ])
        logger.info("Resumo da conferencia salvo em '%s'.", destino)
        return destino
