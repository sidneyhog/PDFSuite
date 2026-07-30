"""Modulo 'Configuracoes': exibe a configuracao atual carregada de
config.json (somente leitura nesta fase - a edicao continua sendo feita
diretamente no arquivo, que e a unica fonte de verdade).
"""
from __future__ import annotations

from models.config import AppConfig


class ConfigModule:
    def __init__(self, config: AppConfig, config_path: str) -> None:
        self._config = config
        self._config_path = config_path

    def run(self) -> None:
        c = self._config
        print(f"""
Configuracao atual ({self._config_path}):

  Origem                     : {c.origem}
  Filtro                     : {c.filtro}
  Calcular hash (EnableHash) : {c.enable_hash}
  Threads                    : {c.threads}
  Padrao do Livro            : {c.livro_pattern or '(nao configurado)'}
  Script PowerShell (copia)  : {c.powershell_script_path or '(nao configurado)'}
  Config do PowerShell       : {c.powershell_config_path or '(nao configurado)'}
  Pasta de relatorios        : {c.reports_dir}
  Pasta de logs              : {c.logs_dir}
  Pasta de progresso         : {c.progress_dir}

Para alterar, edite o arquivo acima e reinicie o PDFSuite.
""")
