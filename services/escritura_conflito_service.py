"""Tratamento dos conflitos da importacao por codigo (opcao 13).

Conflito = pagina cujo codigo do rodape e de OUTRO livro (foi arquivada
na pasta errada no servidor). A opcao 11 deixa essas paginas de fora e as
lista. Aqui a gente resolve: se a folha do codigo FALTA no livro certo,
copia a pagina de origem para la.

Nunca apaga nada. Os originais no servidor ficam intocados (so leitura).
"""
from __future__ import annotations

import csv
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from models.escritura_relatorio import RelatorioEscrituras
from services.codigo_folha_service import CodigoFolhaService
from services.escritura_relatorio_service import _RE_ANEXO, EscrituraRelatorioService
from services.pdf_splitter_service import PdfSplitterService

logger = logging.getLogger("pdfsuite")


@dataclass
class ConflitoItem:
    livro_pasta_errada: int          # livro em cuja pasta a pagina estava
    livro_correto: int               # livro do codigo
    folha: int
    origem: Path                     # arquivo no servidor
    situacao: str
    destino: Optional[Path] = None   # para onde vai (se acao == copiar)
    acao: str = "pular"              # 'copiar' | 'pular'
    motivo: str = ""
    status: str = ""                 # preenchido no executar: 'OK' | 'ERRO' | 'PULADO'


@dataclass
class ConflitoResultado:
    itens: list = field(default_factory=list)
    livros_rediagnosticados: dict = field(default_factory=dict)   # livro -> (antes, depois, movido_para)


@dataclass
class Divergencia:
    livro: int
    folha: str
    tipo: str            # 'faltando_no_disco' | 'origem_sumiu' | 'sem_registro_csv'
    detalhe: str


