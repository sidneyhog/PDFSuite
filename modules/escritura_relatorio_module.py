"""Modulo 'Relatorio de escrituras para o escrevente': le a arvore de saida
ja processada (`<base>/<diagnostico>/<livro>/`) e os CSV de rastreabilidade
em reports/, e gera uma planilha consolidada (abas: Resumo, Folhas
Faltando, Duplicadas, Conflitos, Anexos, Rastreabilidade).

Nao reprocessa nada nem abre PDF - so consolida o que ja existe.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from repositories.escritura_relatorio_repository import EscrituraRelatorioRepository, openpyxl_disponivel
from services.escritura_relatorio_service import EscrituraRelatorioService

logger = logging.getLogger("pdfsuite")


class EscrituraRelatorioModule:
    def __init__(
        self,
        config: AppConfig,
        service: EscrituraRelatorioService,
        repository: EscrituraRelatorioRepository,
    ) -> None:
        self._config = config
        self._service = service
        self._repository = repository

    def run(self) -> None:
        base = self._perguntar_base()
        if base is None:
            return

        if not openpyxl_disponivel():
            print("\n'openpyxl' nao instalado - o relatorio sai como varios .csv (um por aba).")
            if self._sn("Instalar openpyxl agora para sair um .xlsx unico? [S]/[N]: ", padrao=True):
                subprocess.call([sys.executable, "-m", "pip", "install", "openpyxl"])
                print("openpyxl instalado.\n" if openpyxl_disponivel() else "Nao instalou; seguindo com .csv.\n")

        print(f"\nLendo '{base}' ...")
        rel = self._service.gerar(base, self._config.reports_dir)
        if not rel.livros:
            print(f"\nNenhum livro encontrado em '{base}'. Rode a importacao (opcao 9 ou 11) antes.\n")
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = self._repository.salvar(rel, ts)
        self._resumo(rel, caminho)

    # ------------------------------------------------------------------ #

    def _perguntar_base(self) -> Optional[Path]:
        padrao = self._config.escritura_destino
        entrada = input(f"\nPasta da saida da importacao [{padrao}]: ").strip().strip('"')
        alvo = Path(entrada) if entrada else padrao
        if alvo is None or not alvo.is_dir():
            print(f"\nPasta nao encontrada: '{alvo}'.\n")
            return None
        return alvo

    @staticmethod
    def _sn(prompt: str, *, padrao: bool) -> bool:
        r = input(prompt).strip().upper()
        return padrao if not r else r == "S"

    @staticmethod
    def _resumo(rel, caminho: Path) -> None:
        por_diag: dict[str, int] = {}
        faltando = dups = confl = 0
        for lv in rel.livros:
            por_diag[lv.diagnostico or "(sem)"] = por_diag.get(lv.diagnostico or "(sem)", 0) + 1
            faltando += len(lv.folhas_faltando)
            dups += lv.total_duplicadas
            confl += len(lv.conflitos)
        print("\n" + "=" * 60)
        print(" RELATORIO DE ESCRITURAS")
        print("=" * 60)
        print(f"  livros analisados : {len(rel.livros)}")
        for d, q in sorted(por_diag.items()):
            print(f"    {d:<12}: {q}")
        print(f"  folhas faltando (total) : {faltando}")
        print(f"  copias em duplicada/    : {dups}")
        print(f"  conflitos               : {confl}")
        print("=" * 60)
        print(f" Arquivo: {caminho}\n")
