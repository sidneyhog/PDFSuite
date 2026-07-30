"""Teste de integracao do modulo de Renomeacao: grava um inventario falso
diretamente via InventoryRepository (sem depender do modulo de Inventario
em si), roda RenameModule.run() com respostas de input() simuladas e
confere os arquivos gerados no destino.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pytest

from models.config import AppConfig
from models.pdf_record import PdfRecord, PdfStatus
from modules.rename_module import RenameModule
from repositories.inventory_repository import InventoryRepository
from repositories.rename_repository import RenameRepository
from services.rename_template_service import RenameTemplateService


def _fake_record(caminho: Path, livro: Optional[str]) -> PdfRecord:
    caminho.write_bytes(b"conteudo")
    return PdfRecord(
        caminho=caminho,
        nome=caminho.name,
        tamanho_bytes=caminho.stat().st_size,
        modificado_em=datetime.now(),
        status=PdfStatus.OK,
        sha256="ABC",
        paginas=1,
        livro=livro,
    )


@pytest.fixture()
def ambiente(tmp_path: Path):
    origem = tmp_path / "origem"
    origem.mkdir()
    destino = tmp_path / "destino"
    reports_dir = tmp_path / "reports"

    registros = [
        _fake_record(origem / "b_arquivo.pdf", "15"),
        _fake_record(origem / "a_arquivo.pdf", "15"),
        _fake_record(origem / "outro.pdf", None),  # sem livro - deve ser ignorado
        _fake_record(origem / "livro20.pdf", "20"),
    ]

    inventory_repository = InventoryRepository(reports_dir)
    inventory_repository.save(registros)

    config = AppConfig(origem=origem, rename_destino=None, rename_pagina_digits=3)
    rename_repository = RenameRepository(reports_dir)
    module = RenameModule(config, inventory_repository, rename_repository, RenameTemplateService())

    return module, destino, reports_dir


def test_renomeia_agrupando_por_livro_e_ordenando_por_nome(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    respostas = iter(["1", str(destino), "S"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    # Livro 15: a_arquivo.pdf (nome menor) vira pagina 001; b_arquivo.pdf vira 002.
    assert (destino / "15_001.pdf").exists()
    assert (destino / "15_002.pdf").exists()
    assert (destino / "20_001.pdf").exists()
    assert len(list(destino.iterdir())) == 3  # "outro.pdf" (sem livro) foi ignorado


def test_gera_csv_de_rastreabilidade(ambiente, monkeypatch) -> None:
    module, destino, reports_dir = ambiente

    respostas = iter(["1", str(destino), "S"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    csvs = list(reports_dir.glob("Renomeacao_*.csv"))
    assert len(csvs) == 1


def test_cancelar_no_preview_nao_copia_nada(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    respostas = iter(["1", str(destino), "N"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))

    module.run()

    assert not destino.exists() or not list(destino.iterdir())


def test_segunda_execucao_nao_sobrescreve(ambiente, monkeypatch) -> None:
    module, destino, _ = ambiente

    respostas_1 = iter(["1", str(destino), "S"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas_1))
    module.run()

    respostas_2 = iter(["1", str(destino), "S"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas_2))
    module.run()

    assert (destino / "15_001 (2).pdf").exists()
    original = (destino / "15_001.pdf").read_bytes()
    copia = (destino / "15_001 (2).pdf").read_bytes()
    assert original == copia
