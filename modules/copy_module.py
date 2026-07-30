"""Modulo 'Copiar PDFs': ponte (bridge) para o CopiarPDFs.ps1 (PowerShell),
ja validado em producao. Ainda nao existe um modulo nativo de copia em
Python - decisao arquitetural deliberada, documentada em docs/ARCHITECTURE.md.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Optional

from models.config import AppConfig

logger = logging.getLogger("pdfsuite")


class CopyModule:
    """Invoca o CopiarPDFs.ps1 existente, herdando o console do processo pai
    para que os prompts interativos do script (confirmacao S/N, retomada)
    continuem funcionando normalmente, sem reimplementar nenhuma UI aqui.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def run(self) -> None:
        script_path = self._config.powershell_script_path

        if not script_path:
            print(
                "\nO modulo de copia ainda usa o CopiarPDFs.ps1 (PowerShell), mas o "
                "caminho do script nao foi configurado.\n"
                "Defina 'PowerShellScriptPath' (e opcionalmente 'PowerShellConfigPath') "
                "em config.json e tente novamente.\n"
            )
            logger.warning("CopyModule executado sem PowerShellScriptPath configurado.")
            return

        if not script_path.exists():
            print(f"\nScript do PowerShell nao encontrado em: {script_path}\n")
            logger.error("PowerShellScriptPath configurado nao existe: %s", script_path)
            return

        comando = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]

        config_path: Optional[str] = str(self._config.powershell_config_path) if self._config.powershell_config_path else None
        if config_path:
            comando += ["-ConfigPath", config_path]

        print(f"\nExecutando {script_path.name}...\n")
        logger.info("Iniciando bridge para o PowerShell: %s", " ".join(comando))

        # Sem capturar stdin/stdout/stderr: o processo filho herda o console
        # do PDFSuite, entao os prompts interativos do script continuam
        # funcionando exatamente como se fossem chamados diretamente.
        resultado = subprocess.run(comando)

        if resultado.returncode == 0:
            logger.info("CopiarPDFs.ps1 finalizado com sucesso (codigo 0).")
        else:
            logger.warning("CopiarPDFs.ps1 finalizado com codigo %s.", resultado.returncode)

        print(f"\nCopiarPDFs.ps1 finalizado (codigo de saida {resultado.returncode}).\n")
