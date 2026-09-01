"""Planejamento da importacao de um livro de escrituras GUIADO PELO CODIGO
do rodape (SP0869 + livro + folha), nao pela posicao da pagina.

Para cada pagina de cada arquivo de folha:
  - codigo do proprio livro   -> essa pagina E a folha lida (vai direto pra
    pasta certa); 2a+ ocorrencia da mesma folha -> duplicada/
  - codigo de outro livro     -> conflito (fica de fora, reportado)
  - sem codigo                -> nao e folha: vira anexo da folha corrente
    (a ultima folha lida no mesmo arquivo); se aparecer antes da 1a folha,
    espera e cola na primeira folha do arquivo

Termo de abertura = folha 1, termo de encerramento = folha N (400).
Anexos pre-existentes (2_/3_/pasta_/L.####) -> pasta da 1a folha real do
arquivo de folha da mesma pasta 'fXXX'.

Logica pura e testavel: a unica dependencia externa e uma funcao que le os
codigos de um PDF (injetada) e uma que resolve o nome do arquivo de folha.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from models.escritura_import import AnexoDestino, FolhaDestino, LivroOrigem, LivroPlano

FOLHAS_POR_LIVRO_PADRAO = 400

LerCodigos = Callable[[Path], list[Optional[tuple[int, int]]]]


class EscrituraCodigoPlannerService:
    def __init__(
        self,
        ler_codigos: LerCodigos,
        nome_destino: Callable[[int, int], str],
        folhas_por_livro: int = FOLHAS_POR_LIVRO_PADRAO,
        agrupar_por_diagnostico: bool = True,
    ) -> None:
        self._ler_codigos = ler_codigos
        self._nome_destino = nome_destino
        self._total = folhas_por_livro
        self._ultima_conteudo = folhas_por_livro - 1
        self._agrupar = agrupar_por_diagnostico

    # ------------------------------------------------------------------ #

    def planejar(self, livro: LivroOrigem, destino_raiz: Path) -> LivroPlano:
        avisos = list(livro.avisos)
        folhas: list[FolhaDestino] = []
        anexos: list[AnexoDestino] = []
        conflitos: list = []
        vistos: dict[int, int] = {}                    # folha_real -> quantas ja vistas
        folhas_reais_por_arquivo: dict[Path, list[int]] = {}

        # --- folha 1: termo de abertura ---
        if livro.termo_abertura is not None:
            folhas.append(FolhaDestino(1, "abertura", livro.termo_abertura, pagina_origem=1))
            vistos[1] = 1
        else:
            avisos.append("livro sem termo de abertura")

        # --- folhas de conteudo: uma pagina de origem por vez ---
        for arq in livro.folhas:
            codigos = self._ler_codigos(arq.caminho)
            if not codigos:
                avisos.append(f"'{arq.caminho.name}': PDF ilegivel - nenhuma pagina aproveitada")
                continue

            folha_corrente: Optional[int] = None
            pendentes: list[int] = []                  # paginas sem codigo antes da 1a folha
            for pagina, code in enumerate(codigos, start=1):
                if code is None:
                    if folha_corrente is None:
                        pendentes.append(pagina)
                    else:
                        anexos.append(AnexoDestino(
                            origem=arq.caminho, folha_destino=folha_corrente, pagina_origem=pagina))
                elif code[0] != livro.numero:
                    conflitos.append((arq.caminho, pagina, code))
                else:
                    folha_num = code[1]
                    vistos[folha_num] = vistos.get(folha_num, 0) + 1
                    dup = vistos[folha_num] > 1
                    folhas.append(FolhaDestino(
                        folha_num, self._tipo(folha_num), arq.caminho, pagina, duplicada=dup))
                    if not dup:
                        folhas_reais_por_arquivo.setdefault(arq.caminho, []).append(folha_num)
                    folha_corrente = folha_num
                    for p in pendentes:               # coladas na 1a folha do arquivo
                        anexos.append(AnexoDestino(
                            origem=arq.caminho, folha_destino=folha_num, pagina_origem=p))
                    pendentes = []

            if pendentes:                             # arquivo sem NENHUMA folha
                alvo = folha_corrente or self._folha_da_pasta(arq.pasta_scan)
                if alvo is None:
                    avisos.append(
                        f"'{arq.caminho.name}': sem codigo em nenhuma pagina e sem pasta 'fXXX' "
                        f"utilizavel - {len(pendentes)} pagina(s) NAO importada(s)")
                else:
                    for p in pendentes:
                        anexos.append(AnexoDestino(
                            origem=arq.caminho, folha_destino=alvo, pagina_origem=p))
                    avisos.append(
                        f"'{arq.caminho.name}': nenhuma pagina com codigo - {len(pendentes)} "
                        f"pagina(s) tratada(s) como anexo da folha {alvo}")

        # --- anexos pre-existentes: pasta da 1a folha real do mesmo arquivo ---
        for arq in livro.folhas:
            if not arq.anexos:
                continue
            reais = folhas_reais_por_arquivo.get(arq.caminho)
            alvo = reais[0] if reais else self._folha_da_pasta(arq.pasta_scan)
            if alvo is None:
                avisos.append(
                    f"{len(arq.anexos)} anexo(s) de '{arq.caminho.name}' sem folha de destino - conferir")
                alvo = 1
            for ax in arq.anexos:
                anexos.append(AnexoDestino(origem=ax, folha_destino=alvo))

        # --- anexos orfaos (pasta 'fXXX' sem arquivo de folha) ---
        for num_pasta, orfaos in livro.anexos_orfaos.items():
            for ax in orfaos:
                anexos.append(AnexoDestino(origem=ax, folha_destino=num_pasta))
        if livro.anexos_orfaos:
            n = sum(len(v) for v in livro.anexos_orfaos.values())
            avisos.append(f"{n} anexo(s) sem arquivo de folha na pasta - roteados pela pasta 'fXXX' (conferir)")

        # --- folha N: termo de encerramento ---
        if livro.termo_encerramento is not None:
            folhas.append(FolhaDestino(self._total, "encerramento", livro.termo_encerramento, pagina_origem=1))
            vistos[self._total] = vistos.get(self._total, 0) + 1
        else:
            avisos.append("livro sem termo de encerramento")

        # --- diagnostico a partir do que foi realmente posicionado ---
        folhas_reais = {f.numero for f in folhas if not f.duplicada}
        tem_dup = any(f.duplicada for f in folhas)
        conteudo = sorted(f for f in folhas_reais if 1 < f < self._total)
        total_conteudo = len(conteudo)
        ultima_conteudo = conteudo[-1] if conteudo else 0
        faltando = [n for n in range(2, self._ultima_conteudo + 1) if n not in folhas_reais]
        diagnostico = self._diagnosticar(folhas_reais, conteudo, tem_dup, bool(conflitos))

        if conflitos:
            avisos.append(
                f"{len(conflitos)} pagina(s) com codigo de OUTRO livro - fora do plano (ver conflitos)")
        if tem_dup:
            dups = sorted({f.numero for f in folhas if f.duplicada})
            avisos.append(f"folha(s) repetida(s): {', '.join(map(str, dups))} - copias extras em duplicada/")
        if faltando and diagnostico in ("quase", "revisar"):
            amostra = ", ".join(map(str, faltando[:15]))
            avisos.append(f"faltam {len(faltando)} folha(s): {amostra}{' ...' if len(faltando) > 15 else ''}")

        # --- destino ---
        pasta_destino = (destino_raiz / diagnostico / str(livro.numero)) if self._agrupar \
            else destino_raiz / str(livro.numero)
        for f in folhas:
            f.nome_destino = self._nome_destino(livro.numero, f.numero)
            pasta = pasta_destino / f"{f.numero:03d}"
            if f.duplicada:
                pasta = pasta / "duplicada"
            f.caminho_destino = pasta / f.nome_destino
        for a in anexos:
            if a.pagina_origem is None:
                a.nome_destino = a.origem.name
            else:
                a.nome_destino = f"{a.origem.stem}_p{a.pagina_origem:02d}.pdf"
            a.caminho_destino = pasta_destino / f"{a.folha_destino:03d}" / a.nome_destino

        return LivroPlano(
            numero=livro.numero,
            pasta_origem=livro.pasta,
            pasta_destino=pasta_destino,
            folhas=folhas,
            anexos=anexos,
            total_folhas_conteudo=total_conteudo,
            ultima_folha_conteudo=ultima_conteudo,
            diagnostico=diagnostico,
            avisos=avisos,
            conflitos=conflitos,
        )

    # ------------------------------------------------------------------ #

    def _tipo(self, folha: int) -> str:
        if folha == 1:
            return "abertura"
        if folha >= self._total:
            return "encerramento"
        return "conteudo"

    @staticmethod
    def _folha_da_pasta(pasta_scan: str) -> Optional[int]:
        m = re.search(r"\d+", pasta_scan or "")
        if not m:
            return None
        n = int(m.group(0))
        return n if 1 <= n <= 999 else None

    def _diagnosticar(
        self, folhas_reais: set, conteudo: list, tem_dup: bool, tem_conflito: bool
    ) -> str:
        tem_abertura = 1 in folhas_reais
        tem_encerr = self._total in folhas_reais
        if tem_conflito or tem_dup:
            return "revisar"
        if not conteudo:
            return "vazio"
        if len(conteudo) < (self._total - 2) * 0.9:
            return "incompleto"
        if (conteudo == list(range(2, self._ultima_conteudo + 1))
                and tem_abertura and tem_encerr):
            return "ok"
        faltando = self._ultima_conteudo - 1 - len(conteudo)
        return "quase" if faltando <= 3 else "revisar"
