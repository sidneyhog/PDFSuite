"""Modelos do modulo de Conferencia de folhas pelo codigo do rodape.

A conferencia roda sobre a saida do modulo de importacao (arvore
`<destino>/<diagnostico>/<livro>/<NNN>/...`) e corrige a numeracao usando
o codigo real lido de cada pagina.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ItemConferido:
    """Um arquivo PDF encontrado numa pasta de folha da saida."""

    caminho_atual: Path
    pasta_atual: int                 # numero da pasta onde estava (ex: 8)
    eh_folha_gerada: bool            # True = arquivo <livro>_folha_NNN.pdf; False = anexo pre-existente
    livro_lido: Optional[int] = None
    folha_lida: Optional[int] = None
    classe: str = ""                 # 'folha' | 'anexo' | 'outro_livro' | 'sem_codigo'
    destino_folha: Optional[int] = None   # em que folha (numero) ele deve ficar
    caminho_destino: Optional[Path] = None
    acao: str = ""                   # 'mantem' | 'move' | 'vira_anexo' | 'duplicada' | 'conflito'


@dataclass
class ConferenciaLivro:
    """Resultado da conferencia de um livro."""

    numero: int
    pasta_livro: Path
    diagnostico_antes: str
    itens: list[ItemConferido] = field(default_factory=list)
    folhas_reais: set[int] = field(default_factory=set)
    duplicadas: dict[int, int] = field(default_factory=dict)   # folha -> quantas copias extras
    faltando: list[int] = field(default_factory=list)
    outro_livro: int = 0
    sem_codigo: int = 0
    diagnostico_depois: str = ""
    movido_para: Optional[Path] = None      # se o livro mudou de pasta de diagnostico
    avisos: list[str] = field(default_factory=list)
