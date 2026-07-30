"""Modulo 'Inventario': interacao com o usuario (input/print) para a
funcionalidade de inventario. Toda a regra de negocio real fica em
InventoryService - este modulo e propositalmente fino (Separation of
Concerns), o que o torna facil de trocar por uma futura interface grafica
sem tocar em nenhuma logica.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from models.inventory_stats import InventoryStats
from models.pdf_record import PdfRecord
from repositories.inventory_repository import InventoryRepository
from repositories.progress_repository import ProgressRepository
from services.inventory_service import InventoryService

logger = logging.getLogger("pdfsuite")


def _formatar_tamanho(bytes_: float) -> str:
    unidades = ["Bytes", "KB", "MB", "GB", "TB"]
    valor = float(bytes_)
    indice = 0
    while valor >= 1024 and indice < len(unidades) - 1:
        valor /= 1024
        indice += 1
    return f"{valor:,.2f} {unidades[indice]}" if indice else f"{valor:,.0f} {unidades[indice]}"


class InventoryModule:
    def __init__(
        self,
        config: AppConfig,
        inventory_service: InventoryService,
        inventory_repository: InventoryRepository,
        progress_repository: ProgressRepository,
    ) -> None:
        self._config = config
        self._service = inventory_service
        self._repository = inventory_repository
        self._progress = progress_repository

    def run(self) -> None:
        origem = self._perguntar_origem()
        if origem is None:
            return

        config_execucao = self._config
        if origem != self._config.origem:
            config_execucao = replace(self._config, origem=origem)

        already_processed = self._perguntar_retomada()

        print("\nEscaneando... (isso pode levar alguns minutos em acervos grandes)\n")

        cache = self._repository.load_cache()
        inicio_execucao = datetime.now()

        def _on_progress(atual: int, total: Optional[int], caminho: str) -> None:
            nome_curto = Path(caminho).name
            if total:
                percentual = (atual / total) * 100
                print(f"\r{atual}/{total} ({percentual:.1f}%) - {nome_curto[:60]:<60}", end="", flush=True)
            else:
                print(f"\r{atual} arquivos encontrados... - {nome_curto[:60]:<60}", end="", flush=True)

        def _on_checkpoint(registros: list[PdfRecord], caminho_atual: str) -> None:
            self._progress.save(registros, caminho_atual, inicio_execucao)

        try:
            registros, stats = self._service.build(
                config_execucao,
                cache=cache,
                already_processed=already_processed,
                on_progress=_on_progress,
                checkpoint_every=self._config.save_progress_every_n_files,
                on_checkpoint=_on_checkpoint,
            )
        except OSError as erro:
            print(f"\n\nErro ao acessar a origem '{origem}': {erro}\n")
            logger.error("Falha fatal no Inventario: %s", erro)
            return

        print()  # fecha a linha de progresso (impressa com \r)

        caminhos_gerados = self._repository.save(registros)
        self._progress.clear()

        self._mostrar_resumo(stats, caminhos_gerados)
        logger.info(
            "Inventario concluido: %s PDFs, %s duplicados, %s corrompidos, %s protegidos, %s vazios, "
            "%s reaproveitados do cache, %.1fs.",
            stats.pdfs_encontrados, stats.duplicados, stats.corrompidos, stats.protegidos,
            stats.vazios, stats.reaproveitados_do_cache, stats.tempo_execucao_seg,
        )

    def _perguntar_origem(self) -> Optional[Path]:
        entrada = input(f"\nPasta a escanear [{self._config.origem}]: ").strip()
        caminho = Path(entrada) if entrada else self._config.origem
        if not caminho.exists():
            print(f"\nCaminho nao encontrado: {caminho}\n")
            return None
        return caminho

    def _perguntar_retomada(self) -> Optional[dict[str, PdfRecord]]:
        if not self._progress.exists():
            return None

        registros_anteriores = self._progress.load()
        if not registros_anteriores:
            return None

        print(f"\nProgresso anterior encontrado: {len(registros_anteriores)} arquivo(s) ja processados.")
        resposta = input("Deseja continuar a execucao anterior? (S/N): ").strip().upper()

        if resposta != "S":
            self._progress.clear()
            return None

        logger.info("Retomando execucao anterior: %s arquivo(s) serao reaproveitados.", len(registros_anteriores))
        return {str(r.caminho): r for r in registros_anteriores}

    def _mostrar_resumo(self, stats: InventoryStats, caminhos_gerados: list[Path]) -> None:
        print("\n" + "=" * 58)
        print(" RESUMO DO INVENTARIO")
        print("=" * 58)
        print(f" Pastas escaneadas       : {stats.pastas_escaneadas}")
        print(f" Arquivos analisados     : {stats.arquivos_analisados}")
        print(f" PDFs encontrados        : {stats.pdfs_encontrados}")
        print(f" Tamanho total           : {_formatar_tamanho(stats.total_bytes)}")
        print(f" Total de paginas        : {stats.total_paginas}")
        print(f" Duplicados (conteudo)   : {stats.duplicados}")
        print(f" Corrompidos             : {stats.corrompidos}")
        print(f" Protegidos              : {stats.protegidos}")
        print(f" Vazios                  : {stats.vazios}")
        print(f" Reaproveitados do cache : {stats.reaproveitados_do_cache}")
        print(f" Tempo de execucao       : {stats.tempo_execucao_seg:.1f}s")
        print("=" * 58)
        for caminho in caminhos_gerados:
            print(f" Relatorio: {caminho}")
        print()
