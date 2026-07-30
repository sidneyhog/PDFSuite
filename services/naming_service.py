"""Resolucao de colisao de nomes de arquivo: garante que um nome final
nunca sobrescreva outro, adicionando um sufixo sequencial " (N)" quando
necessario.

Equivalente Python do Get-NextAvailableName do CopiarPDFs.ps1 (PowerShell) -
mesmo algoritmo, ja corrigido la para nunca pular numeros (evita o bug real
que gerava "(2), (4), (6)..." em vez de "(2), (3), (4)...").
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


class NamingService:
    """Reserva nomes de arquivo unicos dentro de um destino, evitando
    qualquer sobrescrita - inclusive entre execucoes diferentes, desde que
    `reservar_existentes()` seja chamado antes de planejar os nomes novos.
    """

    def __init__(self, reservados: Optional[dict[str, int]] = None) -> None:
        self._reservados: dict[str, int] = reservados if reservados is not None else {}

    def reservar_existentes(self, pasta: Path) -> None:
        """Pre-popula as reservas com os arquivos ja existentes na pasta de
        destino, para que a primeira colisao gere o sufixo correto em vez de
        tentar sobrescrever um arquivo de uma execucao anterior.
        """
        if not pasta.exists():
            return
        for item in pasta.iterdir():
            if item.is_file():
                self._reservados[item.name] = 1

    def proximo_nome_disponivel(self, nome_base: str) -> str:
        """Retorna `nome_base` se ainda nao estiver reservado, ou
        "nome (N).ext" com o proximo N sequencial disponivel.
        """
        if nome_base not in self._reservados:
            self._reservados[nome_base] = 1
            return nome_base

        extensao = Path(nome_base).suffix
        nome_sem_extensao = Path(nome_base).stem
        contador = self._reservados[nome_base] + 1

        while True:
            candidato = f"{nome_sem_extensao} ({contador}){extensao}"
            if candidato not in self._reservados:
                break
            contador += 1

        self._reservados[candidato] = 1
        self._reservados[nome_base] = contador
        return candidato
