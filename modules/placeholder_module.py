"""Modulo generico usado pelas funcionalidades ainda nao implementadas do
PDFSuite. Mantem o menu principal completo (todas as opcoes da visao do
produto ja aparecem) sem exigir codigo real antes da hora.
"""
from __future__ import annotations


class PlaceholderModule:
    """Exibe uma mensagem clara de 'ainda nao implementado' para uma
    funcionalidade planejada, em vez de falhar ou nem aparecer no menu.
    """

    def __init__(self, nome_funcionalidade: str, fase_planejada: str) -> None:
        self._nome = nome_funcionalidade
        self._fase = fase_planejada

    def run(self) -> None:
        print(f"\n{self._nome} ainda nao foi implementado.\nPlanejado para: {self._fase}.\n")