class EscrituraConflitoService:
    def __init__(
        self,
        leitor: CodigoFolhaService,
        relatorio: Optional[EscrituraRelatorioService] = None,
        splitter: Optional[PdfSplitterService] = None,
        folhas_por_livro: int = 400,
    ) -> None:
        self._leitor = leitor
        self._relatorio = relatorio or EscrituraRelatorioService(folhas_por_livro)
        self._splitter = splitter or PdfSplitterService()
        self._total = folhas_por_livro

    # ------------------------------------------------------------------ #

    def analisar(self, base_dir: Path, reports_dir: Path) -> list[ConflitoItem]:
        rel = self._relatorio.gerar(base_dir, reports_dir)
        pasta_por_livro = {lv.numero: lv.pasta for lv in rel.livros}
        presentes = {lv.numero: set(lv.folhas_presentes) for lv in rel.livros}
        itens: list[ConflitoItem] = []
        for lv in rel.livros:
            for folha_lida, livro_cod, origem, _pagina, situacao, _acao in lv.conflitos:
                itens.append(self._montar(
                    lv.numero, folha_lida, livro_cod, origem, situacao,
                    pasta_por_livro, presentes,
                ))
        return itens

    def _montar(self, livro_errado, folha_lida, livro_cod, origem, situacao,
                pasta_por_livro, presentes) -> ConflitoItem:
        try:
            alvo, folha = int(livro_cod), int(folha_lida)
        except (TypeError, ValueError):
            return ConflitoItem(livro_errado, 0, 0, Path(origem), situacao,
                                motivo="codigo ilegivel")
        it = ConflitoItem(livro_errado, alvo, folha, Path(origem), situacao)
        if alvo not in pasta_por_livro:
            it.motivo = f"livro {alvo} nao esta na saida"
        elif folha in presentes.get(alvo, ()):
            it.motivo = f"folha {folha} ja existe no {alvo} - conferir duplicidade"
        elif not it.origem.exists():
            it.motivo = f"origem nao encontrada: {it.origem}"
        else:
            it.destino = pasta_por_livro[alvo] / f"{folha:03d}" / f"{alvo}_folha_{folha:03d}.pdf"
            it.acao = "copiar"
            it.motivo = f"folha {folha} falta no {alvo}"
        return it

    # ------------------------------------------------------------------ #

    def executar(self, itens: list[ConflitoItem], base_dir: Path,
                 reports_dir: Optional[Path] = None) -> ConflitoResultado:
        res = ConflitoResultado(itens=itens)
        afetados: set[int] = set()
        resolvidos: list[ConflitoItem] = []
        for it in itens:
            if it.acao != "copiar" or it.destino is None:
                it.status = "PULADO"
                continue
            ok, msg = self._copiar(it)
            it.status = "OK" if ok else "ERRO"
            it.motivo = msg
            if ok:
                afetados.add(it.livro_correto)
                resolvidos.append(it)

        if reports_dir is not None:
            self._marcar_resolvidos_no_csv(resolvidos, reports_dir)

        for livro in sorted(afetados):
            mudou = self._rediagnosticar(livro, base_dir, reports_dir or base_dir)
            if mudou:
                res.livros_rediagnosticados[livro] = mudou
        return res

    def _copiar(self, it: ConflitoItem) -> tuple[bool, str]:
        it.destino.parent.mkdir(parents=True, exist_ok=True)
        if it.destino.exists():
            return False, "destino ja existe"
        try:
            from pypdf import PdfReader
            n_pag = len(PdfReader(str(it.origem)).pages)
        except Exception as erro:
            return False, f"nao consegui abrir a origem: {erro}"
        if n_pag == 1:
            try:
                shutil.copy2(it.origem, it.destino)
            except OSError as erro:
                return False, f"falha ao copiar: {erro}"
            return True, "copiado (1 pagina)"
        # multipagina: acha a(s) pagina(s) com o codigo certo
        codigos = self._leitor.identificar_paginas(it.origem)
        paginas = [i + 1 for i, c in enumerate(codigos) if c == (it.livro_correto, it.folha)]
        if not paginas:
            return False, f"origem tem {n_pag} paginas, nenhuma com codigo {it.livro_correto}/{it.folha}"
        erro = self._splitter.split(it.origem, [(paginas[0], it.destino)])[0][1]
        if erro:
            return False, erro
        return True, f"extraida pagina {paginas[0]} de {n_pag}"

    # ------------------------------------------------------------------ #

    def validar(self, base_dir: Path, reports_dir: Path, checar_origem: bool = False) -> list[Divergencia]:
        """Cruza o que os CSV de rastreabilidade dizem que foi gerado com o
        que esta de fato no disco (e, opcionalmente, se a origem ainda
        existe na rede). So relata - nao corrige.
        """
        rel = self._relatorio.gerar(base_dir, base_dir)
        pasta_por_livro = {lv.numero: lv.pasta for lv in rel.livros}
        divs: list[Divergencia] = []
        for lv in rel.livros:
            csv_path = self._relatorio._ultimo_csv(reports_dir, f"Importacao_livro{lv.numero}_*.csv")
            if csv_path is None:
                continue
            registrados: set[str] = set()
            try:
                linhas = list(csv.DictReader(csv_path.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
            except OSError:
                continue
            for lin in linhas:
                tipo = (lin.get("Tipo") or "").strip()
                folha = (lin.get("FolhaDestino") or "").strip()
                nome = (lin.get("NomeDestino") or "").strip()
                origem = (lin.get("Origem") or "").strip()
                status = (lin.get("Status") or "").strip().lower()
                if tipo in ("conteudo", "abertura", "encerramento") and folha.isdigit() and status == "gerada":
                    registrados.add(nome or f"{lv.numero}_folha_{int(folha):03d}.pdf")
                    caminho = lin.get("CaminhoDestino") or ""
                    alvo = Path(caminho) if caminho else pasta_por_livro[lv.numero] / f"{int(folha):03d}" / nome
                    if not alvo.exists():
                        divs.append(Divergencia(lv.numero, folha, "faltando_no_disco",
                                                f"CSV diz gerada, arquivo ausente: {alvo}"))
                if checar_origem and origem and not Path(origem).exists():
                    divs.append(Divergencia(lv.numero, folha or "-", "origem_sumiu",
                                            f"origem nao esta mais na rede: {origem}"))
            # arquivos de folha no disco sem linha no CSV
            for sub in pasta_por_livro[lv.numero].iterdir():
                if not (sub.is_dir() and sub.name.isdigit()):
                    continue
                for pdf in sub.glob("*.pdf"):
                    if _RE_ANEXO.match(pdf.name):
                        continue
                    if pdf.name not in registrados:
                        divs.append(Divergencia(lv.numero, sub.name, "sem_registro_csv",
                                                f"arquivo no disco sem linha no CSV: {pdf}"))
        return divs

    def _marcar_resolvidos_no_csv(self, resolvidos: list[ConflitoItem], reports_dir: Path) -> None:
        """Marca a linha 'conflito' como resolvida no CSV de rastreabilidade do
        livro em cuja pasta a pagina estava (para nao contar mais como pendencia).
        """
        por_livro: dict[int, list[ConflitoItem]] = {}
        for it in resolvidos:
            por_livro.setdefault(it.livro_pasta_errada, []).append(it)
        for livro, its in por_livro.items():
            csv_path = self._relatorio._ultimo_csv(reports_dir, f"Importacao_livro{livro}_*.csv")
            if csv_path is None:
                continue
            origens = {str(it.origem) for it in its}
            destinos = {str(it.origem): str(it.destino) for it in its}
            try:
                linhas = list(csv.DictReader(csv_path.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
                campos = list(linhas[0].keys()) if linhas else []
            except OSError:
                continue
            mudou = False
            for lin in linhas:
                if (lin.get("Tipo") or "").strip() == "conflito" and (lin.get("Origem") or "").strip() in origens:
                    lin["Status"] = "Resolvido"
                    lin["Erro"] = f"{lin.get('Erro', '')} -> movido para {destinos.get(lin['Origem'], '')}"
                    mudou = True
            if mudou and campos:
                with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=campos, delimiter=";")
                    w.writeheader()
                    w.writerows(linhas)

    def _rediagnosticar(self, livro: int, base_dir: Path, reports_dir: Path) -> Optional[tuple]:
        rel: RelatorioEscrituras = self._relatorio.gerar(base_dir, reports_dir)
        lv = next((x for x in rel.livros if x.numero == livro), None)
        if lv is None or not lv.diagnostico or lv.diagnostico == lv.diagnostico_real:
            return None
        alvo = base_dir / lv.diagnostico_real / str(livro)
        if alvo.exists():
            return (lv.diagnostico, lv.diagnostico_real, None)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(lv.pasta), str(alvo))
        except OSError as erro:
            logger.warning("Nao movi o livro %d: %s", livro, erro)
            return (lv.diagnostico, lv.diagnostico_real, None)
        return (lv.diagnostico, lv.diagnostico_real, alvo)
