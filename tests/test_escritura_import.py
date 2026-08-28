"""Testes do modulo de Importacao de livros de escrituras.

Cada livro de teste tem 6 folhas (config EscrituraFolhasPorLivro=6):
folha 1 = abertura, folhas 2..5 = conteudo, folha 6 = encerramento.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from models.config import AppConfig
from repositories.escritura_import_repository import EscrituraImportRepository
from services.escritura_importer_service import EscrituraImporterService
from services.escritura_planner_service import EscrituraPlannerService
from services.escritura_scanner_service import EscrituraScannerService
from services.rename_template_service import RenameTemplateService


def _pdf(caminho: Path, paginas: int) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(max(1, paginas)):
        writer.add_blank_page(width=300, height=400)
    with open(caminho, "wb") as arquivo:
        writer.write(arquivo)
    return caminho


def _livro_padrao(raiz: Path, numero: int = 9001) -> Path:
    """Livro que FECHA: 2+1+1 = 4 folhas de conteudo (2..5), + termos."""
    pasta = raiz / f"livro{numero}"
    _pdf(pasta / f"livro{numero}_termo_abertura.pdf", 1)
    _pdf(pasta / "f002" / f"1_livro{numero}_folha_002.pdf", 2)          # dupla implicita -> folhas 2, 3
    _pdf(pasta / "f002" / f"2_livro{numero}_folha_002.pdf", 1)          # anexo -> pasta 002
    _pdf(pasta / "f002" / "Thumbs.db", 1)                               # lixo
    _pdf(pasta / "f004" / f"1_livro{numero}_folha_004.pdf", 1)          # folha 4
    _pdf(pasta / "f005" / f"1_livro{numero}_folha_005.pdf", 1)          # folha 5
    _pdf(pasta / f"livro{numero}_termo_encerramento.pdf", 1)
    return pasta


def _config(destino: Path) -> AppConfig:
    return AppConfig(
        origem=destino,
        escritura_destino=destino,
        escritura_nome_template="{Livro}_folha_{Pagina}",
        escritura_folha_digitos=3,
        escritura_folhas_por_livro=6,
    )


def _planejador(cfg: AppConfig) -> EscrituraPlannerService:
    templates = RenameTemplateService()

    def nome(livro: int, folha: int) -> str:
        return templates.render(
            cfg.escritura_nome_template, livro=str(livro), pagina=folha,
            pagina_digits=cfg.escritura_folha_digitos, data_formato="%Y%m%d",
            nome_original="", extensao="pdf",
        )

    return EscrituraPlannerService(
        contar_paginas=lambda p: len(PdfReader(str(p)).pages),
        nome_destino=nome,
        folhas_por_livro=cfg.escritura_folhas_por_livro,
    )


# ------------------------------ scanner ------------------------------ #

def test_scanner_classifica_e_ordena(tmp_path: Path) -> None:
    pasta = _livro_padrao(tmp_path)
    livro = EscrituraScannerService().scan_livro(pasta)

    assert livro.numero == 9001
    assert livro.termo_abertura is not None and "abertura" in livro.termo_abertura.name
    assert livro.termo_encerramento is not None
    assert [f.pasta_scan for f in livro.folhas] == ["f002", "f004", "f005"]
    assert [f.folha_nome_ini for f in livro.folhas] == [2, 4, 5]
    # o anexo 2_ foi casado com a folha da mesma pasta
    assert len(livro.folhas[0].anexos) == 1
    assert livro.folhas[0].anexos[0].name.startswith("2_")
    # Thumbs.db foi ignorado
    assert any(p.name == "Thumbs.db" for p in livro.ignorados)


# ------------------------------ planner ------------------------------ #

def test_planner_numera_folhas_com_dupla_implicita(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "out")
    pasta = _livro_padrao(tmp_path)
    livro = EscrituraScannerService().scan_livro(pasta)
    plano = _planejador(cfg).planejar(livro, cfg.escritura_destino)

    assert plano.diagnostico == "ok"
    assert plano.ultima_folha_conteudo == 5
    numeros = [f.numero for f in plano.folhas]
    assert numeros == [1, 2, 3, 4, 5, 6]
    tipos = {f.numero: f.tipo for f in plano.folhas}
    assert tipos[1] == "abertura" and tipos[6] == "encerramento"
    # folha 2 e 3 vem do mesmo PDF, paginas 1 e 2
    f2, f3 = [f for f in plano.folhas if f.numero in (2, 3)]
    assert f2.origem == f3.origem and (f2.pagina_origem, f3.pagina_origem) == (1, 2)
    # anexo vai para a pasta da PRIMEIRA folha daquele arquivo (folha 2)
    assert len(plano.anexos) == 1 and plano.anexos[0].folha_destino == 2
    # nomes de destino
    assert plano.folhas[1].nome_destino == "9001_folha_002.pdf"
    assert plano.folhas[1].caminho_destino.parent.name == "002"


def test_planner_livro_que_nao_fecha_vira_revisar(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "out")
    pasta = tmp_path / "livro9002"
    _pdf(pasta / "livro9002_termo_abertura.pdf", 1)
    _pdf(pasta / "f002" / "1_livro9002_folha_002.pdf", 1)   # so 1 folha de conteudo (esperado 4)
    _pdf(pasta / "livro9002_termo_encerramento.pdf", 1)
    livro = EscrituraScannerService().scan_livro(pasta)
    plano = _planejador(cfg).planejar(livro, cfg.escritura_destino)
    assert plano.diagnostico in ("revisar", "incompleto")
    assert not plano.automatizavel


def test_planner_roteia_anexo_orfao_para_a_folha_da_pasta(tmp_path: Path) -> None:
    """f003 so tem anexo (a folha 3 esta dentro do folha_002.pdf, que tem 2 paginas)."""
    cfg = _config(tmp_path / "out")
    pasta = tmp_path / "livro9010"
    _pdf(pasta / "livro9010_termo_abertura.pdf", 1)
    _pdf(pasta / "f002" / "1_livro9010_folha_002.pdf", 2)       # folhas 2 e 3
    _pdf(pasta / "f003" / "3_livro9010_folha_003.pdf", 1)       # anexo orfao -> folha 3
    _pdf(pasta / "f004" / "1_livro9010_folha_004.pdf", 2)       # folhas 4 e 5
    _pdf(pasta / "livro9010_termo_encerramento.pdf", 1)
    livro = EscrituraScannerService().scan_livro(pasta)
    assert livro.anexos_orfaos == {3: [pasta / "f003" / "3_livro9010_folha_003.pdf"]}

    plano = _planejador(cfg).planejar(livro, cfg.escritura_destino)
    assert plano.diagnostico == "ok"
    assert len(plano.anexos) == 1
    assert plano.anexos[0].folha_destino == 3
    assert plano.anexos[0].caminho_destino.parent.name == "003"


def test_scanner_avisa_termo_com_numero_de_outro_livro(tmp_path: Path) -> None:
    pasta = tmp_path / "livro9011"
    _pdf(pasta / "livro9010_termo_abertura.pdf", 1)             # numero errado no nome
    _pdf(pasta / "f002" / "1_livro9011_folha_002.pdf", 1)
    livro = EscrituraScannerService().scan_livro(pasta)
    assert livro.termo_abertura is not None
    assert any("CONFERIR se e o termo certo" in a for a in livro.avisos)


def test_planner_sem_termo_encerramento_avisa(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "out")
    pasta = tmp_path / "livro9003"
    _pdf(pasta / "livro9003_termo_abertura.pdf", 1)
    _pdf(pasta / "f002" / "1_livro9003_folha_002.pdf", 4)   # folhas 2..5
    livro = EscrituraScannerService().scan_livro(pasta)
    plano = _planejador(cfg).planejar(livro, cfg.escritura_destino)
    assert any("sem termo de encerramento" in a for a in plano.avisos)
    assert plano.diagnostico != "ok"


# --------------------------- importer (disco) --------------------------- #

def test_importer_gera_arvore_de_pastas(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "out")
    pasta = _livro_padrao(tmp_path)
    livro = EscrituraScannerService().scan_livro(pasta)
    plano = _planejador(cfg).planejar(livro, cfg.escritura_destino)

    EscrituraImporterService().executar(plano)

    base = cfg.escritura_destino / "9001"
    for n in range(1, 7):
        arq = base / f"{n:03d}" / f"9001_folha_{n:03d}.pdf"
        assert arq.exists(), arq
        assert len(PdfReader(str(arq)).pages) == 1
    # anexo copiado na pasta 002
    anexos = [p for p in (base / "002").iterdir() if p.name.startswith("2_")]
    assert len(anexos) == 1
    # originais intactos
    assert (pasta / "f002" / "1_livro9001_folha_002.pdf").exists()
    assert all(f.status == "Gerada" for f in plano.folhas)


def test_importer_nao_sobrescreve_em_segunda_execucao(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "out")
    pasta = _livro_padrao(tmp_path)
    livro = EscrituraScannerService().scan_livro(pasta)
    imp = EscrituraImporterService()
    imp.executar(_planejador(cfg).planejar(livro, cfg.escritura_destino))
    imp.executar(_planejador(cfg).planejar(livro, cfg.escritura_destino))
    pasta_002 = cfg.escritura_destino / "9001" / "002"
    assert (pasta_002 / "9001_folha_002.pdf").exists()
    assert (pasta_002 / "9001_folha_002 (2).pdf").exists()


# ---------------------------- repository ---------------------------- #

def test_repository_rastreabilidade_e_retomada(tmp_path: Path) -> None:
    repo = EscrituraImportRepository(tmp_path / "reports", tmp_path / "progress")
    cfg = _config(tmp_path / "out")
    pasta = _livro_padrao(tmp_path)
    livro = EscrituraScannerService().scan_livro(pasta)
    plano = _planejador(cfg).planejar(livro, cfg.escritura_destino)
    EscrituraImporterService().executar(plano)

    csv_path = repo.salvar_livro(plano)
    assert csv_path.exists()
    conteudo = csv_path.read_text(encoding="utf-8-sig")
    assert "abertura" in conteudo and "encerramento" in conteudo and "anexo" in conteudo

    assert repo.concluidos() == set()
    repo.marcar_concluido(9001)
    assert 9001 in repo.concluidos()
