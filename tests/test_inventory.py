"""Testes automatizados do modulo de Inventario (InventoryService), usando
o ambiente ficticio gerado por generate_fixture_environment.py.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from models.config import AppConfig
from models.pdf_record import PdfStatus
from services.hasher_service import HasherService
from services.inventory_service import InventoryService
from services.pdf_inspector_service import PdfInspectorService
from services.scanner_service import ScannerService
from tests.generate_fixture_environment import generate


@pytest.fixture()
def fixtures_dir(tmp_path: Path) -> Path:
    base = tmp_path / "fixtures"
    generate(base_dir=base, limpar=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture()
def service() -> InventoryService:
    return InventoryService(ScannerService(), HasherService(), PdfInspectorService())


def _build(service: InventoryService, origem: Path, cache=None, **overrides):
    config = AppConfig(origem=origem, enable_hash=True, threads=4, **overrides)
    return service.build(config, cache=cache or {})


def test_encontra_todos_os_pdfs(service: InventoryService, fixtures_dir: Path) -> None:
    registros, stats = _build(service, fixtures_dir)
    assert stats.pdfs_encontrados == 7
    assert stats.pastas_escaneadas == 3  # raiz + Livro01 + Livro02
    assert len(registros) == 7


def test_classifica_status_corretamente(service: InventoryService, fixtures_dir: Path) -> None:
    registros, _ = _build(service, fixtures_dir)
    por_nome = {r.nome: r for r in registros}

    assert por_nome["1_pagina_unica.pdf"].status == PdfStatus.OK
    assert por_nome["1_pagina_unica.pdf"].paginas == 1
    assert por_nome["multiplas_paginas.pdf"].status == PdfStatus.OK
    assert por_nome["multiplas_paginas.pdf"].paginas == 5
    assert por_nome["corrompido.pdf"].status == PdfStatus.CORROMPIDO
    assert por_nome["protegido.pdf"].status == PdfStatus.PROTEGIDO
    assert por_nome["vazio.pdf"].status == PdfStatus.VAZIO


def test_detecta_duplicados_por_conteudo(service: InventoryService, fixtures_dir: Path) -> None:
    registros, stats = _build(service, fixtures_dir)
    por_nome = {r.nome: r for r in registros}

    assert stats.duplicados == 1
    assert por_nome["duplicado_copia.pdf"].duplicado is True
    assert por_nome["duplicado_original.pdf"].duplicado is False
    assert por_nome["duplicado_copia.pdf"].duplicado_de == por_nome["duplicado_original.pdf"].caminho


def test_reaproveita_do_cache_quando_nada_muda(service: InventoryService, fixtures_dir: Path) -> None:
    registros_1, stats_1 = _build(service, fixtures_dir)
    assert stats_1.reaproveitados_do_cache == 0

    cache = {r.chave_cache: r for r in registros_1}
    registros_2, stats_2 = _build(service, fixtures_dir, cache=cache)

    assert stats_2.reaproveitados_do_cache == len(registros_1)
    assert len(registros_2) == len(registros_1)


def test_estatisticas_de_status_batem_com_registros(service: InventoryService, fixtures_dir: Path) -> None:
    registros, stats = _build(service, fixtures_dir)

    assert stats.corrompidos == sum(1 for r in registros if r.status == PdfStatus.CORROMPIDO)
    assert stats.protegidos == sum(1 for r in registros if r.status == PdfStatus.PROTEGIDO)
    assert stats.vazios == sum(1 for r in registros if r.status == PdfStatus.VAZIO)
    assert stats.total_paginas == sum(r.paginas or 0 for r in registros)
