"""Teste de integracao do modulo de Separacao: grava um inventario falso
via InventoryRepository, roda SplitModule.run() com input() simulado e
confere os arquivos de 1 pagina gerados no destino.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest
from pypdf import PdfReader, PdfWriter

from models.config import AppConfig
from models.pdf_record import PdfRecord, PdfStatus
from modules.split_module import SplitModule
from repositories.inventory_repository import InventoryRepository
from repositories.split_repository import SplitRepository
from services.rename_template_service import RenameTemplateService


def _pdf_record(caminho: Path, paginas: int, livro: Optional[str], status: PdfStatus = PdfStatus.OK) -> PdfRecord:
    writer = PdfWriter()
    for _ in range(max(paginas, 1)):
        writer.add_blank_page(width=612, height=792)
    with open(caminho, "wb") as arquivo:
        writer.write(arquivo)
    return PdfRecord(
        caminho=caminho,
        nome=caminho.name,
        tamanho_bytes=caminho.stat().st_size,
        modificado_em=datetime.now(),
        status=status,
        sha256="ABC",
        paginas=paginas,
        livro=livro,
    )


@pytest.fixture()
def ambiente(tmp_path: Path):
    origem = tmp_path / "origem"
    origem.mkdir()
    destino = tmp_path / "destino"
    reports_dir = tmp_path / "reports"

    registros = [
        _pdf_record(origem / "contrato.pdf", paginas=3, livro="15"),
        _pdf_record(origem / "escritura.pdf", paginas=2, livro="15"),
        _pdf_record(origem / "avulso.pdf", paginas=1, livro="20"),          # 1 pagina - ignorado
        _pdf_record(origem / "quebrado.pdf", paginas=4, livro="20", status=PdfStatus.CORROMPIDO),  # ignorado
    ]

    inventory_repository = InventoryRepository(reports_dir)
    inventory_repository.save(registros)

    config = AppConfig(origem=origem, split_destino=None, rename_pagina_digits=3)
    split_repository = SplitRepository(reports_dir)
    module = SplitModule(config, inventory_repository, split_repository, RenameTemplateService())

    return module, destino, reports_dir


def test_separa_apenas_multipagina_gerando_uma_pagina_por_arquivo(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    respostas = iter(["1", str(destino), "S"])  # template 1: {NomeOriginal}_p{Pagina}
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    esperados = ["contrato_p001.pdf", "contrato_p002.pdf", "contrato_p003.pdf",
                 "escritura_p001.pdf", "escritura_p002.pdf"]
    for nome in esperados:
        assert (destino / nome).exists()
        assert len(PdfReader(str(destino / nome)).pages) == 1
    assert len(list(destino.iterdir())) == 5  # avulso (1 pag) e quebrado (corrompido) ficam de fora


def test_template_com_total_de_paginas(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    respostas = iter(["2", str(destino), "S"])  # {NomeOriginal}_{Pagina}-de-{TotalPaginas}
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    assert (destino / "contrato_001-de-003.pdf").exists()
    assert (destino / "escritura_002-de-002.pdf").exists()


def test_cancelar_no_preview_nao_gera_nada(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    respostas = iter(["1", str(destino), "N"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    assert not destino.exists() or not list(destino.iterdir())


def test_gera_csv_de_rastreabilidade(ambiente, monkeypatch) -> None:
    module, destino, reports_dir = ambiente

    respostas = iter(["1", str(destino), "S"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    csvs = list(reports_dir.glob("Separacao_*.csv"))
    assert len(csvs) == 1


def test_segunda_execucao_nao_sobrescreve(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    for _ in range(2):
        respostas = iter(["1", str(destino), "S"])
        monkeypatch.setattr("builtins.input", lambda *_: next(respostas))
        module.run()

    assert (destino / "contrato_p001 (2).pdf").exists()
