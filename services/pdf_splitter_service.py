"""Separacao de um PDF multipagina em arquivos de 1 pagina.

Toda a interacao com o pypdf (leitura/escrita de PDF) vive aqui - o modulo
so orquestra. Cada pagina e extraida em um try/except isolado: uma pagina
problematica nunca derruba a separacao das demais, nem dos outros arquivos.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

logger = logging.getLogger("pdfsuite")


class PdfSplitterService:
    """Extrai paginas individuais de um PDF de origem para novos arquivos."""

    def split(
        self, origem: Path, paginas_destinos: list[tuple[int, Path]]
    ) -> list[tuple[int, Optional[str]]]:
        """Abre `origem` UMA vez e grava cada pagina pedida em seu destino.

        `paginas_destinos`: lista de (numero_da_pagina_1based, caminho_destino).
        Retorna, na mesma ordem, uma lista de (numero_da_pagina, erro) onde
        `erro` e None em caso de sucesso ou a mensagem de falha daquela pagina.
        Se o proprio PDF nao puder ser aberto, todas as paginas recebem o
        mesmo erro.
        """
        try:
            reader = PdfReader(str(origem))
            if reader.is_encrypted:
                return [(p, "PDF protegido por senha.") for p, _ in paginas_destinos]
            total = len(reader.pages)
        except PdfReadError as erro:
            return [(p, f"Falha ao ler estrutura do PDF: {erro}") for p, _ in paginas_destinos]
        except (OSError, ValueError) as erro:
            return [(p, f"Erro de leitura: {erro}") for p, _ in paginas_destinos]
        except Exception as erro:  # pypdf pode levantar excecoes variadas
            logger.debug("Excecao inesperada ao abrir '%s' para separar: %s", origem, erro)
            return [(p, f"Erro inesperado ao abrir PDF: {erro}") for p, _ in paginas_destinos]

        resultados: list[tuple[int, Optional[str]]] = []
        for pagina_numero, destino in paginas_destinos:
            resultados.append(
                (pagina_numero, self._extrair_pagina(reader, total, origem, pagina_numero, destino))
            )
        return resultados

    def _extrair_pagina(
        self, reader: PdfReader, total: int, origem: Path, pagina_numero: int, destino: Path
    ) -> Optional[str]:
        if not (1 <= pagina_numero <= total):
            return f"Pagina {pagina_numero} nao existe (o PDF tem {total} pagina(s))."
        try:
            writer = PdfWriter()
            writer.add_page(reader.pages[pagina_numero - 1])
            destino.parent.mkdir(parents=True, exist_ok=True)
            with open(destino, "wb") as arquivo:
                writer.write(arquivo)
            logger.info("Pagina %d de '%s' separada em '%s'.", pagina_numero, origem, destino)
            return None
        except OSError as erro:
            return f"Falha ao gravar '{destino}': {erro}"
        except Exception as erro:  # extracao de uma pagina malformada
            logger.debug("Falha ao extrair pagina %d: %s", pagina_numero, erro)
            return f"Falha ao extrair a pagina: {erro}"
