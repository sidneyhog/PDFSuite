"""Testes do ConfigRepository, com foco na correcao automatica de JSON
com barras invertidas nao escapadas - o mesmo erro comum que ja aconteceu
de verdade com o config.json do CopiarPDFs.ps1 (colar caminho do Windows
sem duplicar as barras).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from repositories.config_repository import ConfigRepository


def test_carrega_config_valido(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"Origem": "N:/NOTAS/Scanner", "Threads": 4, "EnableHash": false}',
        encoding="utf-8",
    )
    config = ConfigRepository().load(config_path)
    assert config.origem == Path("N:/NOTAS/Scanner")
    assert config.threads == 4
    assert config.enable_hash is False


def test_corrige_barras_invertidas_soltas_automaticamente(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    # String raw: reproduz exatamente o que um usuario colaria do Explorer,
    # incluindo o "\\." ja corretamente escapado dentro do Filtro.
    conteudo = r'''{
  "Origem": "N:\NOTAS\Scanner\imagens",
  "Filtro": "^1_.*\\.pdf$",
  "Threads": 8
}'''
    config_path.write_text(conteudo, encoding="utf-8")

    config = ConfigRepository().load(config_path)

    assert config.origem == Path("N:/NOTAS/Scanner/imagens")
    assert config.filtro == r"^1_.*\.pdf$"


def test_erro_claro_quando_json_realmente_invalido(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"Origem": "N:/x", "Threads": }', encoding="utf-8")

    with pytest.raises(ValueError, match="DICA"):
        ConfigRepository().load(config_path)


def test_cria_template_quando_arquivo_nao_existe(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    with pytest.raises(FileNotFoundError):
        ConfigRepository().load(config_path)
    assert config_path.exists()


def test_valida_threads_fora_do_intervalo(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"Origem": "N:/x", "Threads": 200}', encoding="utf-8")
    with pytest.raises(ValueError, match="Threads"):
        ConfigRepository().load(config_path)
