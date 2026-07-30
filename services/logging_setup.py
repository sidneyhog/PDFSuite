"""Configuracao centralizada de logging da aplicacao.

Cada execucao gera seu proprio arquivo de log (nome com timestamp), com
rotacao por tamanho como rede de seguranca para execucoes muito longas
(centenas de milhares de arquivos). Nenhum modulo do projeto usa "print"
para diagnostico - tudo passa pelo modulo logging padrao do Python.
"""
from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOGGER_NAME = "pdfsuite"


def setup_logging(logs_dir: Path, verbose: bool = False) -> logging.Logger:
    """Configura e retorna o logger raiz do PDFSuite.

    Args:
        logs_dir: pasta onde os arquivos de log sao gravados (criada se nao existir).
        verbose: se True, tambem exibe mensagens INFO no console (por padrao
            so WARNING/ERROR aparecem no console - mesmo comportamento do
            CopiarPDFs.ps1 sem -VerboseLog).
    """
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"pdfsuite_{timestamp}.log"

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # evita handlers duplicados se chamado mais de uma vez no mesmo processo

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    """Retorna o logger do PDFSuite (chame setup_logging uma vez antes, em main.py)."""
    return logging.getLogger(_LOGGER_NAME)
