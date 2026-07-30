"""Calculo de hash SHA-256 de arquivos, em streaming (nunca carrega o
arquivo inteiro em memoria - importante para PDFs grandes em acervos com
centenas de milhares de documentos).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024  # 1 MB por leitura


class HasherService:
    """Calcula o hash SHA-256 de um arquivo lendo em blocos."""

    def sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as arquivo:
            for bloco in iter(lambda: arquivo.read(_CHUNK_SIZE), b""):
                digest.update(bloco)
        return digest.hexdigest().upper()
