"""Gera um ambiente ficticio de PDFs para testar o modulo de Inventario,
sem depender de nenhum acervo real. Usado pelos testes automatizados
(tests/test_inventory.py, tests/test_pdf_inspector.py) e para um teste
manual rapido (ver README.md).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from pypdf import PdfWriter

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _write_valid_pdf(path: Path, paginas: int) -> None:
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as arquivo:
        writer.write(arquivo)


def _write_encrypted_pdf(path: Path, senha: str = "segredo123") -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(user_password=senha)
    with open(path, "wb") as arquivo:
        writer.write(arquivo)


def _write_corrupted_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.4\nISSO NAO E UM PDF VALIDO\n%%EOF-TRUNCADO")


def _write_empty_file(path: Path) -> None:
    path.write_bytes(b"")


def generate(base_dir: Path = FIXTURES_DIR, limpar: bool = True) -> Path:
    """Cria (ou recria) o ambiente ficticio e retorna a pasta gerada.

    Estrutura gerada:
        Livro01/
            1_pagina_unica.pdf       - valido, 1 pagina
            multiplas_paginas.pdf    - valido, 5 paginas
            corrompido.pdf           - bytes invalidos
            duplicado_original.pdf   - valido, 2 paginas (par de duplicado)
        Livro02/
            protegido.pdf            - valido, protegido por senha
            vazio.pdf                - 0 bytes
            duplicado_copia.pdf      - copia byte-identica de duplicado_original.pdf
    """
    if limpar and base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    (base_dir / "Livro01").mkdir(exist_ok=True)
    (base_dir / "Livro02").mkdir(exist_ok=True)

    _write_valid_pdf(base_dir / "Livro01" / "1_pagina_unica.pdf", paginas=1)
    _write_valid_pdf(base_dir / "Livro01" / "multiplas_paginas.pdf", paginas=5)
    _write_corrupted_pdf(base_dir / "Livro01" / "corrompido.pdf")
    _write_encrypted_pdf(base_dir / "Livro02" / "protegido.pdf")
    _write_empty_file(base_dir / "Livro02" / "vazio.pdf")

    original = base_dir / "Livro01" / "duplicado_original.pdf"
    _write_valid_pdf(original, paginas=2)
    shutil.copyfile(original, base_dir / "Livro02" / "duplicado_copia.pdf")

    return base_dir


if __name__ == "__main__":
    pasta = generate()
    print(f"Ambiente ficticio gerado em: {pasta}")
