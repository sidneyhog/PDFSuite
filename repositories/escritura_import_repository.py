"""Persistencia do modulo de Importacao de escrituras:

  - CSV de rastreabilidade por livro (origem -> destino, folha a folha)
  - CSV-resumo consolidado da execucao
  - controle de retomada (livros ja concluidos)
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from models.escritura_import import LivroPlano

logger = logging.getLogger("pdfsuite")

_COLUNAS_LIVRO = [
    "Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
    "Origem", "PaginaOrigem", "Status", "Erro",
]
_COLUNAS_RESUMO = [
    "Livro", "Diagnostico", "PastaSaida", "FolhasConteudo", "UltimaFolha",
    "FolhasGeradas", "AnexosCopiados", "Erros", "Avisos",
]


class EscrituraImportRepository:
    def __init__(
        self, reports_dir: Path, progress_dir: Path,
        progress_nome: str = "escritura_importacao.json",
    ) -> None:
        self._reports_dir = reports_dir
        self._progress_path = progress_dir / progress_nome

    # ---------------- retomada ---------------- #

    def concluidos(self) -> set[int]:
        if not self._progress_path.exists():
            return set()
        try:
            dados = json.loads(self._progress_path.read_text(encoding="utf-8"))
            return {int(n) for n in dados.get("concluidos", [])}
        except (json.JSONDecodeError, OSError, ValueError) as erro:
            logger.warning("Progresso de importacao ilegivel (%s) - recomecando.", erro)
            return set()

    def marcar_concluido(self, numero_livro: int) -> None:
        atuais = self.concluidos()
        atuais.add(numero_livro)
        self._progress_path.parent.mkdir(parents=True, exist_ok=True)
        self._progress_path.write_text(
            json.dumps({"concluidos": sorted(atuais)}, indent=2), encoding="utf-8"
        )

    # ---------------- rastreabilidade ---------------- #

    def salvar_livro(self, plano: LivroPlano) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = self._reports_dir / f"Importacao_livro{plano.numero}_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(_COLUNAS_LIVRO)
            for f in plano.folhas:
                escritor.writerow([
                    plano.numero, f.numero, f.tipo,
                    f.caminho_destino.parent.name if f.caminho_destino else "",
                    f.nome_destino, str(f.origem), f.pagina_origem, f.status, f.erro,
                ])
            for a in plano.anexos:
                escritor.writerow([
                    plano.numero, a.folha_destino, "anexo",
                    a.caminho_destino.parent.name if a.caminho_destino else "",
                    a.nome_destino, str(a.origem), a.pagina_origem or "", a.status, a.erro,
                ])
            for origem, pagina, (livro_lido, folha_lida) in getattr(plano, "conflitos", []):
                escritor.writerow([
                    plano.numero, "", "conflito", "", "",
                    str(origem), pagina, "Fora do plano",
                    f"codigo do livro {livro_lido} folha {folha_lida}",
                ])
        logger.info("Rastreabilidade do livro %d salva em '%s'.", plano.numero, destino)
        return destino

    def salvar_resumo(self, planos: list[LivroPlano], timestamp: str) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        destino = self._reports_dir / f"Importacao_resumo_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(_COLUNAS_RESUMO)
            for p in planos:
                geradas = sum(1 for f in p.folhas if f.status == "Gerada")
                anexos_ok = sum(1 for a in p.anexos if a.status == "Copiado")
                erros = sum(1 for f in p.folhas if f.status == "Erro") + \
                    sum(1 for a in p.anexos if a.status == "Erro")
                escritor.writerow([
                    p.numero, p.diagnostico, str(p.pasta_destino),
                    p.total_folhas_conteudo, p.ultima_folha_conteudo,
                    geradas, anexos_ok, erros, " | ".join(p.avisos),
                ])
        logger.info("Resumo da importacao salvo em '%s'.", destino)
        return destino
