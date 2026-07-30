"""Modulo 'Renomear PDFs': interacao com o usuario para a funcionalidade de
renomeacao baseada em templates configuraveis. Reaproveita o ultimo
Inventario salvo (inventario permanente) - nunca reescaneia a origem.

Os arquivos originais nunca sao tocados: a renomeacao SEMPRE copia para uma
pasta de destino separada, com resolucao de colisao de nome (NamingService)
garantindo que nada seja sobrescrito - mesma filosofia do CopiarPDFs.ps1.
"""
from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from models.pdf_record import PdfRecord
from models.rename_plan import RenamePlanItem
from repositories.inventory_repository import InventoryRepository
from repositories.rename_repository import RenameRepository
from services.naming_service import NamingService
from services.rename_template_service import RenameTemplateService, TemplateInvalidoError

logger = logging.getLogger("pdfsuite")

_TEMPLATES_PREDEFINIDOS = {
    "1": "{Livro}_{Pagina}",
    "2": "Livro-{Livro}-Pag-{Pagina}",
    "3": "{Data}_{Livro}_{Pagina}",
}

_PREVIEW_MAX = 15


class RenameModule:
    def __init__(
        self,
        config: AppConfig,
        inventory_repository: InventoryRepository,
        rename_repository: RenameRepository,
        template_service: RenameTemplateService,
    ) -> None:
        self._config = config
        self._inventory_repository = inventory_repository
        self._rename_repository = rename_repository
        self._template_service = template_service

    def run(self) -> None:
        registros = self._inventory_repository.load_all()
        if not registros:
            print(
                "\nNenhum inventario encontrado. Rode a opcao '1 - Inventario' primeiro "
                "(o modulo de Renomeacao reaproveita o inventario ja salvo, sem escanear de novo).\n"
            )
            return

        com_livro = [r for r in registros if r.livro]
        sem_livro = len(registros) - len(com_livro)
        if not com_livro:
            print(
                "\nNenhum arquivo do inventario tem um 'Livro' identificado.\n"
                "Configure 'LivroPattern' em config.json e rode o Inventario novamente.\n"
            )
            return

        template = self._perguntar_template()
        if template is None:
            return

        destino = self._perguntar_destino()
        if destino is None:
            return

        plano = self._montar_plano(com_livro, template, destino)

        if not self._mostrar_preview_e_confirmar(plano, sem_livro):
            print("\nOperacao cancelada. Nenhum arquivo foi copiado.\n")
            return

        self._executar(plano)

        caminho_csv = self._rename_repository.save(plano)
        self._mostrar_resumo(plano, sem_livro, caminho_csv)

    def _perguntar_template(self) -> Optional[str]:
        print("\nEscolha um template de renomeacao:")
        print("  1 - {Livro}_{Pagina}              (ex: 15_0001.pdf)")
        print("  2 - Livro-{Livro}-Pag-{Pagina}     (ex: Livro-15-Pag-0001.pdf)")
        print("  3 - {Data}_{Livro}_{Pagina}        (ex: 20260730_15_0001.pdf)")
        print("  4 - Customizado")

        escolha = input("Opcao [1]: ").strip() or "1"

        if escolha in _TEMPLATES_PREDEFINIDOS:
            return _TEMPLATES_PREDEFINIDOS[escolha]

        if escolha == "4":
            template = input(
                "Digite o template (placeholders: {Livro} {Pagina} {Data} {NomeOriginal}): "
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
        padrao = self._config.rename_destino
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
    ) -> list[RenamePlanItem]:
        naming = NamingService()
        naming.reservar_existentes(destino)

        por_livro: dict[str, list[PdfRecord]] = defaultdict(list)
        for registro in registros:
            por_livro[registro.livro].append(registro)  # type: ignore[index]

        plano: list[RenamePlanItem] = []
        for livro in sorted(por_livro.keys()):
            registros_do_livro = sorted(por_livro[livro], key=lambda r: r.nome)
            for indice, registro in enumerate(registros_do_livro, start=1):
                nome_base = self._template_service.render(
                    template,
                    livro=livro,
                    pagina=indice,
                    pagina_digits=self._config.rename_pagina_digits,
                    data_formato=self._config.rename_data_formato,
                    nome_original=registro.nome,
                    extensao=registro.caminho.suffix,
                )
                nome_final = naming.proximo_nome_disponivel(nome_base)

                plano.append(RenamePlanItem(
                    caminho_original=registro.caminho,
                    nome_original=registro.nome,
                    livro=livro,
                    pagina=indice,
                    nome_novo=nome_final,
                    caminho_destino=destino / nome_final,
                ))

        return plano

    def _mostrar_preview_e_confirmar(self, plano: list[RenamePlanItem], sem_livro: int) -> bool:
        print("\n" + "=" * 66)
        print(" PRE-VISUALIZACAO DA RENOMEACAO")
        print("=" * 66)
        for item in plano[:_PREVIEW_MAX]:
            print(f" {item.nome_original}  ->  {item.nome_novo}")
        if len(plano) > _PREVIEW_MAX:
            print(f" ... e mais {len(plano) - _PREVIEW_MAX} arquivo(s)")
        print("-" * 66)
        print(f" Total a copiar         : {len(plano)}")
        if sem_livro:
            print(f" Ignorados (sem Livro)  : {sem_livro}")
        print("=" * 66)

        resposta = input("\nConfirmar a copia com os novos nomes? [S] Sim  [N] Nao: ").strip().upper()
        return resposta == "S"

    def _executar(self, plano: list[RenamePlanItem]) -> None:
        for indice, item in enumerate(plano, start=1):
            item.caminho_destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                if item.caminho_destino.exists():
                    raise FileExistsError(
                        f"Arquivo de destino ja existe (colisao inesperada): '{item.caminho_destino}'."
                    )
                shutil.copy2(item.caminho_original, item.caminho_destino)
                item.status = "Copiado"
                logger.info("Renomeado '%s' -> '%s'.", item.caminho_original, item.caminho_destino)
            except OSError as erro:
                item.status = "ErroCopia"
                item.erro = str(erro)
                logger.error(
                    "Falha ao copiar '%s' para '%s': %s", item.caminho_original, item.caminho_destino, erro
                )

            print(f"\r{indice}/{len(plano)} arquivos copiados...", end="", flush=True)
        print()

    def _mostrar_resumo(self, plano: list[RenamePlanItem], sem_livro: int, caminho_csv: Path) -> None:
        copiados = sum(1 for item in plano if item.status == "Copiado")
        erros = sum(1 for item in plano if item.status == "ErroCopia")

        print("\n" + "=" * 58)
        print(" RESUMO DA RENOMEACAO")
        print("=" * 58)
        print(f" Copiados               : {copiados}")
        print(f" Erros                  : {erros}")
        print(f" Ignorados (sem Livro)  : {sem_livro}")
        print("=" * 58)
        print(f" Relatorio: {caminho_csv}")
        print()
