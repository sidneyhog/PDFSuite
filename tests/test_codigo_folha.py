"""Testes da leitura do codigo do rodape (SP0869 + livro + folha)."""
from __future__ import annotations

import pytest

from services.codigo_folha_service import _extrair, _extrair_ocr


@pytest.mark.parametrize("texto, esperado", [
    ("SP08691083140", (1083, 140)),                 # formato antigo: SP0869 + LLLL + FFF
    ("SP0869001103150", (1103, 150)),               # formato novo: SP0869 + 00 + LLLL + FFF
    ("SP0869001103001", (1103, 1)),                 # termo de abertura
    ("SP0869001103400", (1103, 400)),               # termo de encerramento
    ("... rodape SP 0869 0011 45150 ...".replace(" ", ""), (1145, 150)),
    ("blablabla\nSP08691083394\noutra linha", (1083, 394)),
])
def test_extrai_livro_e_folha(texto, esperado):
    assert _extrair(texto) == esperado


@pytest.mark.parametrize("texto", [
    "",
    "ATESTADO\nPROCURACAO",                          # anexo, sem codigo
    "REPUBLICA FEDERATIVA DO BRASIL",
    "SP0869123",                                     # curto demais
    "SP99991083140",                                 # prefixo errado
])
def test_sem_codigo_retorna_none(texto):
    assert _extrair(texto) is None


@pytest.mark.parametrize("texto, esperado", [
    ("SP08691083140", (1083, 140)),                  # OCR perfeito
    ("SP0869 001103 150", (1103, 150)),              # espacos do OCR
    ("SPO8691O83l40", (1083, 140)),                  # O->0, l->1 no trecho
    ("5P08691O83l40", (1083, 140)),                  # S->5 no prefixo
    ("Folha n. 007  SP0869 0011 03 001", (1103, 1)), # ruido antes do codigo
    ("sp0869oo11o616o", (1106, 160)),                # tudo minusculo + O no lugar de 0
])
def test_extrai_ocr_tolerante(texto, esperado):
    assert _extrair_ocr(texto) == esperado


@pytest.mark.parametrize("texto", [
    "",
    "ATESTADO PROCURACAO SEM NUMERO",
    "2 TABELIAO DE RIO CLARO",
    "data 16/01/2015 pagina 3",                      # numeros, mas sem 869+cauda
])
def test_ocr_sem_codigo_retorna_none(texto):
    assert _extrair_ocr(texto) is None
