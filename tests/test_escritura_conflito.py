"""Teste do modulo de tratamento de conflitos (opcao 13)."""
from __future__ import annotations

import csv
from pathlib import Path

from services.escritura_conflito_service import EscrituraConflitoService
from services.escritura_relatorio_service import EscrituraRelatorioService


class FakeLeitor:
    def identificar_paginas(self, caminho: Path):
        return []


def _pdf(p: Path, paginas: bytes = b"%PDF-1.4\n%x\n") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(paginas)


def _pdf_real(p: Path, n: int = 1) -> None:
    from pypdf import PdfWriter
    p.parent.mkdir(parents=True, exist_ok=True)
    w = PdfWriter()
    for _ in range(n):
        w.add_blank_page(width=200, height=200)
    with open(p, "wb") as f:
        w.write(f)


def _svc(total: int = 6) -> EscrituraConflitoService:
    return EscrituraConflitoService(FakeLeitor(), EscrituraRelatorioService(total), folhas_por_livro=total)


def _arvore(tmp_path: Path):
    base = tmp_path / "out"
    # 1113 em quase/, faltando a folha 3
    for n in (1, 2, 4, 5, 6):
        _pdf(base / "quase" / "1113" / f"{n:03d}" / f"1113_folha_{n:03d}.pdf")
    # 1114 completo em ok/
    for n in range(1, 7):
        _pdf(base / "ok" / "1114" / f"{n:03d}" / f"1114_folha_{n:03d}.pdf")

    reports = tmp_path / "reports"
    reports.mkdir()
    # a folha 3 do 1113 esta mal arquivada dentro do 1114 (1 pagina, no servidor)
    origem = tmp_path / "N" / "livro1114" / "f003" / "1_livro1113_folha_003.pdf"
    _pdf_real(origem, 1)
    with open(reports / "Importacao_livro1114_20260101_000000.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
                    "Origem", "PaginaOrigem", "Status", "Erro", "CaminhoDestino"])
        w.writerow([1114, 3, "conflito", "", "", str(origem), 1, "Fora do plano",
                    "codigo do livro 1113 folha 3", ""])
    return base, reports, origem


def test_analisar_identifica_encaixe_limpo(tmp_path: Path) -> None:
    base, reports, origem = _arvore(tmp_path)
    itens = _svc().analisar(base, reports)
    assert len(itens) == 1
    it = itens[0]
    assert it.livro_correto == 1113 and it.folha == 3 and it.acao == "copiar"
    assert it.destino == base / "quase" / "1113" / "003" / "1113_folha_003.pdf"


def test_executar_copia_e_rediagnostica(tmp_path: Path) -> None:
    base, reports, origem = _arvore(tmp_path)
    svc = _svc()
    itens = svc.analisar(base, reports)
    res = svc.executar(itens, base, reports)

    assert res.itens[0].status == "OK"
    # 1113 agora fecha -> saiu de quase/ para ok/
    assert (base / "ok" / "1113" / "003" / "1113_folha_003.pdf").exists()
    assert not (base / "quase" / "1113").exists()
    assert res.livros_rediagnosticados[1113][0] == "quase"
    assert res.livros_rediagnosticados[1113][1] == "ok"
    # o original no servidor continua la
    assert origem.exists()
    # a linha de conflito no CSV do 1114 foi marcada como resolvida
    txt = next(reports.glob("Importacao_livro1114_*.csv")).read_text(encoding="utf-8-sig")
    assert "Resolvido" in txt
    # e nao aparece mais como conflito ativo
    assert _svc().analisar(base, reports) == []


def test_folha_que_ja_existe_nao_e_copiada_automaticamente(tmp_path: Path) -> None:
    base, reports, origem = _arvore(tmp_path)
    _pdf(base / "quase" / "1113" / "003" / "1113_folha_003.pdf")   # ja existe
    svc = _svc()
    itens = svc.analisar(base, reports)
    assert itens[0].acao == "pular"
    assert "ja existe" in itens[0].motivo
    # nao rebaixa o 1113 nem copia nada
    res = svc.executar(itens, base, reports)
    assert res.itens[0].status == "PULADO"
    assert not res.livros_rediagnosticados


