"""Testes do NamingService: resolucao sequencial de colisao de nomes, sem
pular numeros - o mesmo bug real (gerava "(2), (4), (6)..." em vez de
"(2), (3), (4)...") que foi encontrado e corrigido no CopiarPDFs.ps1.
"""
from __future__ import annotations

from pathlib import Path

from services.naming_service import NamingService


def test_primeiro_nome_nao_e_alterado() -> None:
    naming = NamingService()
    assert naming.proximo_nome_disponivel("Contrato.pdf") == "Contrato.pdf"


def test_colisao_gera_sufixo_sequencial_sem_pular_numeros() -> None:
    naming = NamingService()
    resultados = [naming.proximo_nome_disponivel("Contrato.pdf") for _ in range(5)]
    assert resultados == [
        "Contrato.pdf",
        "Contrato (2).pdf",
        "Contrato (3).pdf",
        "Contrato (4).pdf",
        "Contrato (5).pdf",
    ]


def test_reservar_existentes_evita_sobrescrever_arquivo_de_execucao_anterior(tmp_path: Path) -> None:
    (tmp_path / "Contrato.pdf").write_bytes(b"conteudo antigo")

    naming = NamingService()
    naming.reservar_existentes(tmp_path)

    assert naming.proximo_nome_disponivel("Contrato.pdf") == "Contrato (2).pdf"


def test_nomes_diferentes_nao_colidem() -> None:
    naming = NamingService()
    assert naming.proximo_nome_disponivel("A.pdf") == "A.pdf"
    assert naming.proximo_nome_disponivel("B.pdf") == "B.pdf"
