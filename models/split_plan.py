"""Modelo de dominio do plano de separacao: um item por PAGINA a ser
extraida de um PDF multipagina para um arquivo individual no destino.

Mesma filosofia do RenamePlanItem - os originais nunca sao tocados, cada
pagina vira um novo arquivo com nome resolvido por template + NamingService.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SplitPlanItem:
    """Um item planejado do modulo de Separacao de paginas."""

    caminho_original: Path
    nome_original: str
    livro: str  # "" quando o Inventario nao identificou um Livro para o arquivo
    paginas_total: int
    pagina_numero: int  # 1-based, na ordem fisica do PDF de origem
    nome_novo: str
    caminho_destino: Path
    status: str = "Pendente"  # Pendente / Separado / ErroSeparacao
    erro: str = ""
