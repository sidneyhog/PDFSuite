"""Configuracao da aplicacao (equivalente ao config.json em disco)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AppConfig:
    """Configuracao carregada de config.json pelo ConfigRepository.

    Nenhum valor e fixado no codigo (hardcoded): tudo que varia entre
    maquinas/execucoes vive aqui.
    """

    origem: Path
    filtro: str = r".*\.pdf$"
    enable_hash: bool = True
    threads: int = 8
    livro_pattern: Optional[str] = None
    powershell_script_path: Optional[Path] = None
    powershell_config_path: Optional[Path] = None
    reports_dir: Path = field(default_factory=lambda: Path("reports"))
    logs_dir: Path = field(default_factory=lambda: Path("logs"))
    progress_dir: Path = field(default_factory=lambda: Path("progress"))
    save_progress_every_n_files: int = 100
    save_progress_every_seconds: int = 15
    rename_destino: Optional[Path] = None
    rename_pagina_digits: int = 4
    rename_data_formato: str = "%Y%m%d"
