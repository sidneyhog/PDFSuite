"""Integracao da opcao 11 (importar por codigo) com PDFs reais de escritura.

So roda se as libs de leitura de codigo estiverem instaladas E os PDFs de
amostra existirem em shared/ (nao versionados).
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("pypdfium2")
pytest.importorskip("zxingcpp")

from services.codigo_folha_service import CodigoFolhaService
from services.escritura_codigo_planner_service import EscrituraCodigoPlannerService
from services.escritura_importer_service import EscrituraImporterService
from services.escritura_scanner_service import EscrituraScannerService

_SHARED = Path(__file__).resolve().parent.parent / "shared"
_AMOSTRAS = {
    "abertura": _SHARED / "1103_folha_001.pdf",
    "encerr": _SHARED / "1103_folha_400.pdf",
    "folha2": _SHARED / "1103_folha_002.pdf",
    "folha150": _SHARED / "1103_folha_150.pdf",
    "anexo2": _SHARED / "2_livro1103_folha_002.pdf",
}

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in _AMOSTRAS.values()),
    reason="PDFs de amostra em shared/ ausentes",
)


def _nome(livro: int, folha: int) -> str:
    return f"{livro}_folha_{folha:03d}.pdf"


@pytest.fixture()
def livro_falso(tmp_path: Path) -> Path:
    raiz = tmp_path / "livro1103"
    (raiz / "f002").mkdir(parents=True)
    (raiz / "f150").mkdir(parents=True)
    shutil.copy(_AMOSTRAS["abertura"], raiz / "livro1103_termo_abertura.pdf")
    shutil.copy(_AMOSTRAS["encerr"], raiz / "livro1103_termo_encerramento.pdf")
    shutil.copy(_AMOSTRAS["folha2"], raiz / "f002" / "1_livro1103_folha_002.pdf")
    shutil.copy(_AMOSTRAS["anexo2"], raiz / "f002" / "2_livro1103_folha_002.pdf")
    shutil.copy(_AMOSTRAS["folha150"], raiz / "f150" / "1_livro1103_folha_150.pdf")
    return raiz


def test_importa_por_codigo_posiciona_pela_folha_real(livro_falso: Path, tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    livro = EscrituraScannerService().scan_livro(livro_falso)
    planner = EscrituraCodigoPlannerService(
        CodigoFolhaService().identificar_paginas, _nome, folhas_por_livro=400,
    )
    plano = planner.planejar(livro, saida)
    EscrituraImporterService().executar(plano)

    base = plano.pasta_destino
    assert (base / "001" / "1103_folha_001.pdf").exists()      # termo abertura
    assert (base / "400" / "1103_folha_400.pdf").exists()      # termo encerramento
    assert (base / "002" / "1103_folha_002.pdf").exists()      # folha real 2
    assert (base / "150" / "1103_folha_150.pdf").exists()      # folha real 150
    assert (base / "002" / "2_livro1103_folha_002.pdf").exists()  # anexo copiado inteiro
    assert not plano.conflitos
    assert {f.numero for f in plano.folhas if not f.duplicada} == {1, 2, 150, 400}
    assert all(f.status == "Gerada" for f in plano.folhas)
