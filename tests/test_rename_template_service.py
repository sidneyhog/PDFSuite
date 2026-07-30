"""Testes do RenameTemplateService (motor de templates de renomeacao)."""
from __future__ import annotations

import pytest

from services.rename_template_service import RenameTemplateService, TemplateInvalidoError


@pytest.fixture()
def service() -> RenameTemplateService:
    return RenameTemplateService()


def test_template_livro_pagina(service: RenameTemplateService) -> None:
    nome = service.render(
        "{Livro}_{Pagina}", livro="15", pagina=1, pagina_digits=4,
        data_formato="%Y%m%d", nome_original="qualquer.pdf", extensao=".pdf",
    )
    assert nome == "15_0001.pdf"


def test_template_livro_pag_com_prefixo(service: RenameTemplateService) -> None:
    nome = service.render(
        "Livro-{Livro}-Pag-{Pagina}", livro="15", pagina=1, pagina_digits=4,
        data_formato="%Y%m%d", nome_original="qualquer.pdf", extensao="pdf",
    )
    assert nome == "Livro-15-Pag-0001.pdf"


def test_template_com_data(service: RenameTemplateService) -> None:
    nome = service.render(
        "{Data}_{Livro}_{Pagina}", livro="15", pagina=1, pagina_digits=4,
        data_formato="%Y%m%d", nome_original="qualquer.pdf", extensao=".pdf",
    )
    partes = nome.split("_")
    assert len(partes[0]) == 8 and partes[0].isdigit()  # AAAAMMDD
    assert partes[1] == "15"
    assert partes[2] == "0001.pdf"


def test_padding_de_pagina_configuravel(service: RenameTemplateService) -> None:
    nome = service.render(
        "{Pagina}", livro="1", pagina=7, pagina_digits=2,
        data_formato="%Y%m%d", nome_original="x.pdf", extensao="pdf",
    )
    assert nome == "07.pdf"


def test_template_com_placeholder_desconhecido_lanca_erro(service: RenameTemplateService) -> None:
    with pytest.raises(TemplateInvalidoError):
        service.render(
            "{Autor}_{Pagina}", livro="15", pagina=1, pagina_digits=4,
            data_formato="%Y%m%d", nome_original="x.pdf", extensao="pdf",
        )


def test_validar_aceita_template_valido(service: RenameTemplateService) -> None:
    service.validar("{Livro}_{Pagina}")  # nao deve lancar


def test_validar_rejeita_template_invalido(service: RenameTemplateService) -> None:
    with pytest.raises(TemplateInvalidoError):
        service.validar("{Inexistente}")
