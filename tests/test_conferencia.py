"""Teste do modulo de Conferencia: monta uma arvore falsa da saida da
importacao (com deriva) e verifica que a conferencia corrige as pastas
pelo codigo lido, com um leitor de codigo dublê.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.conferencia_service import ConferenciaService


class FakeLeitor:
    """Dublê do CodigoFolhaService: devolve o codigo pelo nome do arquivo."""

    def __init__(self, mapa: dict[str, object]) -> None:
        self._mapa = mapa

    def identificar(self, caminho: Path, pagina: int = 0):
        return self._mapa.get(caminho.name)

    def disponivel(self):
        return True, ""


def _pdf(caminho: Path, conteudo: bytes = b"%PDF-1.4\n%fake\n") -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)


@pytest.fixture()
def arvore(tmp_path: Path):
    """Livro 1083 (8 folhas). Split gerou 9 pastas por causa de 1 atestado
    escaneado dentro do arquivo folha_003_004.pdf (pastas 003,004,005).
    """
    base = tmp_path / "saida"
    livro = base / "revisar" / "1083"
    # pasta -> (nome_arquivo, codigo_que_o_leitor_vai_devolver)
    plano = {
        1: ("1083_folha_001.pdf", (1083, 1)),      # abertura
        2: ("1083_folha_002.pdf", (1083, 2)),
        3: ("1083_folha_003.pdf", (1083, 3)),
        4: ("1083_folha_004.pdf", (1083, 4)),
        5: ("1083_folha_005.pdf", None),           # <- atestado (sem codigo)
        6: ("1083_folha_006.pdf", (1083, 5)),      # deriva +1 daqui pra frente
        7: ("1083_folha_007.pdf", (1083, 6)),
        8: ("1083_folha_008.pdf", (1083, 7)),
        9: ("1083_folha_009.pdf", (1083, 8)),      # encerramento
    }
    mapa = {}
    for pasta, (nome, codigo) in plano.items():
        _pdf(livro / f"{pasta:03d}" / nome)
        mapa[nome] = codigo
    # anexo pre-existente na pasta 002
    _pdf(livro / "002" / "2_livro1083_folha_002.pdf")

    reports = tmp_path / "reports"
    reports.mkdir()
    csv_import = reports / "Importacao_livro1083_20260101_000000.csv"
    linhas = ["Livro;FolhaDestino;Tipo;PastaDestino;NomeDestino;Origem;PaginaOrigem;Status;Erro"]
    origem = {1: "livro1083_termo_abertura.pdf", 9: "livro1083_termo_encerramento.pdf"}
    for pasta in range(2, 9):
        arq = ("livro1083_folha_003_004.pdf" if pasta in (3, 4, 5)
               else f"livro1083_folha_{pasta:03d}.pdf")
        linhas.append(f"1083;{pasta};conteudo;{pasta:03d};x.pdf;C:\\o\\{arq};1;Gerada;")
    csv_import.write_text("\n".join(linhas), encoding="utf-8-sig")

    return livro, FakeLeitor(mapa), csv_import


def test_conferencia_simulacao_nao_move(arvore) -> None:
    livro, leitor, csv_import = arvore
    antes = sorted(p.name for p in livro.iterdir())
    res = ConferenciaService(leitor, folhas_por_livro=8).conferir(
        livro, 1083, "revisar", csv_import, executar=False
    )
    assert sorted(p.name for p in livro.iterdir()) == antes   # nada mudou
    assert res.folhas_reais == set(range(1, 9))
    assert res.sem_codigo == 1
    assert res.diagnostico_depois == "ok"
    # o atestado (pasta 005) foi roteado para a folha 3 (1a folha do folha_003_004)
    atestado = next(i for i in res.itens if i.classe == "sem_codigo")
    assert atestado.destino_folha == 3 and atestado.acao == "vira_anexo"


def test_conferencia_executa_e_corrige_as_pastas(arvore) -> None:
    livro, leitor, csv_import = arvore
    res = ConferenciaService(leitor, folhas_por_livro=8).conferir(
        livro, 1083, "revisar", csv_import, executar=True
    )
    pastas = {p.name: sorted(f.name for f in p.iterdir()) for p in livro.iterdir() if p.is_dir()}
    # 8 folhas, pastas 001..008, sem a 009
    assert set(pastas) == {f"{n:03d}" for n in range(1, 9)}
    assert pastas["007"] == ["1083_folha_007.pdf"]           # era a pasta 008
    assert pastas["008"] == ["1083_folha_008.pdf"]           # era a pasta 009 (encerramento)
    # folha 3 tem o anexo antigo + o atestado que virou anexo
    assert "2_livro1083_folha_002.pdf" not in pastas["003"]
    assert any(n.startswith("anexo_") for n in pastas["003"])
    assert res.diagnostico_depois == "ok"


def test_conferencia_nao_rebaixa_livro_ok(tmp_path: Path) -> None:
    """Livro que a importacao fechou como 'ok': se 1 folha nao le o codigo
    (barcode/OCR falharam), a conferencia NAO pode rebaixar nem mover nada.
    """
    base = tmp_path / "s" / "ok" / "1200"
    plano = {n: (f"1200_folha_{n:03d}.pdf", (1200, n)) for n in range(1, 9)}
    plano[5] = ("1200_folha_005.pdf", None)          # folha real, mas codigo ilegivel
    mapa = {}
    for pasta, (nome, codigo) in plano.items():
        _pdf(base / f"{pasta:03d}" / nome)
        mapa[nome] = codigo
    antes = {p.name: sorted(f.name for f in p.iterdir()) for p in base.iterdir()}

    res = ConferenciaService(FakeLeitor(mapa), folhas_por_livro=8).conferir(
        base, 1200, "ok", None, executar=True
    )

    assert res.abortado_guard is True
    assert res.diagnostico_depois == "ok"
    assert res.avisos and res.avisos[0].startswith("CONFERENCIA NAO APLICADA")
    depois = {p.name: sorted(f.name for f in p.iterdir()) for p in base.iterdir()}
    assert depois == antes                                     # nada foi movido
    assert not (base / "_conferencia_tmp").exists()


def test_conferencia_resgata_anexo_que_era_folha(tmp_path: Path) -> None:
    """Nova rodada apos o OCR entrar: um 'anexo_01.pdf' que a conferencia
    anterior criou de uma folha mal-lida agora le o codigo -> volta a ser folha.
    Nao precisa apagar/refazer.
    """
    base = tmp_path / "s" / "quase" / "1300"
    _pdf(base / "010" / "1300_folha_010.pdf")
    _pdf(base / "010" / "anexo_01.pdf")               # era a folha 11, virou anexo
    _pdf(base / "012" / "1300_folha_012.pdf")
    leitor = FakeLeitor({
        "1300_folha_010.pdf": (1300, 10),
        "anexo_01.pdf": (1300, 11),                    # agora o "OCR" le
        "1300_folha_012.pdf": (1300, 12),
    })
    res = ConferenciaService(leitor, folhas_por_livro=14).conferir(
        base, 1300, "quase", None, executar=True
    )

    resgatada = next(i for i in res.itens if i.caminho_atual.name == "anexo_01.pdf")
    assert resgatada.classe == "folha" and resgatada.destino_folha == 11
    assert (base / "011" / "1300_folha_011.pdf").exists()
    assert 11 in res.folhas_reais


def test_conferencia_reabsorve_conflitos_e_duplicada(tmp_path: Path) -> None:
    """Numa nova rodada, arquivos que ficaram presos em _conflitos/ e
    NNN/duplicada/ sao relidos: se agora o codigo bate, sao resgatados.
    """
    base = tmp_path / "s" / "revisar" / "1400"
    _pdf(base / "005" / "1400_folha_005.pdf")
    _pdf(base / "_conflitos" / "1400_folha_006.pdf")            # era "outro livro" por mau OCR
    _pdf(base / "005" / "duplicada" / "1400_folha_005_2.pdf")   # falsa duplicata: e a folha 7
    leitor = FakeLeitor({
        "1400_folha_005.pdf": (1400, 5),
        "1400_folha_006.pdf": (1400, 6),                        # agora le certo
        "1400_folha_005_2.pdf": (1400, 7),                      # nao era dup, e a folha 7
    })
    res = ConferenciaService(leitor, folhas_por_livro=12).conferir(
        base, 1400, "revisar", None, executar=True
    )

    assert (base / "006" / "1400_folha_006.pdf").exists()
    assert (base / "007" / "1400_folha_007.pdf").exists()
    assert res.folhas_reais.issuperset({5, 6, 7})
    assert not (base / "_conflitos").exists() or not list((base / "_conflitos").glob("*.pdf"))


def test_conferencia_duplicata_vai_para_subpasta(tmp_path: Path) -> None:
    base = tmp_path / "s" / "quase" / "1090"
    _pdf(base / "010" / "1090_folha_010.pdf")
    _pdf(base / "011" / "1090_folha_011.pdf")
    leitor = FakeLeitor({
        "1090_folha_010.pdf": (1090, 10),
        "1090_folha_011.pdf": (1090, 10),          # duplicata da folha 10
    })
    res = ConferenciaService(leitor, folhas_por_livro=12).conferir(
        base, 1090, "quase", None, executar=True
    )
    assert res.duplicadas.get(10) == 1
    assert (base / "010" / "duplicada").is_dir()
    assert list((base / "010" / "duplicada").glob("*.pdf"))
