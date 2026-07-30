"""Orquestra a construcao do inventario: varredura + reaproveitamento de
cache + inspecao paralela + deteccao de duplicados por conteudo (hash).

Regra de negocio pura - nenhuma chamada a input()/print() aqui (isso fica
no modules/inventory_module.py). Isso e o que torna esta classe testavel
isoladamente com pytest.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from models.config import AppConfig
from models.inventory_stats import InventoryStats
from models.pdf_record import PdfRecord, PdfStatus
from services.hasher_service import HasherService
from services.pdf_inspector_service import PdfInspectorService
from services.scanner_service import ScannerService

logger = logging.getLogger("pdfsuite")

# (arquivos_processados, total_conhecido_ou_None, caminho_atual)
ProgressCallback = Callable[[int, Optional[int], str], None]
CheckpointCallback = Callable[[list[PdfRecord], str], None]


class InventoryService:
    """Regra de negocio do modulo de Inventario."""

    def __init__(
        self,
        scanner: ScannerService,
        hasher: HasherService,
        inspector: PdfInspectorService,
    ) -> None:
        self._scanner = scanner
        self._hasher = hasher
        self._inspector = inspector

    def build(
        self,
        config: AppConfig,
        cache: dict[tuple[str, int, float], PdfRecord],
        already_processed: Optional[dict[str, PdfRecord]] = None,
        on_progress: Optional[ProgressCallback] = None,
        checkpoint_every: int = 100,
        on_checkpoint: Optional[CheckpointCallback] = None,
    ) -> tuple[list[PdfRecord], InventoryStats]:
        """Executa a varredura completa e retorna os registros + estatisticas.

        `cache` e o inventario da execucao anterior indexado por
        (caminho, tamanho, mtime) - usado para pular re-hash/re-inspecao se
        nada mudou desde entao (inventario permanente).
        `already_processed` sao registros de uma execucao interrompida que
        esta sendo retomada agora (chave = caminho absoluto em string).
        """
        inicio = datetime.now()
        already_processed = already_processed or {}

        registros: list[PdfRecord] = list(already_processed.values())
        processados_paths = set(already_processed.keys())
        reaproveitados = 0
        contador_desde_checkpoint = 0

        pendentes_para_inspecionar: list[Path] = []

        for caminho in self._scanner.scan(config.origem, config.filtro):
            caminho_str = str(caminho)
            if caminho_str in processados_paths:
                continue  # ja veio de uma retomada de progresso

            try:
                stat = caminho.stat()
            except OSError as erro:
                logger.warning("Nao foi possivel acessar '%s': %s. Ignorando.", caminho, erro)
                continue

            # Normaliza o mtime pelo mesmo arredondamento que PdfRecord.chave_cache
            # aplica (via datetime, precisao de microssegundos) - comparar o
            # st_mtime bruto (float de maior precisao) contra o valor ja
            # arredondado de um registro em cache faria a chave nunca bater.
            mtime_normalizado = datetime.fromtimestamp(stat.st_mtime).timestamp()
            chave = (caminho_str, stat.st_size, mtime_normalizado)
            registro_em_cache = cache.get(chave)

            if registro_em_cache is not None:
                reaproveitados += 1
                registros.append(registro_em_cache)
                processados_paths.add(caminho_str)
                contador_desde_checkpoint += 1
            else:
                pendentes_para_inspecionar.append(caminho)

            if on_progress:
                on_progress(len(registros) + len(pendentes_para_inspecionar), None, caminho_str)

        pastas_escaneadas = self._scanner.pastas_escaneadas
        arquivos_analisados = self._scanner.arquivos_analisados
        total = len(registros) + len(pendentes_para_inspecionar)

        with ThreadPoolExecutor(max_workers=max(1, config.threads)) as executor:
            futuros = {
                executor.submit(self._inspecionar_arquivo, caminho, config): caminho
                for caminho in pendentes_para_inspecionar
            }
            for futuro in as_completed(futuros):
                caminho = futuros[futuro]
                try:
                    registro = futuro.result()
                except Exception as erro:  # isolamento: um erro individual nao aborta o lote
                    logger.error("Falha inesperada ao processar '%s': %s", caminho, erro)
                    continue

                registros.append(registro)
                processados_paths.add(str(caminho))
                contador_desde_checkpoint += 1

                if on_progress:
                    on_progress(len(registros), total, str(caminho))

                if on_checkpoint and contador_desde_checkpoint >= checkpoint_every:
                    on_checkpoint(registros, str(caminho))
                    contador_desde_checkpoint = 0

        self._marcar_duplicados(registros)

        stats = self._calcular_estatisticas(
            registros, inicio, reaproveitados, pastas_escaneadas, arquivos_analisados
        )
        return registros, stats

    def _inspecionar_arquivo(self, caminho: Path, config: AppConfig) -> PdfRecord:
        stat = caminho.stat()
        status, paginas, observacoes = self._inspector.inspect(caminho)

        sha256 = None
        if config.enable_hash:
            try:
                sha256 = self._hasher.sha256(caminho)
            except OSError as erro:
                observacoes = f"{observacoes} Falha ao calcular hash: {erro}".strip()

        livro = self._inspector.extract_livro(caminho, config.livro_pattern)

        return PdfRecord(
            caminho=caminho,
            nome=caminho.name,
            tamanho_bytes=stat.st_size,
            modificado_em=datetime.fromtimestamp(stat.st_mtime),
            status=status,
            sha256=sha256,
            paginas=paginas,
            livro=livro,
            observacoes=observacoes,
        )

    @staticmethod
    def _marcar_duplicados(registros: list[PdfRecord]) -> None:
        por_hash: dict[str, list[PdfRecord]] = defaultdict(list)
        for registro in registros:
            if registro.sha256:
                por_hash[registro.sha256].append(registro)

        for grupo in por_hash.values():
            if len(grupo) <= 1:
                continue
            original, *duplicatas = sorted(grupo, key=lambda r: str(r.caminho))
            for duplicata in duplicatas:
                duplicata.duplicado = True
                duplicata.duplicado_de = original.caminho

    @staticmethod
    def _calcular_estatisticas(
        registros: list[PdfRecord],
        inicio: datetime,
        reaproveitados: int,
        pastas_escaneadas: int,
        arquivos_analisados: int,
    ) -> InventoryStats:
        stats = InventoryStats(
            pastas_escaneadas=pastas_escaneadas,
            arquivos_analisados=arquivos_analisados,
            pdfs_encontrados=len(registros),
            reaproveitados_do_cache=reaproveitados,
        )
        for registro in registros:
            stats.total_bytes += registro.tamanho_bytes
            stats.total_paginas += registro.paginas or 0
            if registro.duplicado:
                stats.duplicados += 1
            if registro.status == PdfStatus.CORROMPIDO:
                stats.corrompidos += 1
            elif registro.status == PdfStatus.PROTEGIDO:
                stats.protegidos += 1
            elif registro.status == PdfStatus.VAZIO:
                stats.vazios += 1
        stats.tempo_execucao_seg = (datetime.now() - inicio).total_seconds()
        return stats
