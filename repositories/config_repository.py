"""Repositorio de configuracao: le/valida config.json e produz um AppConfig.

Reaplica a mesma correcao defensiva usada no CopiarPDFs.ps1 (PowerShell):
usuarios frequentemente colam caminhos do Windows (ex: "N:\\NOTAS\\Scanner")
sem duplicar as barras invertidas, o que quebra o JSON. Corrigimos
automaticamente apenas as barras "soltas" (que nao fazem parte de uma
sequencia de escape ja valida: \\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX) e
avisamos o usuario, em vez de falhar de cara.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from models.config import AppConfig

logger = logging.getLogger("pdfsuite")

_TEMPLATE: dict[str, Any] = {
    "Origem": "O:/",
    "Filtro": r".*\.pdf$",
    "EnableHash": True,
    "Threads": 8,
    "LivroPattern": None,
    "PowerShellScriptPath": None,
    "PowerShellConfigPath": None,
    "ReportsDir": "reports",
    "LogsDir": "logs",
    "ProgressDir": "progress",
    "SaveProgressEveryNFiles": 100,
    "SaveProgressEverySeconds": 15,
    "RenameDestino": None,
    "RenamePaginaDigits": 4,
    "RenameDataFormato": "%Y%m%d",
    "SplitDestino": None,
}

# Casa primeiro um par de escape JSON ja valido (mantendo-o intacto) - so o
# que sobrar e tratado como barra "solta" e duplicado.
_BACKSLASH_PATTERN = re.compile(r'\\["\\/bfnrtu]|\\')


def _fix_unescaped_backslashes(raw: str) -> str:
    def _replace(match: "re.Match[str]") -> str:
        return match.group(0) if len(match.group(0)) == 2 else "\\\\"

    return _BACKSLASH_PATTERN.sub(_replace, raw)


class ConfigRepository:
    """Carrega config.json do disco e o converte em um AppConfig validado."""

    def load(self, path: Path) -> AppConfig:
        if not path.exists():
            path.write_text(json.dumps(_TEMPLATE, indent=2, ensure_ascii=False), encoding="utf-8")
            raise FileNotFoundError(
                f"Arquivo de configuracao nao encontrado. Um modelo foi criado em '{path}'. "
                "Revise os valores (especialmente Origem) e execute novamente."
            )

        raw = path.read_text(encoding="utf-8")

        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as primeiro_erro:
            corrigido = _fix_unescaped_backslashes(raw)
            try:
                data = json.loads(corrigido)
                logger.warning(
                    "O arquivo '%s' continha barras invertidas nao escapadas (comum ao colar "
                    "caminhos do Windows em JSON). Corrigido automaticamente apenas para esta execucao.",
                    path,
                )
            except json.JSONDecodeError:
                dica = (
                    "\n\nDICA: em JSON, toda barra invertida dentro de um texto precisa ser duplicada.\n"
                    '  ERRADO : "Origem": "N:\\NOTAS\\Scanner"\n'
                    '  CORRETO: "Origem": "N:\\\\NOTAS\\\\Scanner"\n'
                    "Alternativa mais simples: use barra normal (/) nos caminhos:\n"
                    '  "Origem": "N:/NOTAS/Scanner"\n'
                    f"Revise o arquivo '{path}' e tente novamente."
                )
                raise ValueError(
                    f"Falha ao interpretar o JSON de configuracao em '{path}': {primeiro_erro}{dica}"
                ) from primeiro_erro

        return self._build_config(data, path)

    def _build_config(self, data: dict[str, Any], config_path: Path) -> AppConfig:
        origem = data.get("Origem")
        if not origem:
            raise ValueError("Configuracao invalida: 'Origem' nao pode ser vazio.")

        filtro = data.get("Filtro") or r".*\.pdf$"
        try:
            re.compile(filtro, re.IGNORECASE)
        except re.error as erro:
            raise ValueError(
                f"Configuracao invalida: 'Filtro' nao e uma expressao regular valida ('{filtro}'): {erro}"
            ) from erro

        livro_pattern = data.get("LivroPattern")
        if livro_pattern:
            try:
                re.compile(livro_pattern)
            except re.error as erro:
                raise ValueError(
                    f"Configuracao invalida: 'LivroPattern' nao e uma expressao regular valida: {erro}"
                ) from erro

        threads = int(data.get("Threads", 8))
        if not (1 <= threads <= 128):
            raise ValueError(
                f"Configuracao invalida: 'Threads' deve estar entre 1 e 128 (valor atual: {threads})."
            )

        base_dir = config_path.parent

        def _resolve_dir(value: Any, default_name: str) -> Path:
            resolved = Path(value) if value else Path(default_name)
            return resolved if resolved.is_absolute() else base_dir / resolved

        powershell_script_path = data.get("PowerShellScriptPath")
        powershell_config_path = data.get("PowerShellConfigPath")

        origem_path = Path(origem)
        if not origem_path.is_absolute():
            origem_path = base_dir / origem_path

        rename_destino = data.get("RenameDestino")
        rename_destino_path = _resolve_dir(rename_destino, "") if rename_destino else None

        split_destino = data.get("SplitDestino")
        split_destino_path = _resolve_dir(split_destino, "") if split_destino else None

        rename_pagina_digits = int(data.get("RenamePaginaDigits", 4))
        if rename_pagina_digits < 1:
            raise ValueError(
                f"Configuracao invalida: 'RenamePaginaDigits' deve ser no minimo 1 (valor atual: {rename_pagina_digits})."
            )

        return AppConfig(
            origem=origem_path,
            filtro=filtro,
            enable_hash=bool(data.get("EnableHash", True)),
            threads=threads,
            livro_pattern=livro_pattern,
            powershell_script_path=Path(powershell_script_path) if powershell_script_path else None,
            powershell_config_path=Path(powershell_config_path) if powershell_config_path else None,
            reports_dir=_resolve_dir(data.get("ReportsDir"), "reports"),
            logs_dir=_resolve_dir(data.get("LogsDir"), "logs"),
            progress_dir=_resolve_dir(data.get("ProgressDir"), "progress"),
            save_progress_every_n_files=int(data.get("SaveProgressEveryNFiles", 100)),
            save_progress_every_seconds=int(data.get("SaveProgressEverySeconds", 15)),
            rename_destino=rename_destino_path,
            rename_pagina_digits=rename_pagina_digits,
            rename_data_formato=data.get("RenameDataFormato") or "%Y%m%d",
            split_destino=split_destino_path,
        )
