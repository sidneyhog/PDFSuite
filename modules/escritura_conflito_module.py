"""Modulo 'Tratar conflitos e validar a saida' (opcao 13).

  1. Conflitos: paginas com codigo de outro livro (arquivadas na pasta
     errada no servidor). Se a folha do codigo FALTA no livro certo,
     copia a pagina de origem para la e re-diagnostica o livro.
  2. Validacao: cruza os reports/Importacao_livro*.csv com o que esta
     de fato no disco (e, opcional, se a origem ainda existe na rede).

Nunca apaga nada. Originais no servidor: so leitura.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from repositories.escritura_conflito_repository import EscrituraConflitoRepository
from services.codigo_folha_service import CodigoFolhaService
from services.escritura_conflito_service import EscrituraConflitoService

logger = logging.getLogger("pdfsuite")


class EscrituraConflitoModule:
    def __init__(
        self,
        config: AppConfig,
        leitor: CodigoFolhaService,
        service: EscrituraConflitoService,
        repository: EscrituraConflitoRepository,
    ) -> None:
        self._config = config
        self._leitor = leitor
        self._service = service
        self._repository = repository

    def run(self) -> None:
        base = self._perguntar_base()
        if base is None:
            return
        reports = self._config.reports_dir

        self._tratar_conflitos(base, reports)
        self._validar(base, reports)

    # ---------------- conflitos ---------------- #

    def _tratar_conflitos(self, base: Path, reports: Path) -> None:
        reproc = self._sn(
            "\nReprocessar tambem os conflitos ja marcados 'Resolvido' (re-corrigir)? [S]/[N]: ",
            padrao=False,
        )
        print("Procurando conflitos (paginas com codigo de outro livro)...")
        itens = self._service.analisar(base, reports, incluir_resolvidos=reproc)
        if not itens:
            print("  nenhum conflito registrado.\n")
            return

        copiar = [i for i in itens if i.acao == "copiar"]
        pular = [i for i in itens if i.acao != "copiar"]
        print(f"\n  {len(itens)} conflito(s): {len(copiar)} com encaixe limpo, {len(pular)} para conferir a mao.")
        for it in itens:
            marca = "COPIAR" if it.acao == "copiar" else "pular "
            print(f"   [{marca}] livro {it.livro_correto} folha {it.folha}  ({it.motivo})")
            if it.destino:
                print(f"            {it.origem}\n         -> {it.destino}")

        if not copiar:
            print("\n  nada a copiar automaticamente. Veja o relatorio (opcao 12) para os demais.\n")
            self._salvar_conflitos(itens)
            return

        if self._sn(f"\nCopiar as {len(copiar)} paginas de encaixe limpo agora? [S]/[N]: ", padrao=False):
            self._garantir_libs_se_preciso(copiar)
            res = self._service.executar(itens, base, reports)
            for it in res.itens:
                if it.status:
                    print(f"   {it.status:<7} livro {it.livro_correto} folha {it.folha}: {it.motivo}")
            for livro, (antes, depois, movido) in sorted(res.livros_rediagnosticados.items()):
                destino = f" -> {movido}" if movido else " (pasta destino ja existia)"
                print(f"   livro {livro}: {antes} -> {depois}{destino}")
            self._repository.salvar_conflitos(res, self._ts())
        else:
            print("  ok, so o relatorio entao.")
            self._salvar_conflitos(itens)

    def _salvar_conflitos(self, itens) -> None:
        from services.escritura_conflito_service import ConflitoResultado
        self._repository.salvar_conflitos(ConflitoResultado(itens=itens), self._ts())

    def _garantir_libs_se_preciso(self, copiar) -> None:
        # copia de 1 pagina nao precisa de lib; multipagina precisa do leitor
        ok, msg = self._leitor.disponivel()
        if ok:
            return
        print(f"\n  {msg}")
        if self._sn("  Instalar (pip install pypdfium2 zxing-cpp pillow)? [S]/[N]: ", padrao=True):
            subprocess.call([sys.executable, "-m", "pip", "install", "pypdfium2", "zxing-cpp", "pillow"])

    # ---------------- validacao ---------------- #

    def _validar(self, base: Path, reports: Path) -> None:
        if not self._sn("\nValidar os CSV de rastreabilidade contra o disco? [S]/[N]: ", padrao=True):
            return
        checar = self._sn("  Checar tambem se cada arquivo de origem ainda existe na rede (lento)? [S]/[N]: ", padrao=False)
        print("  validando...")
        divs = self._service.validar(base, reports, checar_origem=checar)
        if not divs:
            print("  nenhuma divergencia entre os CSV e o disco.\n")
            return
        por_tipo: dict[str, int] = {}
        for d in divs:
            por_tipo[d.tipo] = por_tipo.get(d.tipo, 0) + 1
        print(f"\n  {len(divs)} divergencia(s):")
        for tipo, qtd in sorted(por_tipo.items()):
            print(f"    {tipo:<20}: {qtd}")
        for d in divs[:20]:
            print(f"    - livro {d.livro} folha {d.folha}: {d.detalhe}")
        if len(divs) > 20:
            print(f"    ... e mais {len(divs) - 20} (ver CSV)")
        caminho = self._repository.salvar_validacao(divs, self._ts())
        print(f"\n  Detalhe: {caminho}\n")

    # ---------------- helpers ---------------- #

    def _perguntar_base(self) -> Optional[Path]:
        padrao = self._config.escritura_destino
        entrada = input(f"\nPasta da saida da importacao [{padrao}]: ").strip().strip('"')
        alvo = Path(entrada) if entrada else padrao
        if alvo is None or not alvo.is_dir():
            print(f"\nPasta nao encontrada: '{alvo}'.\n")
            return None
        return alvo

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    @staticmethod
    def _sn(prompt: str, *, padrao: bool) -> bool:
        r = input(prompt).strip().upper()
        return padrao if not r else r == "S"
