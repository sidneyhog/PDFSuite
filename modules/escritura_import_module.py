"""Modulo 'Preparar livros para importacao': normaliza os livros de
escrituras digitalizados para o formato que o sistema do cartorio importa
- uma pasta por folha (`001`..`400`), um arquivo de folha em cada, com os
anexos junto da primeira folha correspondente.

Trabalha por faixa de livros, e retomavel (livro ja concluido e pulado) e
tem modo de simulacao (dry-run) que so mostra o plano, sem gerar nada.
Os arquivos de origem nunca sao tocados.
"""
from __future__ import annotations

import csv
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.config import AppConfig
from models.escritura_import import LivroPlano
from repositories.escritura_import_repository import EscrituraImportRepository
from services.escritura_importer_service import EscrituraImporterService
from services.escritura_planner_service import EscrituraPlannerService
from services.escritura_scanner_service import EscrituraScannerService
from services.pdf_inspector_service import PdfInspectorService
from services.rename_template_service import RenameTemplateService, TemplateInvalidoError

logger = logging.getLogger("pdfsuite")

_PREVIEW_MAX = 12
_RE_PASTA_LIVRO = re.compile(r"^livro[ _]?(\d+)$", re.IGNORECASE)


class EscrituraImportModule:
    def __init__(
        self,
        config: AppConfig,
        scanner: EscrituraScannerService,
        repository: EscrituraImportRepository,
        template_service: RenameTemplateService,
        inspector: Optional[PdfInspectorService] = None,
        importer: Optional[EscrituraImporterService] = None,
    ) -> None:
        self._config = config
        self._scanner = scanner
        self._repository = repository
        self._template_service = template_service
        self._inspector = inspector or PdfInspectorService()
        self._importer = importer or EscrituraImporterService()
        self._cache_paginas = self._carregar_cache_paginas(config.escritura_paginas_cache)

    @staticmethod
    def _carregar_cache_paginas(caminho: Optional[Path]) -> dict[str, int]:
        """Le um CSV 'Caminho;...;PaginasPDF' (saida da fase 2) para evitar
        reabrir cada PDF so para contar paginas. Chave = caminho em minusculas.
        """
        if caminho is None or not caminho.exists():
            return {}
        cache: dict[str, int] = {}
        try:
            with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
                for linha in csv.DictReader(arquivo, delimiter=";"):
                    valor = (linha.get("PaginasPDF") or "").strip()
                    if valor.isdigit():
                        cache[(linha.get("Caminho") or "").strip().lower()] = int(valor)
        except OSError as erro:
            logger.warning("Falha ao ler cache de paginas '%s': %s", caminho, erro)
        if cache:
            logger.info("Cache de paginas: %d arquivos carregados de '%s'.", len(cache), caminho)
        return cache

    def run(self) -> None:
        if self._cache_paginas:
            print(f"\nCache de paginas ativo: {len(self._cache_paginas)} arquivos (fase 2).")
        origem = self._perguntar_pasta("origem", self._config.escritura_origem)
        if origem is None:
            return
        destino = self._perguntar_pasta("destino", self._config.escritura_destino)
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

        try:
            self._template_service.validar(self._config.escritura_nome_template)
        except TemplateInvalidoError as erro:
            print(f"\nTemplate de nome invalido em config.json: {erro}\n")
            return

        dry_run = self._perguntar_sn("\nModo simulacao (nao gera nada, so mostra o plano)? [S]/[N]: ", padrao=True)
        so_ok = True
        if not dry_run:
            so_ok = self._perguntar_sn(
                "Processar apenas os livros automatizaveis (que fecham 400)? "
                "[S] Sim  [N] Tambem os que precisam de revisao: ", padrao=True
            )
        # com muitos livros, so 1 linha por livro (o detalhe fica no CSV-resumo)
        compacto = len(livros) > 6

        if not self._cache_paginas and len(livros) > 3 and dry_run:
            print(
                "\n(AVISO: sem cache de paginas - vou abrir cada arquivo de folha pela rede.\n"
                " Para acelerar, aponte 'EscrituraPaginasCache' no config.json para o CSV da fase 2.)\n"
            )

        concluidos = self._repository.concluidos()
        planos: list[LivroPlano] = []
        planejador = EscrituraPlannerService(
            contar_paginas=self._contar_paginas,
            nome_destino=self._nome_destino,
            folhas_por_livro=self._config.escritura_folhas_por_livro,
        )

        for numero, pasta in livros:
            if numero in concluidos and not dry_run:
                print(f"  livro {numero}: ja concluido, pulando.")
                continue

            livro_origem = self._scanner.scan_livro(pasta)
            plano = planejador.planejar(livro_origem, destino)
            planos.append(plano)
            if compacto:
                self._mostrar_plano_compacto(plano)
            else:
                self._mostrar_plano(plano)

            if dry_run:
                continue
            if plano.diagnostico in ("incompleto", "vazio"):
                print(f"    -> livro {numero} ({plano.diagnostico}) nao processado - precisa de digitalizacao/revisao.")
                continue
            if so_ok and not plano.automatizavel:
                print(f"    -> livro {numero} ({plano.diagnostico}) nao processado nesta execucao (so automatizaveis).")
                continue

            self._importer.executar(plano)
            self._repository.salvar_livro(plano)
            self._repository.marcar_concluido(numero)
            self._mostrar_resultado_livro(plano)

        if planos:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            caminho = self._repository.salvar_resumo(planos, timestamp)
            self._mostrar_resumo_geral(planos, dry_run, caminho)

    # ---------------- contagem de paginas ---------------- #

    def _contar_paginas(self, caminho: Path) -> int:
        do_cache = self._cache_paginas.get(str(caminho).lower())
        if do_cache is not None:
            return do_cache
        _status, paginas, _obs = self._inspector.inspect(caminho)
        return paginas or 0

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

    # ---------------- perguntas ---------------- #

    def _perguntar_pasta(self, rotulo: str, padrao: Optional[Path]) -> Optional[Path]:
        prompt = f"\nPasta de {rotulo} [{padrao}]: " if padrao else f"\nPasta de {rotulo}: "
        entrada = input(prompt).strip().strip('"')
        alvo = Path(entrada) if entrada else padrao
        if alvo is None:
            print(f"\nNenhuma pasta de {rotulo} informada.\n")
            return None
        if rotulo == "origem" and not alvo.is_dir():
            print(f"\nPasta de origem nao encontrada: '{alvo}'.\n")
            return None
        return alvo

    def _perguntar_faixa(self) -> Optional[tuple[int, int]]:
        entrada = input("\nFaixa de livros (ex: 1083-1100, ou Enter para todos): ").strip()
        if not entrada:
            return None
        numeros = [int(n) for n in re.findall(r"\d+", entrada)]
        if not numeros:
            return None
        return (min(numeros), max(numeros))

    @staticmethod
    def _perguntar_sn(prompt: str, *, padrao: bool) -> bool:
        resposta = input(prompt).strip().upper()
        if not resposta:
            return padrao
        return resposta == "S"

    # ---------------- exibicao ---------------- #

    def _descobrir_livros(self, origem: Path) -> list[tuple[int, Path]]:
        # a origem pode apontar DIRETO para uma pasta 'livroNNNN'
        m_direta = _RE_PASTA_LIVRO.match(origem.name)
        if m_direta:
            return [(int(m_direta.group(1)), origem)]

        achados: list[tuple[int, Path]] = []
        try:
            for item in origem.iterdir():
                if not item.is_dir():
                    continue
                m = _RE_PASTA_LIVRO.match(item.name)
                if m:
                    achados.append((int(m.group(1)), item))
        except OSError as erro:
            logger.error("Falha ao listar '%s': %s", origem, erro)
        return sorted(achados)

    @staticmethod
    def _mostrar_plano_compacto(plano: LivroPlano) -> None:
        marca = {"ok": "OK  ", "revisar": "REV ", "manual": "MAN ",
                 "incompleto": "INC ", "vazio": "VAZ "}.get(plano.diagnostico, "??? ")
        extra = f"  {len(plano.avisos)} aviso(s)" if plano.avisos else ""
        print(
            f"  [{marca}] livro {plano.numero}: {plano.total_folhas_conteudo} folhas de conteudo "
            f"(termina em {plano.ultima_folha_conteudo}), {len(plano.anexos)} anexos{extra}"
        )

    def _mostrar_plano(self, plano: LivroPlano) -> None:
        print(f"\n--- Livro {plano.numero}  [{plano.diagnostico.upper()}] ---")
        print(f"  Folhas de conteudo : {plano.total_folhas_conteudo} (termina na folha {plano.ultima_folha_conteudo})")
        print(f"  Folhas de destino  : {len(plano.folhas)}   Anexos: {len(plano.anexos)}")
        for f in plano.folhas[:_PREVIEW_MAX]:
            destino = f.caminho_destino
            pasta_arq = f"{destino.parent.name}/{destino.name}" if destino else "?"
            print(f"    folha {f.numero:>3} ({f.tipo:<11}) <- {f.origem.name} p.{f.pagina_origem}  ->  {pasta_arq}")
        if len(plano.folhas) > _PREVIEW_MAX:
            print(f"    ... e mais {len(plano.folhas) - _PREVIEW_MAX} folha(s)")
        for aviso in plano.avisos:
            print(f"  ! {aviso}")

    @staticmethod
    def _mostrar_resultado_livro(plano: LivroPlano) -> None:
        geradas = sum(1 for f in plano.folhas if f.status == "Gerada")
        anexos_ok = sum(1 for a in plano.anexos if a.status == "Copiado")
        erros = sum(1 for f in plano.folhas if f.status == "Erro") + \
            sum(1 for a in plano.anexos if a.status == "Erro")
        print(f"    -> {geradas} folhas geradas, {anexos_ok} anexos copiados, {erros} erro(s).")

    @staticmethod
    def _mostrar_resumo_geral(planos: list[LivroPlano], dry_run: bool, caminho_csv: Path) -> None:
        por_diag: dict[str, int] = {}
        for p in planos:
            por_diag[p.diagnostico] = por_diag.get(p.diagnostico, 0) + 1
        print("\n" + "=" * 60)
        print(" RESUMO DA IMPORTACAO" + ("  (SIMULACAO)" if dry_run else ""))
        print("=" * 60)
        for diag in ("ok", "revisar", "manual", "incompleto", "vazio"):
            if diag in por_diag:
                print(f"  {diag:<12}: {por_diag[diag]} livro(s)")
        print("=" * 60)
        print(f" Relatorio: {caminho_csv}")
        print()
