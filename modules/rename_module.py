"""Modulo 'Renomear PDFs' - renomeacao baseada em templates configuraveis
(ex: {Livro}_{Pagina}). Ainda nao implementado - ver docs/ARCHITECTURE.md.
"""
from __future__ import annotations

from modules.placeholder_module import PlaceholderModule


class RenameModule(PlaceholderModule):
    def __init__(self) -> None:
        super().__init__("Renomeacao de PDFs (templates configuraveis)", "proxima sessao")
