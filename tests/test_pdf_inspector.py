"""Testes unitarios de PdfInspectorService e HasherService, isolados do
InventoryService (mais rapidos e focados que os testes de integracao)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from models.pdf_record import PdfStatus
from services.hasher_service import HasherService
from services.pdf_inspector_service import PdfInspectorService
from tests.generate_fixture_environment import generate


@pytest.fixture()
def fixtures_dir(tmp_path: Path) -> Path:
    base = tmp_path / "fixtures"
    generate(base_dir=base, limpar=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


def test_inspect_pdf_valido(fixtures_dir: Path) -> None:
    inspector = PdfInspectorService()
    status, paginas, observacoes = inspector.inspect(fixtures_dir / "Livro01" / "multiplas_paginas.pdf")
    assert status == PdfStatus.OK
    assert paginas == 5
    assert observacoes == ""


def test_inspect_pdf_corrompido(fixtures_dir: Path) -> None:
    inspector = PdfInspectorService()
    status, paginas, observacoes = inspector.inspect(fixtures_dir / "Livro01" / "corrompido.pdf")
    assert status == PdfStatus.CORROMPIDO
    assert paginas is None
    assert observacoes


def test_inspect_pdf_protegido(fixtures_dir: Path) -> None:
    inspector = PdfInspectorService()
    status, paginas, _ = inspector.inspect(fixtures_dir / "Livro02" / "protegido.pdf")
    assert status == PdfStatus.PROTEGIDO
    assert paginas is None


def test_inspect_pdf_vazio(fixtures_dir: Path) -> None:
    inspector = PdfInspectorService()
    status, paginas, _ = inspector.inspect(fixtures_dir / "Livro02" / "vazio.pdf")
    assert status == PdfStatus.VAZIO
    assert paginas == 0


def test_extract_livro_sem_padrao_retorna_none(fixtures_dir: Path) -> None:
    inspector = PdfInspectorService()
    resultado = inspector.extract_livro(fixtures_dir / "Livro01" / "1_pagina_unica.pdf", None)
    assert resultado is None


def test_extract_livro_com_padrao_configurado(tmp_path: Path) -> None:
    inspector = PdfInspectorService()
    arquivo = tmp_path / "Livro015_pagina0001.pdf"
    arquivo.write_bytes(b"")
    resultado = inspector.extract_livro(arquivo, r"Livro(?P<livro>\d+)")
    assert resultado == "015"


def test_hash_e_deterministico_e_muda_com_conteudo(tmp_path: Path) -> None:
    hasher = HasherService()
    arquivo_a = tmp_path / "a.pdf"
    arquivo_b = tmp_path / "b.pdf"
    arquivo_a.write_bytes(b"conteudo identico")
    arquivo_b.write_bytes(b"conteudo identico")
    arquivo_c = tmp_path / "c.pdf"
    arquivo_c.write_bytes(b"conteudo diferente")

    assert hasher.sha256(arquivo_a) == hasher.sha256(arquivo_b)
    assert hasher.sha256(arquivo_a) != hasher.sha256(arquivo_c)