def test_reprocessar_conflito_ja_resolvido(tmp_path: Path) -> None:
    """Depois de resolver, 'incluir_resolvidos=True' re-le o conflito - para
    re-corrigir um roteamento anterior (ex: registrar a folha no CSV certo)."""
    base, reports, origem = _arvore(tmp_path)
    svc = _svc()
    svc.executar(svc.analisar(base, reports), base, reports)          # 1a vez: resolve
    assert svc.analisar(base, reports) == []                          # nao aparece mais
    # com a flag, volta a aparecer (agora como 'pular', destino ja existe)
    de_novo = svc.analisar(base, reports, incluir_resolvidos=True)
    assert len(de_novo) == 1 and de_novo[0].livro_correto == 1113


def test_folha_roteada_entra_no_csv_do_livro_certo(tmp_path: Path) -> None:
    base, reports, origem = _arvore(tmp_path)
    svc = _svc()
    svc.executar(svc.analisar(base, reports), base, reports)
    txt = next(reports.glob("Importacao_livro1113_*.csv")).read_text(encoding="utf-8-sig")
    assert "Roteado (opcao 13)" in txt
    assert "1_livro1113_folha_003.pdf" in txt
    # rodar de novo nao duplica a linha
    svc2 = _svc()
    svc2.executar(svc2.analisar(base, reports), base, reports)
    txt2 = next(reports.glob("Importacao_livro1113_*.csv")).read_text(encoding="utf-8-sig")
    assert txt2.count("Roteado (opcao 13)") == 1


def test_conflito_csv_formato_antigo_sem_coluna_folha(tmp_path: Path) -> None:
    """CSV da 1a versao da opcao 11: FolhaDestino do conflito vinha vazia,
    a folha so aparece no texto do Erro. Precisa ser lida de la."""
    base, reports, origem = _arvore(tmp_path)
    with open(reports / "Importacao_livro1114_20260101_000000.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
                    "Origem", "PaginaOrigem", "Status", "Erro"])
        w.writerow([1114, "", "conflito", "", "", str(origem), 1, "Fora do plano",
                    "codigo do livro 1113 folha 3"])
    itens = _svc().analisar(base, reports)
    assert len(itens) == 1
    assert itens[0].livro_correto == 1113 and itens[0].folha == 3
    assert itens[0].acao == "copiar"


def test_validar_nao_reclama_de_anexo_por_pagina(tmp_path: Path) -> None:
    """Os anexos '<origem>_pNN.pdf' que a opcao 11 gera estao no CSV como
    linhas 'anexo' - nao podem virar 'sem_registro_csv'."""
    base, reports, origem = _arvore(tmp_path)
    _pdf(base / "quase" / "1113" / "002" / "livro1113_folha_002_003_p03.pdf")
    with open(reports / "Importacao_livro1113_20260101_000000.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
                    "Origem", "PaginaOrigem", "Status", "Erro", "CaminhoDestino"])
        w.writerow([1113, 2, "conteudo", "002", "1113_folha_002.pdf", "N:\\a.pdf", 1, "Gerada", "", ""])
        w.writerow([1113, 2, "anexo", "002", "livro1113_folha_002_003_p03.pdf", "N:\\b.pdf", 3, "Copiado", "", ""])
    divs = _svc().validar(base, reports)
    assert not [d for d in divs if "_p03.pdf" in d.detalhe]


def test_validar_detecta_folha_no_csv_ausente_no_disco(tmp_path: Path) -> None:
    base, reports, origem = _arvore(tmp_path)
    with open(reports / "Importacao_livro1113_20260101_000000.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Livro", "FolhaDestino", "Tipo", "PastaDestino", "NomeDestino",
                    "Origem", "PaginaOrigem", "Status", "Erro", "CaminhoDestino"])
        w.writerow([1113, 2, "conteudo", "002", "1113_folha_002.pdf", "N:\\x.pdf", 1, "Gerada", "", ""])
        w.writerow([1113, 99, "conteudo", "099", "1113_folha_099.pdf", "N:\\y.pdf", 1, "Gerada", "", ""])
    divs = _svc().validar(base, reports)
    tipos = {(d.livro, d.folha, d.tipo) for d in divs}
    assert (1113, "99", "faltando_no_disco") in tipos
    assert (1113, "2", "faltando_no_disco") not in tipos
