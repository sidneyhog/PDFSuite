"""Testes do planejador GUIADO POR CODIGO (opcao 11): a folha de cada
pagina sai do codigo do rodape, nao da posicao.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models.escritura_import import ArquivoFolhaOrigem, LivroOrigem
from services.escritura_codigo_planner_service import EscrituraCodigoPlannerService


def _nome_destino(livro: int, folha: int) -> str:
    return f"{livro}_folha_{folha:03d}.pdf"


class FakeLeitor:
    """name do PDF -> lista de (livro, folha) | None, uma por pagina."""

    def __init__(self, mapa: dict[str, list]) -> None:
        self._mapa = mapa

    def __call__(self, caminho: Path) -> list:
        return list(self._mapa.get(caminho.name, []))


def _livro(numero: int, folhas: list[ArquivoFolhaOrigem], *, com_termos: bool = True,
           orfaos: dict | None = None) -> LivroOrigem:
    return LivroOrigem(
        numero=numero,
        pasta=Path(f"/orig/livro{numero}"),
        termo_abertura=Path(f"/orig/livro{numero}/abertura.pdf") if com_termos else None,
        termo_encerramento=Path(f"/orig/livro{numero}/encerr.pdf") if com_termos else None,
        folhas=folhas,
        anexos_orfaos=orfaos or {},
    )


def _arq(nome: str, pasta_scan: str = "f001", anexos: list | None = None) -> ArquivoFolhaOrigem:
    return ArquivoFolhaOrigem(
        caminho=Path(f"/orig/{nome}"), pasta_scan=pasta_scan,
        folha_nome_ini=None, folha_nome_fim=None, anexos=anexos or [],
    )


def _plan(leitor: FakeLeitor, folhas_por_livro: int = 6):
    return EscrituraCodigoPlannerService(leitor, _nome_destino, folhas_por_livro=folhas_por_livro)


def test_livro_limpo_fecha_ok(tmp_path: Path) -> None:
    leitor = FakeLeitor({
        "a.pdf": [(1000, 2)],
        "b.pdf": [(1000, 3), (1000, 4)],
        "c.pdf": [(1000, 5)],
    })
    livro = _livro(1000, [_arq("a.pdf"), _arq("b.pdf"), _arq("c.pdf")])
    plano = _plan(leitor).planejar(livro, tmp_path)

    assert plano.diagnostico == "ok"
    assert {f.numero for f in plano.folhas} == {1, 2, 3, 4, 5, 6}
    folha4 = next(f for f in plano.folhas if f.numero == 4)
    assert folha4.origem.name == "b.pdf" and folha4.pagina_origem == 2
    assert plano.pasta_destino == tmp_path / "ok" / "1000"


def test_pagina_sem_codigo_no_meio_vira_anexo_da_folha_corrente(tmp_path: Path) -> None:
    leitor = FakeLeitor({"a.pdf": [(1000, 2), None, (1000, 3)]})
    livro = _livro(1000, [_arq("a.pdf")])
    plano = _plan(leitor).planejar(livro, tmp_path)

    assert [f.numero for f in plano.folhas if f.tipo == "conteudo"] == [2, 3]
    anx = [a for a in plano.anexos if a.pagina_origem is not None]
    assert len(anx) == 1
    assert anx[0].folha_destino == 2 and anx[0].pagina_origem == 2
    assert anx[0].caminho_destino == tmp_path / plano.diagnostico / "1000" / "002" / "a_p02.pdf"


def test_sem_codigo_antes_da_primeira_folha_cola_na_primeira(tmp_path: Path) -> None:
    leitor = FakeLeitor({"a.pdf": [None, None, (1000, 4), (1000, 5)]})
    livro = _livro(1000, [_arq("a.pdf")])
    plano = _plan(leitor).planejar(livro, tmp_path)

    anx = sorted((a for a in plano.anexos if a.pagina_origem), key=lambda a: a.pagina_origem)
    assert [a.pagina_origem for a in anx] == [1, 2]
    assert all(a.folha_destino == 4 for a in anx)


def test_folha_repetida_vira_duplicada(tmp_path: Path) -> None:
    leitor = FakeLeitor({
        "a.pdf": [(1000, 2), (1000, 3)],
        "b.pdf": [(1000, 3), (1000, 4), (1000, 5)],       # folha 3 repetida
    })
    livro = _livro(1000, [_arq("a.pdf"), _arq("b.pdf")])
    plano = _plan(leitor).planejar(livro, tmp_path)

    dups = [f for f in plano.folhas if f.duplicada]
    assert len(dups) == 1 and dups[0].numero == 3
    assert dups[0].caminho_destino.parent.name == "duplicada"
    assert plano.diagnostico == "revisar"


def test_codigo_de_outro_livro_e_conflito(tmp_path: Path) -> None:
    leitor = FakeLeitor({"a.pdf": [(1000, 2), (999, 40), (1000, 3)]})
    livro = _livro(1000, [_arq("a.pdf")])
    plano = _plan(leitor).planejar(livro, tmp_path)

    assert len(plano.conflitos) == 1
    origem, pagina, code = plano.conflitos[0]
    assert pagina == 2 and code == (999, 40)
    assert not any(f.numero == 40 for f in plano.folhas)
    assert plano.diagnostico == "revisar"


def test_anexo_preexistente_vai_para_primeira_folha_real_do_arquivo(tmp_path: Path) -> None:
    ax = Path("/orig/2_livro1000_folha_010.pdf")
    leitor = FakeLeitor({"f.pdf": [(1000, 10), (1000, 11)]})
    livro = _livro(1000, [_arq("f.pdf", pasta_scan="f010", anexos=[ax])])
    plano = _plan(leitor).planejar(livro, tmp_path)

    copias = [a for a in plano.anexos if a.pagina_origem is None]
    assert len(copias) == 1
    assert copias[0].folha_destino == 10
    assert copias[0].nome_destino == "2_livro1000_folha_010.pdf"


def test_anexos_orfaos_roteados_pelo_numero_da_pasta(tmp_path: Path) -> None:
    ax = Path("/orig/f042/pasta_livro1000_folha_042.pdf")
    leitor = FakeLeitor({"a.pdf": [(1000, 2)]})
    livro = _livro(1000, [_arq("a.pdf")], orfaos={42: [ax]})
    plano = _plan(leitor).planejar(livro, tmp_path)

    orfao = next(a for a in plano.anexos if a.origem == ax)
    assert orfao.folha_destino == 42 and orfao.pagina_origem is None


def test_livro_incompleto(tmp_path: Path) -> None:
    leitor = FakeLeitor({"a.pdf": [(1000, 2)]})            # so 1 folha de conteudo, esperado 4
    livro = _livro(1000, [_arq("a.pdf")])
    plano = _plan(leitor).planejar(livro, tmp_path)
    assert plano.diagnostico == "incompleto"
