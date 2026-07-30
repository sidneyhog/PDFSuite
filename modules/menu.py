"""Menu principal do PDFSuite: loop de interacao + registro de opcoes
(padrao Factory/Registry) - adicionar uma funcionalidade nova e registrar
uma linha em main.py, sem tocar neste loop (Open/Closed Principle).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

_BANNER = """
=========================================
              PDF SUITE
========================================="""


@dataclass
class MenuOption:
    numero: str
    rotulo: str
    executar: Callable[[], None]


class Menu:
    """Loop de menu de console generico, orientado por uma lista de opcoes."""

    def __init__(self, opcoes: list[MenuOption], sair_numero: str = "0") -> None:
        self._opcoes = opcoes
        self._sair_numero = sair_numero

    def run(self) -> None:
        while True:
            self._exibir()
            escolha = input("\nEscolha uma opcao: ").strip()

            if escolha == self._sair_numero:
                print("\nAte logo!\n")
                return

            opcao = self._encontrar(escolha)
            if opcao is None:
                print("\nOpcao invalida. Tente novamente.\n")
                continue

            try:
                opcao.executar()
            except KeyboardInterrupt:
                print("\nOperacao interrompida pelo usuario.\n")
            except Exception as erro:  # nunca deixar o menu principal cair por erro de um modulo
                print(f"\nErro inesperado em '{opcao.rotulo}': {erro}\n")

    def _exibir(self) -> None:
        print(_BANNER)
        for opcao in self._opcoes:
            print(f"{opcao.numero} - {opcao.rotulo}")
        print(f"{self._sair_numero} - Sair")

    def _encontrar(self, numero: str) -> Optional[MenuOption]:
        for opcao in self._opcoes:
            if opcao.numero == numero:
                return opcao
        return None
