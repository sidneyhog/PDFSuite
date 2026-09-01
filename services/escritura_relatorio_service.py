"""Le a arvore de saida da importacao de escrituras (ja processada) e os
CSV de rastreabilidade, e consolida num RelatorioEscrituras para o
escrevente. NAO abre PDF, NAO reprocessa - so olha o que ja esta no disco.
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.escritura_relatorio import LivroRelatorio, RelatorioEscrituras

logger = logging.getLogger("pdfsuite")

_DIAGS = ("ok", "quase", "revisar", "manual", "incompleto", "vazio")
_RE_NUM = re.compile(r"^\d+$")
_RE_ANEXO = re.compile(r"^(anexo_|pasta_|L\.|\d{1,2}_)", re.IGNORECASE)


class EscrituraRelatorioService:
    def __init__(self, folhas_por_livro: int = 400) -> None:
        self._total = folhas_por_livro

    def gerar(self, base_dir: Path, reports_dir: Path) -> RelatorioEscrituras:
        rel = RelatorioEscrituras(
            base_dir=base_dir,
            gerado_em=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        for numero, diag, pasta in self._descobrir(base_dir):
            rel.livros.append(self._analisar(numero, diag, pasta, reports_dir))
        rel.livros.sort(key=lambda lv: lv.numero)
        self._pos_processar(rel)
        return rel

    def _pos_processar(self, rel: RelatorioEscrituras) -> None:
        """Recalcula o diagnostico real (do que esta no disco) e cruza cada
        conflito: a folha do codigo falta no livro certo? ja existe?
        """
        presentes_por_livro = {lv.numero: set(lv.folhas_presentes) for lv in rel.livros}
        pasta_por_livro = {lv.numero: lv.pasta for lv in rel.livros}
        for lv in rel.livros:
            lv.diagnostico_real = self._diag_real(lv)
            novos = []
            for folha_lida, livro_cod, origem, pagina, *_ in lv.conflitos:
                situacao, acao = self._analisar_conflito(folha_lida, livro_cod, presentes_por_livro, pasta_por_livro)
                novos.append((folha_lida, livro_cod, origem, pagina, situacao, acao))
            lv.conflitos = novos

    def _analisar_conflito(self, folha_lida, livro_cod, presentes_por_livro, pasta_por_livro):
        try:
            alvo, folha = int(livro_cod), int(folha_lida)
        except (TypeError, ValueError):
            return "codigo ilegivel", "conferir manualmente"
        if alvo not in presentes_por_livro:
            return f"livro {alvo} nao processado", f"conferir livro {alvo}"
        if folha in presentes_por_livro[alvo]:
            return f"folha ja existe no {alvo}", "conferir duplicidade"
        destino = pasta_por_livro[alvo] / f"{folha:03d}" / f"{alvo}_folha_{folha:03d}.pdf"
        return f"FALTA no {alvo}", f"copiar para {destino}"

    def _diag_real(self, lv: LivroRelatorio) -> str:
        presentes = set(lv.folhas_presentes)
        conteudo = sorted(f for f in presentes if 1 < f < self._total)
        if lv.conflitos or lv.duplicadas:
            return "revisar"
        if not conteudo:
            return "vazio"
        if len(conteudo) < (self._total - 2) * 0.9:
            return "incompleto"
        if (conteudo == list(range(2, self._total)) and 1 in presentes and self._total in presentes):
            return "ok"
        faltam = (self._total - 1) - 1 - len(conteudo)
        return "quase" if faltam <= 3 else "revisar"

    # ------------------------------------------------------------------ #

    def _descobrir(self, base_dir: Path) -> list[tuple[int, str, Path]]:
        achados: list[tuple[int, str, Path]] = []
        for diag in _DIAGS:
            pdiag = base_dir / diag
            if not pdiag.is_dir():
                continue
            for item in pdiag.iterdir():
                if item.is_dir() and _RE_NUM.match(item.name):
                    achados.append((int(item.name), diag, item))
        if not achados:                       # arvore sem agrupamento por diagnostico
            for item in base_dir.iterdir():
                if item.is_dir() and _RE_NUM.match(item.name):
                    achados.append((int(item.name), "", item))
        return sorted(achados)

    def _analisar(self, numero: int, diag: str, pasta: Path, reports_dir: Path) -> LivroRelatorio:
        lr = LivroRelatorio(numero=numero, diagnostico=diag, pasta=pasta)

        for sub in sorted(pasta.iterdir(), key=lambda p: p.name):
            if not (sub.is_dir() and _RE_NUM.match(sub.name)):
                if sub.is_dir() and sub.name == "_conflitos":
                    for p in sub.glob("*.pdf"):
                        lr.avisos.append(f"arquivo solto em _conflitos/: {p.name}")
                continue
            n = int(sub.name)
            pdfs = list(sub.glob("*.pdf"))
            folha_files = [p for p in pdfs if not _RE_ANEXO.match(p.name)]
            anexo_files = [p for p in pdfs if _RE_ANEXO.match(p.name)]
            if folha_files:
                lr.folhas_presentes.append(n)
                if len(folha_files) > 1:
                    lr.avisos.append(f"pasta {n:03d} tem {len(folha_files)} arquivos de folha")
            elif anexo_files:
                lr.folhas_sem_arquivo.append(n)
            if anexo_files:
                lr.anexos_por_folha[n] = len(anexo_files)
            dup = sub / "duplicada"
            if dup.is_dir():
                qtd = len(list(dup.glob("*.pdf")))
                if qtd:
                    lr.duplicadas[n] = qtd

        lr.folhas_presentes.sort()
        presentes = set(lr.folhas_presentes)
        lr.folhas_faltando = [n for n in range(1, self._total + 1) if n not in presentes]
        lr.tem_abertura = 1 in presentes
        lr.tem_encerramento = self._total in presentes

        csv_path = self._ultimo_csv(reports_dir, f"Importacao_livro{numero}_*.csv")
        if csv_path is not None:
            lr.csv_rastreio = csv_path
            self._ler_rastreio(csv_path, lr)

        return lr

    @staticmethod
    def _ultimo_csv(reports_dir: Path, padrao: str) -> Optional[Path]:
        if not reports_dir.is_dir():
            return None
        achados = sorted(reports_dir.glob(padrao))
        return achados[-1] if achados else None

    @staticmethod
    def _ler_rastreio(csv_path: Path, lr: LivroRelatorio) -> None:
        try:
            linhas = list(csv.DictReader(csv_path.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
        except OSError as erro:
            lr.avisos.append(f"nao consegui ler '{csv_path.name}': {erro}")
            return
        for lin in linhas:
            tipo = (lin.get("Tipo") or "").strip()
            folha = (lin.get("FolhaDestino") or "").strip()
            origem = (lin.get("Origem") or "").strip()
            if tipo == "conflito":
                if (lin.get("Status") or "").strip().lower().startswith("resolv"):
                    continue                       # ja tratado pela opcao 13
                det = lin.get("Erro") or ""
                m = re.search(r"livro (\d+)", det)
                lr.conflitos.append((folha, m.group(1) if m else "", origem, (lin.get("PaginaOrigem") or "").strip()))
            elif tipo in ("conteudo", "abertura", "encerramento") and folha.isdigit():
                lr.origem_por_folha.setdefault(int(folha), origem)
            if (lin.get("Status") or "").strip().lower() == "erro":
                lr.erros.append((folha, origem, (lin.get("Erro") or "").strip()))
