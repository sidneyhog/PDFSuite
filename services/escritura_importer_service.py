"""Execucao de um LivroPlano: separa as paginas de folha e copia os
anexos para a arvore de destino. Nunca toca nos arquivos de origem.

Reaproveita o PdfSplitterService (abre cada PDF de origem uma vez) e o
NamingService (colisao de nome no destino nunca sobrescreve).
"""
from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from pathlib import Path

from models.escritura_import import LivroPlano
from services.naming_service import NamingService
from services.pdf_splitter_service import PdfSplitterService

logger = logging.getLogger("pdfsuite")


class EscrituraImporterService:
    def __init__(self, splitter: PdfSplitterService | None = None) -> None:
        self._splitter = splitter or PdfSplitterService()

    def executar(self, plano: LivroPlano) -> None:
        """Gera todas as folhas e anexos do plano, em ordem. Erro isolado
        por folha/anexo - um problema nunca derruba o restante do livro.
        """
        namings: dict[Path, NamingService] = {}

        def naming_da_pasta(pasta: Path) -> NamingService:
            if pasta not in namings:
                ns = NamingService()
                ns.reservar_existentes(pasta)
                namings[pasta] = ns
            return namings[pasta]

        # --- folhas: agrupa por PDF de origem para abrir cada um uma vez ---
        por_origem: dict[Path, list] = defaultdict(list)
        for folha in plano.folhas:
            por_origem[folha.origem].append(folha)

        for origem, folhas in por_origem.items():
            pedidos = []
            for folha in folhas:
                pasta = folha.caminho_destino.parent
                pasta.mkdir(parents=True, exist_ok=True)
                nome_final = naming_da_pasta(pasta).proximo_nome_disponivel(folha.nome_destino)
                folha.nome_destino = nome_final
                folha.caminho_destino = pasta / nome_final
                pedidos.append((folha.pagina_origem, folha.caminho_destino))

            resultados = self._splitter.split(origem, pedidos)
            erro_por_pagina = {pagina: erro for pagina, erro in resultados}
            for folha in folhas:
                erro = erro_por_pagina.get(folha.pagina_origem)
                if erro is None:
                    folha.status = "Gerada"
                else:
                    folha.status = "Erro"
                    folha.erro = erro
                    logger.error("Folha %d do livro %d: %s", folha.numero, plano.numero, erro)

        # --- anexos arquivo-inteiro: copia preservando metadados ---
        for anexo in plano.anexos:
            if anexo.pagina_origem is not None:
                continue
            pasta = anexo.caminho_destino.parent
            pasta.mkdir(parents=True, exist_ok=True)
            nome_final = naming_da_pasta(pasta).proximo_nome_disponivel(anexo.nome_destino)
            anexo.nome_destino = nome_final
            anexo.caminho_destino = pasta / nome_final
            try:
                shutil.copy2(anexo.origem, anexo.caminho_destino)
                anexo.status = "Copiado"
            except OSError as erro:
                anexo.status = "Erro"
                anexo.erro = str(erro)
                logger.error("Anexo '%s' do livro %d: %s", anexo.origem.name, plano.numero, erro)

        # --- anexos de 1 pagina (fluxo por codigo): extrai a pagina do PDF de origem ---
        por_origem_anexo: dict[Path, list] = defaultdict(list)
        for anexo in plano.anexos:
            if anexo.pagina_origem is not None:
                por_origem_anexo[anexo.origem].append(anexo)
        for origem, lista in por_origem_anexo.items():
            pedidos = []
            for anexo in lista:
                pasta = anexo.caminho_destino.parent
                pasta.mkdir(parents=True, exist_ok=True)
                nome_final = naming_da_pasta(pasta).proximo_nome_disponivel(anexo.nome_destino)
                anexo.nome_destino = nome_final
                anexo.caminho_destino = pasta / nome_final
                pedidos.append((anexo.pagina_origem, anexo.caminho_destino))
            erro_por_pagina = {p: e for p, e in self._splitter.split(origem, pedidos)}
            for anexo in lista:
                erro = erro_por_pagina.get(anexo.pagina_origem)
                if erro is None:
                    anexo.status = "Copiado"
                else:
                    anexo.status = "Erro"
                    anexo.erro = erro
                    logger.error("Anexo p.%s de '%s' (livro %d): %s",
                                 anexo.pagina_origem, origem.name, plano.numero, erro)
