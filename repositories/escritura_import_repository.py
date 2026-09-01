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
from typing import Optional

from models.escritura_import import LivroPlano

logger = logging.getLogger("pdfsuite")

_COLUNAS_LIVRO = [
    "Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
    "Origem", "PaginaOrigem", "Status", "Erro", "CaminhoDestino",
]
_COLUNAS_RESUMO = [
    "Livro", "Diagnostico", "PastaSaida", "FolhasConteudo", "UltimaFolha",
    "FolhasGeradas", "AnexosCopiados", "Erros", "FolhasFaltando",
    "FolhasDuplicadas", "Conflitos", "Avisos",
]
_COLUNAS_PENDENCIAS = ["Livro", "Diagnostico", "Tipo", "Folha", "Detalhe"]


def _faixas(numeros: list[int]) -> str:
    """[2,3,4,7,9,10] -> '2-4, 7, 9-10' (compacta faixas contiguas)."""
    if not numeros:
        return ""
    numeros = sorted(set(numeros))
    partes: list[str] = []
    ini = ant = numeros[0]
    for n in numeros[1:]:
        if n == ant + 1:
            ant = n
            continue
        partes.append(str(ini) if ini == ant else f"{ini}-{ant}")
        ini = ant = n
    partes.append(str(ini) if ini == ant else f"{ini}-{ant}")
    return ", ".join(partes)


class EscrituraImportRepository:
    def __init__(
        self, reports_dir: Path, progress_dir: Path,
        progress_nome: str = "escritura_importacao.json",
        folhas_por_livro: int = 400,
    ) -> None:
        self._reports_dir = reports_dir
        self._progress_path = progress_dir / progress_nome
        self._total = folhas_por_livro

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
                pasta = f.caminho_destino.parent.name if f.caminho_destino else ""
                if f.duplicada and f.caminho_destino:
                    pasta = f"{f.caminho_destino.parent.parent.name}/duplicada"
                escritor.writerow([
                    plano.numero, f.numero, "duplicada" if f.duplicada else f.tipo,
                    pasta, f.nome_destino, str(f.origem), f.pagina_origem, f.status, f.erro,
                    str(f.caminho_destino) if f.caminho_destino else "",
                ])
            for a in plano.anexos:
                escritor.writerow([
                    plano.numero, a.folha_destino, "anexo",
                    a.caminho_destino.parent.name if a.caminho_destino else "",
                    a.nome_destino, str(a.origem), a.pagina_origem or "", a.status, a.erro,
                    str(a.caminho_destino) if a.caminho_destino else "",
                ])
            for origem, pagina, (livro_lido, folha_lida) in getattr(plano, "conflitos", []):
                escritor.writerow([
                    plano.numero, folha_lida, "conflito", "", "",
                    str(origem), pagina, "Fora do plano",
                    f"codigo do livro {livro_lido} folha {folha_lida}", "",
                ])
        logger.info("Rastreabilidade do livro %d salva em '%s'.", plano.numero, destino)
        return destino

    @staticmethod
    def _folhas_faltando(plano: LivroPlano, total: int) -> list[int]:
        presentes = {f.numero for f in plano.folhas if not f.duplicada and f.status != "Erro"}
        return [n for n in range(1, total + 1) if n not in presentes]

    @staticmethod
    def _folhas_duplicadas(plano: LivroPlano) -> dict[int, int]:
        contagem: dict[int, int] = {}
        for f in plano.folhas:
            if f.duplicada:
                contagem[f.numero] = contagem.get(f.numero, 0) + 1
        return contagem

    def salvar_resumo(self, planos: list[LivroPlano], timestamp: str) -> Path:
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        destino = self._reports_dir / f"Importacao_resumo_{timestamp}.csv"
        total = self._total
        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(_COLUNAS_RESUMO)
            for p in planos:
                geradas = sum(1 for f in p.folhas if f.status == "Gerada")
                anexos_ok = sum(1 for a in p.anexos if a.status == "Copiado")
                erros = sum(1 for f in p.folhas if f.status == "Erro") + \
                    sum(1 for a in p.anexos if a.status == "Erro")
                faltando = self._folhas_faltando(p, total)
                dups = self._folhas_duplicadas(p)
                escritor.writerow([
                    p.numero, p.diagnostico, str(p.pasta_destino),
                    p.total_folhas_conteudo, p.ultima_folha_conteudo,
                    geradas, anexos_ok, erros,
                    _faixas(faltando), _faixas(sorted(dups)), len(getattr(p, "conflitos", [])),
                    " | ".join(p.avisos),
                ])
        logger.info("Resumo da importacao salvo em '%s'.", destino)
        self._salvar_pendencias(planos, timestamp, total)
        return destino

    def _salvar_pendencias(self, planos: list[LivroPlano], timestamp: str, total: int) -> Optional[Path]:
        """Um arquivo dedicado, uma linha por pendencia (folha faltando,
        duplicada, conflito, termo ausente) - para o escrevente filtrar/pivotar.
        So e gerado se houver ao menos uma pendencia.
        """
        linhas: list[list] = []
        for p in planos:
            for folha in self._folhas_faltando(p, total):
                rotulo = {1: "termo de abertura", total: "termo de encerramento"}.get(folha, "")
                linhas.append([p.numero, p.diagnostico, "faltando", folha, rotulo])
            for folha, extra in sorted(self._folhas_duplicadas(p).items()):
                linhas.append([p.numero, p.diagnostico, "duplicada", folha,
                               f"{extra} copia(s) extra em {p.pasta_destino}\\{folha:03d}\\duplicada"])
            for origem, pagina, (livro_lido, folha_lida) in getattr(p, "conflitos", []):
                linhas.append([p.numero, p.diagnostico, "conflito", folha_lida,
                               f"codigo do livro {livro_lido} - {origem} p.{pagina}"])
        if not linhas:
            return None
        destino = self._reports_dir / f"Importacao_pendencias_{timestamp}.csv"
        with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(_COLUNAS_PENDENCIAS)
            escritor.writerows(linhas)
        logger.info("Pendencias da importacao salvas em '%s' (%d linha(s)).", destino, len(linhas))
        return destino
