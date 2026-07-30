"""Varredura recursiva do sistema de arquivos.

Implementacao iterativa (fila), no espirito do ScanDirectories do
CopiarPDFs.ps1 (PowerShell): nunca materializa a arvore inteira em memoria
(scan() e um generator) e um erro de permissao/rede em uma pasta nao aborta
a varredura das demais - so aquela pasta e pulada, com aviso no log.
"""
from __future__ import annotations

import logging
import os
import re
from collections import deque
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("pdfsuite")


class ScannerService:
    """Varre uma arvore de diretorios e produz os arquivos que casam com um filtro."""

    def __init__(self) -> None:
        self.pastas_escaneadas = 0
        self.arquivos_analisados = 0

    def scan(self, origem: Path, filtro: str) -> Iterator[Path]:
        """Gera, sob demanda, os caminhos de arquivo cujo NOME casa com `filtro`
        (regex, case-insensitive) dentro da arvore `origem`.
        """
        self.pastas_escaneadas = 0
        self.arquivos_analisados = 0
        padrao = re.compile(filtro, re.IGNORECASE)

        pendentes: deque[Path] = deque([origem])

        while pendentes:
            pasta_atual = pendentes.popleft()
            self.pastas_escaneadas += 1

            try:
                with os.scandir(pasta_atual) as iterador:
                    entradas = list(iterador)
            except (PermissionError, OSError) as erro:
                logger.warning("Sem permissao/erro ao listar '%s': %s. Pulando.", pasta_atual, erro)
                continue

            for entrada in entradas:
                try:
                    if entrada.is_dir(follow_symlinks=False):
                        pendentes.append(Path(entrada.path))
                    elif entrada.is_file(follow_symlinks=False):
                        self.arquivos_analisados += 1
                        if padrao.search(entrada.name):
                            yield Path(entrada.path)
                except OSError as erro:
                    logger.warning("Falha ao inspecionar item '%s': %s. Ignorando.", entrada.path, erro)
