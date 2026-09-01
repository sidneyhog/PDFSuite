"""Persistencia do modulo de tratamento de conflitos (opcao 13)."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from services.escritura_conflito_service import ConflitoResultado, Divergencia

logger = logging.getLogger("pdfsuite")


class EscrituraConflitoRepository:
    def __init__(self, reports_dir: Path) -> None:
        self._dir = reports_dir

    def salvar_conflitos(self, res: ConflitoResultado, timestamp: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        destino = self._dir / f"Conflitos_tratados_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["LivroPastaErrada", "LivroCorreto", "Folha", "Acao", "Status",
                        "Motivo", "Origem", "Destino"])
            for it in res.itens:
                w.writerow([
                    it.livro_pasta_errada, it.livro_correto, it.folha, it.acao,
                    it.status or "-", it.motivo, str(it.origem),
                    str(it.destino) if it.destino else "",
                ])
            for livro, (antes, depois, movido) in sorted(res.livros_rediagnosticados.items()):
                w.writerow([livro, livro, "-", "rediagnostico", "OK",
                            f"{antes} -> {depois}", "", str(movido) if movido else ""])
        logger.info("Conflitos tratados salvos em '%s'.", destino)
        return destino

    def salvar_validacao(self, divs: list[Divergencia], timestamp: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        destino = self._dir / f"Validacao_saida_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Livro", "Folha", "Tipo", "Detalhe"])
            for d in divs:
                w.writerow([d.livro, d.folha, d.tipo, d.detalhe])
        logger.info("Validacao da saida salva em '%s' (%d divergencia(s)).", destino, len(divs))
        return destino
