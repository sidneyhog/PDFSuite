"""Testes unitarios do PdfSplitterService, isolados do modulo de Separacao."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from services.pdf_splitter_service import PdfSplitterService


def _pdf(path: Path, paginas: int, senha: str | None = None) -> Path:
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=612, height=792)
    if senha:
        writer.encrypt(user_password=senha)
    with open(path, "wb") as arquivo:
        writer.write(arquivo)
    return path


def test_separa_todas_as_paginas_em_arquivos_de_uma_pagina(tmp_path: Path) -> None:
    origem = _pdf(tmp_path / "doc.pdf", paginas=3)
    destinos = [(n, tmp_path / f"p{n}.pdf") for n in (1, 2, 3)]

    resultados = PdfSplitterService().split(origem, destinos)

    assert resultados == [(1, None), (2, None), (3, None)]
    for _, caminho in destinos:
        assert caminho.exists()
        assert len(PdfReader(str(caminho)).pages) == 1


def test_pdf_protegido_gera_erro_em_todas_as_paginas(tmp_path: Path) -> None:
    origem = _pdf(tmp_path / "protegido.pdf", paginas=2, senha="segredo123")
    destinos = [(1, tmp_path / "a.pdf"), (2, tmp_path / "b.pdf")]

    resultados = PdfSplitterService().split(origem, destinos)

    assert all(erro is not None for _, erro in resultados)
    assert not (tmp_path / "a.pdf").exists()


def test_pagina_inexistente_gera_erro_isolado(tmp_path: Path) -> None:
    origem = _pdf(tmp_path / "doc.pdf", paginas=2)
    destinos = [(1, tmp_path / "ok.pdf"), (99, tmp_path / "nao.pdf")]

    resultados = dict(PdfSplitterService().split(origem, destinos))

    assert resultados[1] is None
    assert resultados[99] is not None
    assert (tmp_path / "ok.pdf").exists()
    assert not (tmp_path / "nao.pdf").exists()


def test_pdf_corrompido_nao_levanta_excecao(tmp_path: Path) -> None:
    origem = tmp_path / "ruim.pdf"
    origem.write_bytes(b"%PDF-1.4\nNAO E PDF\n%%EOF")
    destinos = [(1, tmp_path / "x.pdf")]

    resultados = PdfSplitterService().split(origem, destinos)

    assert resultados[0][0] == 1 and resultados[0][1] is not None
