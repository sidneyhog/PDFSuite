"""Motor de templates para renomeacao (Strategy - mesma ideia do
ReportWriter). Usa str.format() do proprio Python: nao reinventa um parser
de template - "{Livro}_{Pagina}" ja e uma format string valida, o servico
so monta o dicionario de valores computados antes de formatar.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

PLACEHOLDERS_SUPORTADOS = (
    "Livro", "Pagina", "Data", "NomeOriginal", "Extensao", "TotalPaginas",
)


class TemplateInvalidoError(ValueError):
    """Erro ao validar ou renderizar um template de renomeacao."""


class RenameTemplateService:
    """Renderiza um nome de arquivo novo a partir de um template configuravel."""

    def render(
        self,
        template: str,
        *,
        livro: str,
        pagina: int,
        pagina_digits: int,
        data_formato: str,
        nome_original: str,
        extensao: str,
        total_paginas: int = 0,
    ) -> str:
        extensao_limpa = extensao.lstrip(".")
        valores = {
            "Livro": livro,
            "Pagina": str(pagina).zfill(pagina_digits),
            "Data": datetime.now().strftime(data_formato),
            "NomeOriginal": Path(nome_original).stem,
            "Extensao": extensao_limpa,
            # 'TotalPaginas' so faz sentido no modulo de Separacao (quantas
            # paginas o PDF de origem tinha); no de Renomeacao fica 0.
            "TotalPaginas": str(total_paginas).zfill(pagina_digits),
        }
        try:
            nome_sem_extensao = template.format(**valores)
        except (KeyError, IndexError) as erro:
            raise TemplateInvalidoError(
                f"Template invalido: placeholder desconhecido {erro}. "
                f"Placeholders suportados: {', '.join('{' + p + '}' for p in PLACEHOLDERS_SUPORTADOS)}."
            ) from erro
        except ValueError as erro:
            raise TemplateInvalidoError(f"Template invalido: {erro}") from erro

        return f"{nome_sem_extensao}.{extensao_limpa}"

    def validar(self, template: str) -> None:
        """Valida um template renderizando-o com valores de exemplo.
        Lanca TemplateInvalidoError se o template nao puder ser usado.
        """
        self.render(
            template,
            livro="15",
            pagina=1,
            pagina_digits=4,
            data_formato="%Y%m%d",
            nome_original="exemplo.pdf",
            extensao="pdf",
        )
