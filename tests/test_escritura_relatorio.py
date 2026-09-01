"""Teste do relatorio de escrituras (opcao 12): le a arvore de saida ja
processada + os CSV de rastreabilidade e consolida.
"""
from __future__ import annotations

import csv
from pathlib import Path

from repositories.escritura_relatorio_repository import EscrituraRelatorioRepository
from services.escritura_relatorio_service import EscrituraRelatorioService
from services.util_faixas import faixas


def _pdf(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\n%x\n")


def test_faixas():
    assert faixas([2, 3, 4, 7, 9, 10]) == "2-4, 7, 9-10"
    assert faixas([]) == ""
    assert faixas([5]) == "5"


def _arvore(tmp_path: Path):
    base = tmp_path / "out"
    livro = base / "revisar" / "1107"
    # folhas 1..8 (total=8), menos a 5; folha 3 com 1 duplicada; folha 2 com 2 anexos
    for n in (1, 2, 3, 4, 6, 7, 8):
        _pdf(livro / f"{n:03d}" / f"1107_folha_{n:03d}.pdf")
    _pdf(livro / "003" / "duplicada" / "1107_folha_003.pdf")
    _pdf(livro / "002" / "anexo_01.pdf")
    _pdf(livro / "002" / "2_livro1107_folha_002.pdf")

    reports = tmp_path / "reports"
    reports.mkdir()
    csv_imp = reports / "Importacao_livro1107_20260101_000000.csv"
    with open(csv_imp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
                    "Origem", "PaginaOrigem", "Status", "Erro", "CaminhoDestino"])
        for n in (1, 2, 3, 4, 6, 7, 8):
            w.writerow([1107, n, "conteudo", f"{n:03d}", f"1107_folha_{n:03d}.pdf",
                        f"N:\\livro1107\\f{n:03d}\\1_livro1107_folha_{n:03d}.pdf", 1, "Gerada", "", ""])
        w.writerow([1107, 30, "conflito", "", "", "N:\\livro1107\\x.pdf", 2,
                    "Fora do plano", "codigo do livro 1250 folha 30", ""])
    return base, reports


def test_relatorio_consolida_faltando_dup_anexo_conflito(tmp_path: Path) -> None:
    base, reports = _arvore(tmp_path)
    rel = EscrituraRelatorioService(folhas_por_livro=8).gerar(base, reports)

    assert len(rel.livros) == 1
    lv = rel.livros[0]
    assert lv.numero == 1107 and lv.diagnostico == "revisar"
    assert lv.folhas_presentes == [1, 2, 3, 4, 6, 7, 8]
    assert lv.folhas_faltando == [5]
    assert lv.duplicadas == {3: 1}
    assert lv.anexos_por_folha == {2: 2}
    assert lv.tem_abertura and lv.tem_encerramento
    assert len(lv.conflitos) == 1 and lv.conflitos[0][1] == "1250"
    assert lv.origem_por_folha[4].endswith("1_livro1107_folha_004.pdf")


def test_relatorio_repository_csv_fallback(tmp_path: Path) -> None:
    base, reports = _arvore(tmp_path)
    rel = EscrituraRelatorioService(folhas_por_livro=8).gerar(base, reports)
    saida = EscrituraRelatorioRepository(tmp_path / "rep", folhas_por_livro=8).salvar(rel, "20260101_000000")

    # sem openpyxl -> pasta com um csv por aba
    if saida.is_dir():
        resumo = (saida / "Resumo.csv").read_text(encoding="utf-8-sig")
        assert "1107" in resumo and "revisar" in resumo
        falt = list(csv.DictReader((saida / "Folhas_Faltando.csv").read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
        assert falt and falt[0]["Folha"] == "5"
    else:
        assert saida.suffix == ".xlsx" and saida.exists()
