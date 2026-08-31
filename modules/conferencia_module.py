"""Modulo 'Conferir folhas pelo codigo do rodape': roda sobre a saida do
modulo de importacao de escrituras (`<destino>/<diagnostico>/<livro>/...`)
e corrige a numeracao das pastas usando o codigo real lido de cada
pagina (camada de texto do PDF ou barcode Code 39 do rodape).

Corrige NO LUGAR (nao duplica em disco). Os originais na rede nunca sao
tocados. Tem modo de simulacao e e retomavel por livro.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from models.conferencia import ConferenciaLivro
from repositories.conferencia_repository import ConferenciaRepository
from services.codigo_folha_service import CodigoFolhaService
from services.conferencia_service import ConferenciaService

logger = logging.getLogger("pdfsuite")

_DIAGS = ("ok", "quase", "revisar", "manual", "incompleto", "vazio")
_RE_NUM = re.compile(r"^\d+$")


class ConferenciaModule:
    def __init__(
        self,
        config: AppConfig,
        leitor: CodigoFolhaService,
        repository: ConferenciaRepository,
    ) -> None:
        self._config = config
        self._leitor = leitor
        self._repository = repository
        self._servico = ConferenciaService(leitor, config.escritura_folhas_por_livro)
        self._progress = config.progress_dir / "conferencia.json"

    def run(self) -> None:
        if not self._garantir_libs():
            return

        base = self._perguntar_base()
        if base is None:
            return

        livros = self._descobrir(base)
        if not livros:
            print(f"\nNada encontrado em '{base}'. Rode a importacao (opcao 9) primeiro.\n")
            return

        faixa = self._perguntar_faixa()
        if faixa:
            lo, hi = faixa
            livros = [x for x in livros if lo <= x[0] <= hi]
            if not livros:
                print(f"\nNenhum livro na faixa {lo}-{hi}.\n")
                return

        simular = self._sn("\nModo simulacao (mostra o de-para, nao move nada)? [S]/[N]: ", padrao=True)
        concluidos = self._carregar_concluidos()

        resultados: list[ConferenciaLivro] = []
        for numero, diag, pasta in livros:
            if numero in concluidos and not simular:
                print(f"  livro {numero}: ja conferido, pulando.")
                continue
            import_csv = self._achar_import_csv(numero)
            print(f"\n--- Livro {numero}  (estava em '{diag}') ---")
            res = self._servico.conferir(pasta, numero, diag, import_csv, executar=not simular)
            resultados.append(res)
            self._mostrar(res, simular)

            if not simular:
                res.movido_para = self._mover_para_diagnostico(base, diag, res)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                self._repository.salvar_livro(res, ts)
                concluidos.add(numero)
                self._salvar_concluidos(concluidos)

        if resultados:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho = self._repository.salvar_resumo(resultados, ts)
            self._resumo_geral(resultados, simular, caminho)

    # ---------------- descoberta ---------------- #

    def _descobrir(self, base: Path) -> list[tuple[int, str, Path]]:
        achados: list[tuple[int, str, Path]] = []
        for diag in _DIAGS:
            pasta_diag = base / diag
            if not pasta_diag.is_dir():
                continue
            for item in pasta_diag.iterdir():
                if item.is_dir() and _RE_NUM.match(item.name):
                    achados.append((int(item.name), diag, item))
        # fallback: <base>/<numero>/ direto (sem agrupamento por diagnostico)
        if not achados:
            for item in base.iterdir():
                if item.is_dir() and _RE_NUM.match(item.name):
                    achados.append((int(item.name), "", item))
        return sorted(achados)

    def _achar_import_csv(self, numero: int) -> Optional[Path]:
        pasta = self._config.reports_dir
        if not pasta.is_dir():
            return None
        candidatos = sorted(pasta.glob(f"Importacao_livro{numero}_*.csv"))
        return candidatos[-1] if candidatos else None

    def _mover_para_diagnostico(
        self, base: Path, diag_antes: str, res: ConferenciaLivro
    ) -> Optional[Path]:
        if not diag_antes or res.diagnostico_depois == diag_antes:
            return None
        alvo = base / res.diagnostico_depois / str(res.numero)
        if alvo.exists():
            res.avisos.append(f"nao movi para '{res.diagnostico_depois}/': ja existe")
            return None
        alvo.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(res.pasta_livro), str(alvo))
            print(f"    -> livro {res.numero}: '{diag_antes}' -> '{res.diagnostico_depois}'")
            return alvo
        except OSError as erro:
            res.avisos.append(f"falha ao mover para '{res.diagnostico_depois}/': {erro}")
            return None

    # ---------------- libs ---------------- #

    def _garantir_libs(self) -> bool:
        ok, msg = self._leitor.disponivel()
        if ok:
            return True
        print(f"\n{msg}\n")
        if not self._sn("Instalar agora (pip install pypdfium2 zxing-cpp pillow)? [S]/[N]: ", padrao=True):
            return False
        print("Instalando...")
        rc = subprocess.call(
            [sys.executable, "-m", "pip", "install", "pypdfium2", "zxing-cpp", "pillow"]
        )
        if rc != 0:
            print("\nFalha na instalacao. Instale manualmente e tente de novo.\n")
            return False
        ok, msg = self._leitor.disponivel()
        if not ok:
            print(f"\n{msg}\n")
        return ok

    # ---------------- perguntas ---------------- #

    def _perguntar_base(self) -> Optional[Path]:
        padrao = self._config.escritura_destino
        entrada = input(f"\nPasta da saida da importacao [{padrao}]: ").strip().strip('"')
        alvo = Path(entrada) if entrada else padrao
        if alvo is None or not alvo.is_dir():
            print(f"\nPasta nao encontrada: '{alvo}'.\n")
            return None
        return alvo

    def _perguntar_faixa(self) -> Optional[tuple[int, int]]:
        entrada = input("Faixa de livros (ex: 1083-1100, ou Enter para todos): ").strip()
        nums = [int(n) for n in re.findall(r"\d+", entrada)]
        if not nums:
            return None
        return (min(nums), max(nums))

    @staticmethod
    def _sn(prompt: str, *, padrao: bool) -> bool:
        r = input(prompt).strip().upper()
        return padrao if not r else r == "S"

    # ---------------- retomada ---------------- #

    def _carregar_concluidos(self) -> set[int]:
        import json
        if not self._progress.exists():
            return set()
        try:
            return {int(n) for n in json.loads(self._progress.read_text(encoding="utf-8")).get("concluidos", [])}
        except (ValueError, OSError):
            return set()

    def _salvar_concluidos(self, valores: set[int]) -> None:
        import json
        self._progress.parent.mkdir(parents=True, exist_ok=True)
        self._progress.write_text(json.dumps({"concluidos": sorted(valores)}, indent=2), encoding="utf-8")

    # ---------------- exibicao ---------------- #

    @staticmethod
    def _mostrar(res: ConferenciaLivro, simular: bool) -> None:
        movs = sum(1 for i in res.itens if i.acao == "move")
        anx = sum(1 for i in res.itens if i.acao == "vira_anexo")
        dup = sum(res.duplicadas.values())
        print(f"  folhas lidas: {len(res.folhas_reais)}   movidas: {movs}   "
              f"viraram anexo: {anx}   duplicadas: {dup}   outro livro: {res.outro_livro}")
        if res.faltando:
            amostra = ", ".join(str(f) for f in res.faltando[:10])
            print(f"  faltam folhas: {amostra}{' ...' if len(res.faltando) > 10 else ''}")
        for aviso in res.avisos:
            print(f"  ! {aviso}")
        seta = "->" if not simular else "(simulacao) ->"
        print(f"  diagnostico: {res.diagnostico_antes} {seta} {res.diagnostico_depois}")

    @staticmethod
    def _resumo_geral(resultados: list[ConferenciaLivro], simular: bool, csv_path: Path) -> None:
        antes: dict[str, int] = {}
        depois: dict[str, int] = {}
        subiu = 0
        for r in resultados:
            antes[r.diagnostico_antes] = antes.get(r.diagnostico_antes, 0) + 1
            depois[r.diagnostico_depois] = depois.get(r.diagnostico_depois, 0) + 1
            if r.diagnostico_antes != "ok" and r.diagnostico_depois == "ok":
                subiu += 1
        print("\n" + "=" * 60)
        print(" RESUMO DA CONFERENCIA" + ("  (SIMULACAO)" if simular else ""))
        print("=" * 60)
        for d in _DIAGS:
            if antes.get(d) or depois.get(d):
                print(f"  {d:<12} {antes.get(d, 0):>3}  ->  {depois.get(d, 0):>3}")
        print("-" * 60)
        print(f"  viraram 'ok': {subiu}")
        print("=" * 60)
        print(f" Relatorio: {csv_path}\n")
