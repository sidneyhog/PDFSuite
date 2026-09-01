"""Utilitario: compacta uma lista de inteiros em faixas contiguas.

    [2, 3, 4, 7, 9, 10] -> "2-4, 7, 9-10"
"""
from __future__ import annotations


def faixas(numeros: list[int]) -> str:
    if not numeros:
        return ""
    numeros = sorted(set(numeros))
    partes: list[str] = []
    ini = ant = numeros[0]
    for n in numeros[1:]:
        if n == ant + 1:
            ant = n
            continue
        partes.append(str(ini) if ini == ant else f"{ini}-{ant}")
        ini = ant = n
    partes.append(str(ini) if ini == ant else f"{ini}-{ant}")
    return ", ".join(partes)
