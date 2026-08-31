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
