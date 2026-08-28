"""Planejamento da importacao de um livro de escrituras: transforma um
LivroOrigem (arquivos de folha + anexos + termos) num LivroPlano (uma
folha de destino por pasta numerada).

Logica pura e testavel - a unica dependencia externa e uma funcao que
conta as paginas de um PDF (injetada) e uma que resolve o nome do
arquivo de destino a partir do numero da folha.

Regra de numeracao (confirmada com o cartorio):
  - folha 1   = termo de abertura
  - folhas 2..399 = conteudo (paginas dos arquivos de folha, em ordem)
  - folha 400 = termo de encerramento
Cada arquivo de folha com N paginas ocupa N folhas consecutivas; seus
anexos vao para a pasta da PRIMEIRA dessas folhas.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from models.escritura_import import AnexoDestino, FolhaDestino, LivroOrigem, LivroPlano

FOLHAS_POR_LIVRO_PADRAO = 400   # folha 1 = abertura, folha N = encerramento


class EscrituraPlannerService:
    def __init__(
        self,
        contar_paginas: Callable[[Path], int],
        nome_destino: Callable[[int, int], str],
        folhas_por_livro: int = FOLHAS_POR_LIVRO_PADRAO,
        agrupar_por_diagnostico: bool = False,
    ) -> None:
        self._contar_paginas = contar_paginas
        self._nome_destino = nome_destino          # (numero_livro, numero_folha) -> nome do arquivo
        self._total = folhas_por_livro
        self._ultima_conteudo_esperada = folhas_por_livro - 1   # 399
        self._conteudo_esperado = folhas_por_livro - 2          # 398
        self._agrupar = agrupar_por_diagnostico

    def planejar(self, livro: LivroOrigem, destino_raiz: Path) -> LivroPlano:
        avisos = list(livro.avisos)
        folhas: list[FolhaDestino] = []
        anexos: list[AnexoDestino] = []

        # --- folha 1: termo de abertura ---
        if livro.termo_abertura is not None:
            folhas.append(FolhaDestino(numero=1, tipo="abertura",
                                       origem=livro.termo_abertura, pagina_origem=1))
        else:
            avisos.append("livro sem termo de abertura")

        # --- folhas 2..N: conteudo ---
        proxima = 2
        max_paginas_arquivo = 0
        arquivos_grandes = 0
        arquivos_fora_do_nome = 0
        primeiro_desvio = ""
        for arq in livro.folhas:
            n = max(0, int(self._contar_paginas(arq.caminho)))
            if n == 0:
                avisos.append(f"'{arq.caminho.name}': nao foi possivel contar as paginas - ignorado")
                continue
            max_paginas_arquivo = max(max_paginas_arquivo, n)
            if n >= 12:
                arquivos_grandes += 1
            primeira = proxima
            for pagina in range(1, n + 1):
                folhas.append(FolhaDestino(numero=proxima, tipo="conteudo",
                                           origem=arq.caminho, pagina_origem=pagina))
                proxima += 1
            if arq.folha_nome_ini is not None and abs(arq.folha_nome_ini - primeira) > 2:
                arquivos_fora_do_nome += 1
                if not primeiro_desvio:
                    primeiro_desvio = (
                        f"'{arq.caminho.name}' (nome: folha {arq.folha_nome_ini}, "
                        f"caiu na {primeira})"
                    )
            for origem_anexo in arq.anexos:
                anexos.append(AnexoDestino(origem=origem_anexo, folha_destino=primeira))

        if arquivos_grandes:
            avisos.append(
                f"{arquivos_grandes} arquivo(s) de folha com 12+ paginas - folha + anexos no mesmo PDF?"
            )
        if arquivos_fora_do_nome:
            avisos.append(
                f"{arquivos_fora_do_nome} arquivo(s) de folha cairam numa folha diferente do nome, "
                f"a partir de {primeiro_desvio} - conferir o CSV"
            )

        ultima_conteudo = proxima - 1
        total_conteudo = max(0, ultima_conteudo - 1)   # folhas 2..ultima

        # anexos orfaos (pasta 'fXXX' so com anexos): vao para a folha XXX se ela existir
        folhas_existentes = {f.numero for f in folhas}
        orfaos_perdidos = 0
        orfaos_roteados = 0
        for num_pasta, lista in sorted(livro.anexos_orfaos.items()):
            if num_pasta in folhas_existentes:
                for origem_anexo in lista:
                    anexos.append(AnexoDestino(origem=origem_anexo, folha_destino=num_pasta))
                orfaos_roteados += len(lista)
            else:
                orfaos_perdidos += len(lista)
        if orfaos_roteados:
            avisos.append(
                f"{orfaos_roteados} anexo(s) estavam numa pasta 'fXXX' sem arquivo de folha - "
                "roteados para a folha de mesmo numero da pasta (conferir)"
            )
        if orfaos_perdidos:
            avisos.append(
                f"{orfaos_perdidos} anexo(s) em pastas 'fXXX' sem folha correspondente no plano - NAO importados"
            )

        # --- folha final: termo de encerramento ---
        if livro.termo_encerramento is not None:
            if ultima_conteudo >= self._total:
                avisos.append(
                    f"conteudo terminou na folha {ultima_conteudo}: colide com a folha "
                    f"{self._total} (encerramento) - livro precisa de revisao"
                )
            else:
                folhas.append(FolhaDestino(numero=self._total, tipo="encerramento",
                                           origem=livro.termo_encerramento, pagina_origem=1))
        else:
            avisos.append("livro sem termo de encerramento")

        diagnostico = self._diagnosticar(
            livro, ultima_conteudo, total_conteudo, max_paginas_arquivo
        )

        # destino: opcionalmente agrupado por diagnostico, para o escrevente
        # saber de cara o que e o que (destino/ok/1103/, destino/quase/1085/, ...)
        pasta_destino = destino_raiz / diagnostico / str(livro.numero) if self._agrupar \
            else destino_raiz / str(livro.numero)

        # nomes e caminhos de destino
        for f in folhas:
            f.nome_destino = self._nome_destino(livro.numero, f.numero)
            f.caminho_destino = pasta_destino / f"{f.numero:03d}" / f.nome_destino
        for a in anexos:
            a.nome_destino = a.origem.name
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
        )

    def _diagnosticar(
        self, livro: LivroOrigem, ultima_conteudo: int, total_conteudo: int,
        max_paginas_arquivo: int,
    ) -> str:
        if not livro.folhas or total_conteudo == 0:
            return "vazio"
        if total_conteudo < self._conteudo_esperado * 0.9:
            return "incompleto"
        dif = ultima_conteudo - self._ultima_conteudo_esperada
        tem_termos = bool(livro.termo_abertura and livro.termo_encerramento)
        if dif == 0 and tem_termos:
            return "ok"
        if max_paginas_arquivo >= 30 or dif >= 50:
            return "manual"
        if abs(dif) <= 3:
            return "quase"
        return "revisar"
