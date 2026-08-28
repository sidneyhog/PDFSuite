"""Varredura de uma pasta `livroNNNN` do acervo de escrituras.

So classificacao e organizacao - nao abre PDF nenhum (a contagem de
paginas fica no planejador). Reconhece os quatro padroes de nome que
convivem no acervo:

  - sem prefixo   : livroNNNN_folha_NNN.pdf
  - prefixo `1_`  : 1_livroNNNN_folha_NNN.pdf        -> folha
  - prefixo 2_..13_ / `pasta_` / `L.####,fls`        -> anexo
  - livroNNNN_termo_abertura.pdf / _termo_encerramento.pdf
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from models.escritura_import import ArquivoFolhaOrigem, LivroOrigem

logger = logging.getLogger("pdfsuite")

_RE_PASTA_SCAN = re.compile(r"^f\d+$", re.IGNORECASE)
_RE_PREFIXO = re.compile(r"^(\d+)_")
_RE_FOLHA_NOME = re.compile(r"(?:folha|fls\.?|livro)[_ ]+(\d{1,3})(?:[ _-]+(\d{1,3}))?", re.IGNORECASE)
_RE_GUIA = re.compile(r"^L\.\d", re.IGNORECASE)


def _folha_do_nome(nome: str) -> tuple[Optional[int], Optional[int]]:
    m = _RE_FOLHA_NOME.search(nome)
    if not m:
        return (None, None)
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    if not (1 <= a <= 420):
        return (None, None)
    if not (1 <= b <= 420):
        b = a
    return (min(a, b), max(a, b))


def _classificar(nome: str) -> str:
    """Retorna 'termo_abertura' | 'termo_encerramento' | 'folha' | 'anexo' | 'ignorar'."""
    low = nome.lower()
    if not low.endswith(".pdf"):
        return "ignorar"
    if "termo_abertura" in low:
        return "termo_abertura"
    if "termo_encerr" in low:
        return "termo_encerramento"
    if _RE_GUIA.match(nome) or low.startswith("pasta_"):
        return "anexo"
    m = _RE_PREFIXO.match(nome)
    if m:
        return "folha" if m.group(1) == "1" else "anexo"
    if "_folha_" in low:
        return "folha"
    return "ignorar"


class EscrituraScannerService:
    """Le uma pasta de livro e devolve um LivroOrigem classificado."""

    def scan_livro(self, pasta_livro: Path) -> LivroOrigem:
        numero = self._numero_do_livro(pasta_livro.name)
        termo_abertura: Optional[Path] = None
        termo_encerramento: Optional[Path] = None
        ignorados: list[Path] = []
        avisos: list[str] = []
        # folhas e anexos por pasta de scan (para casar anexo com a folha da mesma pasta)
        folhas_por_pasta: dict[str, list[Path]] = {}
        anexos_por_pasta: dict[str, list[Path]] = {}

        for arquivo in self._listar_arquivos(pasta_livro):
            pasta_scan = self._pasta_scan(arquivo, pasta_livro)
            classe = _classificar(arquivo.name)
            if classe == "termo_abertura":
                self._conferir_numero_do_termo(arquivo, numero, avisos, "abertura")
                termo_abertura = self._preferir(termo_abertura, arquivo, avisos, "abertura")
            elif classe == "termo_encerramento":
                self._conferir_numero_do_termo(arquivo, numero, avisos, "encerramento")
                termo_encerramento = self._preferir(termo_encerramento, arquivo, avisos, "encerramento")
            elif classe == "folha":
                folhas_por_pasta.setdefault(pasta_scan, []).append(arquivo)
            elif classe == "anexo":
                anexos_por_pasta.setdefault(pasta_scan, []).append(arquivo)
            else:
                ignorados.append(arquivo)

        folhas: list[ArquivoFolhaOrigem] = []
        for pasta_scan, arquivos in folhas_por_pasta.items():
            anexos = sorted(anexos_por_pasta.pop(pasta_scan, []), key=lambda p: p.name.lower())
            if len(arquivos) > 1:
                avisos.append(f"pasta '{pasta_scan}' tem {len(arquivos)} arquivos de folha")
            for indice, arq in enumerate(sorted(arquivos, key=lambda p: p.name.lower())):
                ini, fim = _folha_do_nome(arq.name)
                folhas.append(ArquivoFolhaOrigem(
                    caminho=arq,
                    pasta_scan=pasta_scan,
                    folha_nome_ini=ini,
                    folha_nome_fim=fim,
                    # anexos vao junto do PRIMEIRO arquivo de folha da pasta
                    anexos=anexos if indice == 0 else [],
                ))

        # anexos em pastas sem nenhuma folha na mesma pasta - o planejador tenta
        # rotea-los para a folha de numero igual ao da pasta 'fXXX'
        anexos_orfaos: dict[int, list[Path]] = {}
        for pasta_scan, orfaos in anexos_por_pasta.items():
            num = self._numero_pasta(pasta_scan)
            if num < 9999:
                anexos_orfaos[num] = sorted(orfaos, key=lambda p: p.name.lower())
            else:
                avisos.append(f"pasta '{pasta_scan}' tem {len(orfaos)} anexo(s) sem folha e sem numero")
                ignorados.extend(orfaos)

        folhas.sort(key=lambda f: (
            f.folha_nome_ini if f.folha_nome_ini is not None else 9999,
            self._numero_pasta(f.pasta_scan),
            f.caminho.name.lower(),
        ))

        return LivroOrigem(
            numero=numero,
            pasta=pasta_livro,
            termo_abertura=termo_abertura,
            termo_encerramento=termo_encerramento,
            folhas=folhas,
            anexos_orfaos=anexos_orfaos,
            ignorados=ignorados,
            avisos=avisos,
        )

    # ------------------------------------------------------------------ #

    @staticmethod
    def _listar_arquivos(pasta: Path):
        """Varredura iterativa (fila, sem recursao) - erro numa subpasta nao
        aborta o restante.
        """
        fila = [pasta]
        while fila:
            atual = fila.pop()
            try:
                for item in atual.iterdir():
                    if item.is_dir():
                        fila.append(item)
                    elif item.is_file():
                        yield item
            except OSError as erro:
                logger.warning("Falha ao ler '%s': %s", atual, erro)

    @staticmethod
    def _pasta_scan(arquivo: Path, pasta_livro: Path) -> str:
        rel = arquivo.relative_to(pasta_livro).parts
        if len(rel) >= 2 and _RE_PASTA_SCAN.match(rel[0]):
            return rel[0]
        return "(raiz)"

    @staticmethod
    def _numero_pasta(pasta_scan: str) -> int:
        m = re.search(r"\d+", pasta_scan)
        return int(m.group(0)) if m else 9999

    @staticmethod
    def _numero_do_livro(nome_pasta: str) -> int:
        m = re.search(r"\d+", nome_pasta)
        if not m:
            raise ValueError(f"Pasta de livro sem numero no nome: '{nome_pasta}'")
        return int(m.group(0))

    @staticmethod
    def _conferir_numero_do_termo(arquivo: Path, numero_livro: int, avisos: list[str], rotulo: str) -> None:
        m = re.search(r"livro[ _]?(\d+)", arquivo.name, re.IGNORECASE)
        if m and int(m.group(1)) != numero_livro:
            avisos.append(
                f"termo de {rotulo} '{arquivo.name}' tem numero {m.group(1)} mas esta na pasta "
                f"do livro {numero_livro} - CONFERIR se e o termo certo"
            )

    @staticmethod
    def _preferir(atual: Optional[Path], novo: Path, avisos: list[str], rotulo: str) -> Path:
        if atual is None:
            return novo
        avisos.append(f"mais de um termo de {rotulo} encontrado; usando '{atual.name}'")
        return atual
