"""Estatisticas agregadas de uma execucao do modulo de Inventario."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InventoryStats:
    pastas_escaneadas: int = 0
    arquivos_analisados: int = 0
    pdfs_encontrados: int = 0
    total_bytes: int = 0
    total_paginas: int = 0
    duplicados: int = 0
    corrompidos: int = 0
    protegidos: int = 0
    vazios: int = 0
    reaproveitados_do_cache: int = 0
    tempo_execucao_seg: float = 0.0
