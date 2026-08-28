"""Modulo 'Separar paginas': quebra cada PDF multipagina do Inventario em
arquivos individuais de 1 pagina, mantendo rastreabilidade.

Reaproveita o ultimo Inventario salvo (inventario permanente - a contagem
de paginas ja esta la, nao reabre nada para descobrir) e, como o modulo de
Renomeacao, NUNCA toca nos originais: cada pagina e gravada como um novo
arquivo no destino, com nome resolvido por template configuravel
(RenameTemplateService) + resolucao de colisao (NamingService).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from models.pdf_record import PdfRecord, PdfStatus
from models.split_plan import SplitPlanItem
from repositories.inventory_repository import InventoryRepository
from repositories.split_repository import SplitRepository
from services.naming_service import NamingService
from services.pdf_splitter_service import PdfSplitterService
from services.rename_template_service import RenameTemplateService, TemplateInvalidoError

logger = logging.getLogger("pdfsuite")

_TEMPLATES_PREDEFINIDOS = {
    "1": "{NomeOriginal}_p{Pagina}",
    "2": "{NomeOriginal}_{Pagina}-de-{TotalPaginas}",
    "3": "{Livro}_{NomeOriginal}_{Pagina}",
}

_PREVIEW_MAX = 15


class SplitModule:
    def __init__(
        self,
        config: AppConfig,
        inventory_repository: InventoryRepository,
        split_repository: SplitRepository,
        template_service: RenameTemplateService,
        splitter_service: Optional[PdfSplitterService] = None,
    ) -> None:
        self._config = config
        self._inventory_repository = inventory_repository
        self._split_repository = split_repository
        self._template_service = template_service
        self._splitter = splitter_service or PdfSplitterService()

    def run(self) -> None:
        registros = self._inventory_repository.load_all()
        if not registros:
            print(
                "\nNenhum inventario encontrado. Rode a opcao '1 - Inventario' primeiro "
                "(o modulo de Separacao reaproveita o inventario ja salvo, sem escanear de novo).\n"
            )
            return

        multipagina = [r for r in registros if self._e_multipagina(r)]
        uma_pagina = sum(1 for r in registros if r.status == PdfStatus.OK and (r.paginas or 0) == 1)
        nao_ok = sum(1 for r in registros if r.status != PdfStatus.OK)

        if not multipagina:
            print(
                "\nNenhum PDF com mais de uma pagina no inventario - nada para separar.\n"
                f"(1 pagina: {uma_pagina}  |  nao inspecionaveis: {nao_ok})\n"
            )
            return

        template = self._perguntar_template()
        if template is None:
            return

        destino = self._perguntar_destino()
        if destino is None:
            return

        plano = self._montar_plano(multipagina, template, destino)

        if not self._mostrar_preview_e_confirmar(plano, len(multipagina), uma_pagina, nao_ok):
            print("\nOperacao cancelada. Nenhum arquivo foi gerado.\n")
            return

        self._executar(plano)

        caminho_csv = self._split_repository.save(plano)
        self._mostrar_resumo(plano, len(multipagina), caminho_csv)

    @staticmethod
    def _e_multipagina(registro: PdfRecord) -> bool:
        return registro.status == PdfStatus.OK and (registro.paginas or 0) > 1

    def _perguntar_template(self) -> Optional[str]:
        print("\nEscolha um template para os arquivos de 1 pagina:")
        print("  1 - {NomeOriginal}_p{Pagina}                (ex: contrato_p0001.pdf)")
        print("  2 - {NomeOriginal}_{Pagina}-de-{TotalPaginas} (ex: contrato_0001-de-0012.pdf)")
        print("  3 - {Livro}_{NomeOriginal}_{Pagina}          (ex: 15_contrato_0001.pdf)")
        print("  4 - Customizado")

        escolha = input("Opcao [1]: ").strip() or "1"

        if escolha in _TEMPLATES_PREDEFINIDOS:
            return _TEMPLATES_PREDEFINIDOS[escolha]

        if escolha == "4":
            template = input(
                "Digite o template (placeholders: {NomeOriginal} {Pagina} {TotalPaginas} "
                "{Livro} {Data}): "
            ).strip()
            try:
                self._template_service.validar(template)
            except TemplateInvalidoError as erro:
                print(f"\n{erro}\n")
                return None
            return template

        print("\nOpcao invalida.\n")
        return None

    def _perguntar_destino(self) -> Optional[Path]:
        padrao = self._config.split_destino
        prompt = f"\nPasta de destino [{padrao}]: " if padrao else "\nPasta de destino: "
        entrada = input(prompt).strip()

        if entrada:
            return Path(entrada)
        if padrao:
            return padrao

        print("\nNenhuma pasta de destino informada.\n")
        return None

    def _montar_plano(
        self, registros: list[PdfRecord], template: str, destino: Path
    ) -> list[SplitPlanItem]:
        naming = NamingService()
        naming.reservar_existentes(destino)

        plano: list[SplitPlanItem] = []
        for registro in sorted(registros, key=lambda r: str(r.caminho)):
            total = registro.paginas or 0
            for pagina in range(1, total + 1):
                nome_base = self._template_service.render(
                    template,
                    livro=registro.livro or "",
                    pagina=pagina,
                    pagina_digits=self._config.rename_pagina_digits,
                    data_formato=self._config.rename_data_formato,
                    nome_original=registro.nome,
                    extensao=registro.caminho.suffix,
                    total_paginas=total,
                )
                nome_final = naming.proximo_nome_disponivel(nome_base)
                plano.append(SplitPlanItem(
                    caminho_original=registro.caminho,
                    nome_original=registro.nome,
                    livro=registro.livro or "",
                    paginas_total=total,
                    pagina_numero=pagina,
                    nome_novo=nome_final,
                    caminho_destino=destino / nome_final,
                ))

        return plano

    def _mostrar_preview_e_confirmar(
        self, plano: list[SplitPlanItem], arquivos: int, uma_pagina: int, nao_ok: int
    ) -> bool:
        print("\n" + "=" * 70)
        print(" PRE-VISUALIZACAO DA SEPARACAO")
        print("=" * 70)
        for item in plano[:_PREVIEW_MAX]:
            print(
                f" {item.nome_original} (pag {item.pagina_numero}/{item.paginas_total})"
                f"  ->  {item.nome_novo}"
            )
        if len(plano) > _PREVIEW_MAX:
            print(f" ... e mais {len(plano) - _PREVIEW_MAX} pagina(s)")
        print("-" * 70)
        print(f" PDFs multipagina a separar : {arquivos}")
        print(f" Paginas a gerar            : {len(plano)}")
        if uma_pagina:
            print(f" Ignorados (1 pagina)       : {uma_pagina}")
        if nao_ok:
            print(f" Ignorados (nao inspecionaveis): {nao_ok}")
        print("=" * 70)

        resposta = input("\nConfirmar a separacao? [S] Sim  [N] Nao: ").strip().upper()
        return resposta == "S"

    def _executar(self, plano: list[SplitPlanItem]) -> None:
        por_arquivo: dict[Path, list[SplitPlanItem]] = defaultdict(list)
        for item in plano:
            por_arquivo[item.caminho_original].append(item)

        feitas = 0
        for origem, itens in por_arquivo.items():
            paginas_destinos = [(item.pagina_numero, item.caminho_destino) for item in itens]
            resultados = dict(self._splitter.split(origem, paginas_destinos))

            for item in itens:
                erro = resultados.get(item.pagina_numero)
                if erro is None:
                    item.status = "Separado"
                else:
                    item.status = "ErroSeparacao"
                    item.erro = erro
                    logger.error(
                        "Falha ao separar pagina %d de '%s': %s",
                        item.pagina_numero, origem, erro,
                    )
                feitas += 1
                print(f"\r{feitas}/{len(plano)} paginas processadas...", end="", flush=True)
        print()

    def _mostrar_resumo(
        self, plano: list[SplitPlanItem], arquivos: int, caminho_csv: Path
    ) -> None:
        separadas = sum(1 for item in plano if item.status == "Separado")
        erros = sum(1 for item in plano if item.status == "ErroSeparacao")

        print("\n" + "=" * 58)
        print(" RESUMO DA SEPARACAO")
        print("=" * 58)
        print(f" PDFs multipagina processados : {arquivos}")
        print(f" Paginas geradas              : {separadas}")
        print(f" Erros                        : {erros}")
        print("=" * 58)
        print(f" Relatorio: {caminho_csv}")
        print()
