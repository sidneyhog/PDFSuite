"""Inspecao de um arquivo PDF: contagem de paginas e classificacao de status.

Cada inspecao e isolada (try/except por arquivo) - um PDF corrompido ou
protegido nunca derruba o restante do inventario, apenas gera um registro
com o status correspondente.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from models.pdf_record import PdfStatus

logger = logging.getLogger("pdfsuite")


class PdfInspectorService:
    """Abre um PDF e determina numero de paginas + status de saude."""

    def inspect(self, path: Path) -> tuple[PdfStatus, Optional[int], str]:
        """Retorna (status, quantidade_de_paginas, observacoes)."""
        try:
            if path.stat().st_size == 0:
                return PdfStatus.VAZIO, 0, "Arquivo com 0 bytes."

            reader = PdfReader(str(path))

            if reader.is_encrypted:
                # pypdf consegue abrir o cabecalho de PDFs protegidos, mas as
                # paginas nao ficam acessiveis sem a senha.
                return PdfStatus.PROTEGIDO, None, "PDF protegido por senha."

            paginas = len(reader.pages)
            if paginas == 0:
                return PdfStatus.VAZIO, 0, "PDF valido, porem sem paginas."

            return PdfStatus.OK, paginas, ""

        except PdfReadError as erro:
            return PdfStatus.CORROMPIDO, None, f"Falha ao ler estrutura do PDF: {erro}"
        except (OSError, ValueError) as erro:
            return PdfStatus.ERRO_LEITURA, None, f"Erro de leitura: {erro}"
        except Exception as erro:  # limite de isolamento: pypdf pode levantar excecoes
            # variadas para arquivos malformados que nao herdam de PdfReadError.
            # Um PDF ruim nunca pode derrubar o restante da varredura.
            logger.debug("Excecao inesperada ao inspecionar '%s': %s", path, erro)
            return PdfStatus.CORROMPIDO, None, f"Erro inesperado ao processar PDF: {erro}"

    def extract_livro(self, path: Path, livro_pattern: Optional[str]) -> Optional[str]:
        """Extrai o identificador do 'Livro' a partir do nome do arquivo,
        usando uma regex configuravel com grupo nomeado (?P<livro>...).
        Retorna None se nao houver padrao configurado ou nao houver match.
        """
        if not livro_pattern:
            return None
        match = re.search(livro_pattern, path.name)
        if not match:
            return None
        try:
            return match.group("livro")
        except IndexError:
            return match.group(0)
