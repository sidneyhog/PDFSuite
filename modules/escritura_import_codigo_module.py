"""Modulo 'Importar por codigo': normaliza os livros de escrituras num
passo so, decidindo a folha de cada pagina pelo CODIGO do rodape (nao pela
posicao). Copia + separa + confere de uma vez - sem a etapa de conferencia
posterior e sem o 'drift' dos livros antigos.

Le da origem (rede), grava a saida no destino local. Nunca toca nos
originais. Trabalha por faixa de livros, e retomavel e tem simulacao.
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from models.escritura_import import LivroPlano
from repositories.escritura_import_repository import EscrituraImportRepository
from services.codigo_folha_service import CodigoFolhaService
from services.escritura_codigo_planner_service import EscrituraCodigoPlannerService
from services.escritura_importer_service import EscrituraImporterService
from services.escritura_scanner_service import EscrituraScannerService
from services.rename_template_service import RenameTemplateService, TemplateInvalidoError

logger = logging.getLogger("pdfsuite")

_RE_PASTA_LIVRO = re.compile(r"^livro[ _]?(\d+)$", re.IGNORECASE)
_DIAGS = ("ok", "quase", "revisar", "manual", "incompleto", "vazio")


class EscrituraImportCodigoModule:
    def __init__(
        self,
        config: AppConfig,
        scanner: EscrituraScannerService,
        leitor: CodigoFolhaService,
        repository: EscrituraImportRepository,
        template_service: RenameTemplateService,
        importer: Optional[EscrituraImporterService] = None,
    ) -> None:
        self._config = config
        self._scanner = scanner
        self._leitor = leitor
        self._repository = repository
        self._template_service = template_service
        self._importer = importer or EscrituraImporterService()

    # ------------------------------------------------------------------ #

    def run(self) -> None:
        if not self._garantir_libs():
            return
        try:
            self._template_service.validar(self._config.escritura_nome_template)
        except TemplateInvalidoError as erro:
            print(f"\nTemplate de nome invalido em config.json: {erro}\n")
            return

        origem = self._perguntar_pasta("origem", self._config.escritura_origem, exige=True)
        if origem is None:
            return
        destino = self._perguntar_pasta("destino", self._config.escritura_destino, exige=False)
        if destino is None:
            return

        livros = self._descobrir_livros(origem)
        if not livros:
            print(f"\nNenhuma pasta 'livroNNNN' encontrada em '{origem}'.\n")
            return

        faixa = self._perguntar_faixa()
        if faixa is not None:
            lo, hi = faixa
            livros = [lv for lv in livros if lo <= lv[0] <= hi]
            if not livros:
                print(f"\nNenhum livro na faixa {lo}-{hi}.\n")
                return

        dry_run = self._sn("\nModo simulacao (le os codigos e mostra o plano, nao grava nada)? [S]/[N]: ", padrao=True)
        so_ok = True
        if not dry_run:
            so_ok = self._sn(
                "Gravar apenas os livros que fecham 400 na mosca? "
                "[S] Sim  [N] Tambem 'quase'/'revisar' (escrevente confere): ", padrao=True
            )

        print(
            "\n(A leitura de codigo abre e renderiza cada pagina pela rede - "
            "e mais lento que a opcao 9. Rode em lotes / deixe rodando.)\n"
        )

        planejador = EscrituraCodigoPlannerService(
            ler_codigos=self._leitor.identificar_paginas,
            nome_destino=self._nome_destino,
            folhas_por_livro=self._config.escritura_folhas_por_livro,
            agrupar_por_diagnostico=self._config.escritura_agrupar_por_diagnostico,
        )
        concluidos = self._repository.concluidos()
        compacto = len(livros) > 6
        planos: list[LivroPlano] = []

        for numero, pasta in livros:
            if numero in concluidos and not dry_run:
                print(f"  livro {numero}: ja concluido, pulando.")
                continue

            livro_origem = self._scanner.scan_livro(pasta)
            plano = planejador.planejar(livro_origem, destino)
            planos.append(plano)
            self._mostrar_plano(plano, compacto)

            if dry_run:
                continue
            if plano.diagnostico in ("incompleto", "vazio", "manual"):
                print(f"    -> livro {numero} ({plano.diagnostico}) nao gravado - tratamento a parte.")
                continue
            if so_ok and plano.diagnostico != "ok":
                print(f"    -> livro {numero} ({plano.diagnostico}) nao gravado nesta execucao.")
                continue

            self._importer.executar(plano)
            self._repository.salvar_livro(plano)
            self._repository.marcar_concluido(numero)
            self._mostrar_resultado(plano)

        if planos:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho = self._repository.salvar_resumo(planos, ts)
            pend = caminho.with_name(f"Importacao_pendencias_{ts}.csv")
            self._resumo_geral(planos, dry_run, caminho, pend if pend.exists() else None)

    # ---------------- libs ---------------- #

    def _garantir_libs(self) -> bool:
        ok, msg = self._leitor.disponivel()
        if not ok:
            print(f"\n{msg}\n")
            if not self._sn("Instalar agora (pip install pypdfium2 zxing-cpp pillow)? [S]/[N]: ", padrao=True):
                return False
            subprocess.call([sys.executable, "-m", "pip", "install", "pypdfium2", "zxing-cpp", "pillow"])
            ok, msg = self._leitor.disponivel()
            if not ok:
                print(f"\n{msg}\n")
                return False
        if not self._leitor.ocr_disponivel():
            print("\nOCR de fallback nao instalado (recupera paginas cujo barcode nao le).")
            if self._sn("Instalar agora (pip install rapidocr-onnxruntime, ~100 MB)? [S]/[N]: ", padrao=True):
                subprocess.call([sys.executable, "-m", "pip", "install", "rapidocr-onnxruntime"])
                print("OCR instalado.\n" if self._leitor.ocr_disponivel() else "OCR indisponivel; seguindo sem.\n")
            else:
                print("Seguindo sem OCR.\n")
        return True

    # ---------------- helpers ---------------- #

    def _nome_destino(self, livro: int, folha: int) -> str:
        return self._template_service.render(
            self._config.escritura_nome_template,
            livro=str(livro),
            pagina=folha,
            pagina_digits=self._config.escritura_folha_digitos,
            data_formato=self._config.rename_data_formato,
            nome_original="",
            extensao="pdf",
        )

    def _descobrir_livros(self, origem: Path) -> list[tuple[int, Path]]:
        m = _RE_PASTA_LIVRO.match(origem.name)
        if m:
            return [(int(m.group(1)), origem)]
        achados: list[tuple[int, Path]] = []
        try:
            for item in origem.iterdir():
                mm = _RE_PASTA_LIVRO.match(item.name) if item.is_dir() else None
                if mm:
                    achados.append((int(mm.group(1)), item))
        except OSError as erro:
            logger.error("Falha ao listar '%s': %s", origem, erro)
        return sorted(achados)

    def _perguntar_pasta(self, rotulo: str, padrao: Optional[Path], *, exige: bool) -> Optional[Path]:
        prompt = f"\nPasta de {rotulo} [{padrao}]: " if padrao else f"\nPasta de {rotulo}: "
        entrada = input(prompt).strip().strip('"')
        alvo = Path(entrada) if entrada else padrao
        if alvo is None:
            print(f"\nNenhuma pasta de {rotulo} informada.\n")
            return None
        if exige and not alvo.is_dir():
            print(f"\nPasta de {rotulo} nao encontrada: '{alvo}'.\n")
            return None
        return alvo

    def _perguntar_faixa(self) -> Optional[tuple[int, int]]:
        entrada = input("\nFaixa de livros (ex: 1083-1100, ou Enter para todos): ").strip()
        nums = [int(n) for n in re.findall(r"\d+", entrada)]
        return (min(nums), max(nums)) if nums else None

    @staticmethod
    def _sn(prompt: str, *, padrao: bool) -> bool:
        r = input(prompt).strip().upper()
        return padrao if not r else r == "S"

    # ---------------- exibicao ---------------- #

    @staticmethod
    def _mostrar_plano(plano: LivroPlano, compacto: bool) -> None:
        marca = {"ok": "OK   ", "quase": "QUASE", "revisar": "REV  ", "manual": "MAN  ",
                 "incompleto": "INC  ", "vazio": "VAZ  "}.get(plano.diagnostico, "???  ")
        folhas = sum(1 for f in plano.folhas if not f.duplicada)
        dups = sum(1 for f in plano.folhas if f.duplicada)
        anx = len(plano.anexos)
        cfl = len(plano.conflitos)
        if compacto:
            print(f"  [{marca}] livro {plano.numero}: {folhas} folhas, {anx} anexos"
                  f"{f', {dups} dup' if dups else ''}{f', {cfl} conflito' if cfl else ''}")
            return
        print(f"\n--- Livro {plano.numero}  [{plano.diagnostico.upper()}] ---")
        print(f"  Folhas posicionadas: {folhas} (termina em {plano.ultima_folha_conteudo})   "
              f"Anexos: {anx}   Duplicadas: {dups}   Conflitos: {cfl}")
        for aviso in plano.avisos:
            print(f"  ! {aviso}")

    @staticmethod
    def _mostrar_resultado(plano: LivroPlano) -> None:
        geradas = sum(1 for f in plano.folhas if f.status == "Gerada")
        anexos_ok = sum(1 for a in plano.anexos if a.status == "Copiado")
        erros = sum(1 for f in plano.folhas if f.status == "Erro") + \
            sum(1 for a in plano.anexos if a.status == "Erro")
        print(f"    -> {geradas} folhas, {anexos_ok} anexos, {erros} erro(s) em '{plano.pasta_destino}'")

    @staticmethod
    def _resumo_geral(planos: list[LivroPlano], dry_run: bool, csv_path: Path,
                      pendencias_path: Optional[Path]) -> None:
        por_diag: dict[str, int] = {}
        for p in planos:
            por_diag[p.diagnostico] = por_diag.get(p.diagnostico, 0) + 1
        print("\n" + "=" * 60)
        print(" RESUMO DA IMPORTACAO POR CODIGO" + ("  (SIMULACAO)" if dry_run else ""))
        print("=" * 60)
        for d in _DIAGS:
            if d in por_diag:
                print(f"  {d:<12}: {por_diag[d]} livro(s)")
        print("=" * 60)
        print(f" Resumo    : {csv_path}")
        if pendencias_path is not None:
            print(f" Pendencias: {pendencias_path}  (folha faltando / duplicada / conflito, 1 por linha)")
        print()
