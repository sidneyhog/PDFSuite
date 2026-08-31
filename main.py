"""Ponto de entrada do PDFSuite.

Composition root: monta o grafo de dependencias (repositories -> services
-> modules, injecao via construtor) e inicia o menu principal. Nenhuma
regra de negocio vive aqui - apenas montagem de objetos.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from models.config import AppConfig
from modules.audit_module import AuditModule
from modules.conferencia_module import ConferenciaModule
from modules.config_module import ConfigModule
from modules.copy_module import CopyModule
from modules.escritura_import_module import EscrituraImportModule
from modules.inventory_module import InventoryModule
from modules.menu import Menu, MenuOption
from modules.merge_module import MergeModule
from modules.rename_module import RenameModule
from modules.report_module import ReportModule
from modules.split_module import SplitModule
from repositories.conferencia_repository import ConferenciaRepository
from repositories.config_repository import ConfigRepository
from repositories.escritura_import_repository import EscrituraImportRepository
from repositories.inventory_repository import InventoryRepository
from repositories.progress_repository import ProgressRepository
from repositories.rename_repository import RenameRepository
from repositories.split_repository import SplitRepository
from services.codigo_folha_service import CodigoFolhaService
from services.escritura_importer_service import EscrituraImporterService
from services.escritura_scanner_service import EscrituraScannerService
from services.hasher_service import HasherService
from services.inventory_service import InventoryService
from services.logging_setup import setup_logging
from services.pdf_inspector_service import PdfInspectorService
from services.pdf_splitter_service import PdfSplitterService
from services.rename_template_service import RenameTemplateService
from services.scanner_service import ScannerService

_ROOT_DIR = Path(__file__).resolve().parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDFSuite - gerenciamento de acervos de PDF")
    parser.add_argument("--config", default=str(_ROOT_DIR / "config.json"), help="Caminho do config.json")
    parser.add_argument("--verbose", action="store_true", help="Exibe tambem mensagens INFO no console")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config_path = Path(args.config)

    config_repository = ConfigRepository()
    try:
        config: AppConfig = config_repository.load(config_path)
    except (FileNotFoundError, ValueError) as erro:
        print(f"\n{erro}\n")
        return 2

    logger = setup_logging(config.logs_dir, verbose=args.verbose)
    logger.info(
        "PDFSuite iniciado. Origem=%s Filtro=%s EnableHash=%s Threads=%s",
        config.origem, config.filtro, config.enable_hash, config.threads,
    )

    scanner = ScannerService()
    hasher = HasherService()
    inspector = PdfInspectorService()
    inventory_service = InventoryService(scanner, hasher, inspector)
    inventory_repository = InventoryRepository(config.reports_dir)
    progress_repository = ProgressRepository(config.progress_dir)

    inventory_module = InventoryModule(config, inventory_service, inventory_repository, progress_repository)
    copy_module = CopyModule(config)
    config_module = ConfigModule(config, str(config_path))

    rename_repository = RenameRepository(config.reports_dir)
    rename_template_service = RenameTemplateService()
    rename_module = RenameModule(config, inventory_repository, rename_repository, rename_template_service)

    split_repository = SplitRepository(config.reports_dir)
    split_module = SplitModule(
        config, inventory_repository, split_repository, rename_template_service, PdfSplitterService()
    )

    escritura_repository = EscrituraImportRepository(config.reports_dir, config.progress_dir)
    escritura_module = EscrituraImportModule(
        config,
        EscrituraScannerService(),
        escritura_repository,
        rename_template_service,
        inspector,
        EscrituraImporterService(),
    )

    conferencia_module = ConferenciaModule(
        config,
        CodigoFolhaService(),
        ConferenciaRepository(config.reports_dir),
    )

    menu = Menu(
        [
            MenuOption("1", "Inventario", inventory_module.run),
            MenuOption("2", "Copiar PDFs", copy_module.run),
            MenuOption("3", "Renomear PDFs", rename_module.run),
            MenuOption("4", "Separar paginas", split_module.run),
            MenuOption("5", "Unir PDFs", MergeModule().run),
            MenuOption("6", "Auditoria", AuditModule().run),
            MenuOption("7", "Relatorios", ReportModule().run),
            MenuOption("8", "Configuracoes", config_module.run),
            MenuOption("9", "Preparar livros de escrituras para importacao", escritura_module.run),
            MenuOption("10", "Conferir folhas pelo codigo do rodape", conferencia_module.run),
        ],
        sair_numero="11",
    )

    try:
        menu.run()
    finally:
        logger.info("PDFSuite finalizado.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
