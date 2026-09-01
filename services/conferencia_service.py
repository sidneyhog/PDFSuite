"""Conferencia de um livro pela leitura do codigo do rodape de cada pagina.

Roda sobre a saida do modulo de importacao
(`<destino>/<diagnostico>/<livro>/<NNN>/...`) e:

  - le o codigo real de cada arquivo de folha gerado (texto do PDF,
    barcode ou OCR do rodape)
  - pagina sem codigo => nao e folha => vira anexo da primeira folha do
    arquivo de origem (usa o CSV Importacao_livro<N> para saber a origem)
  - pagina com codigo de outro livro => conflito
  - remonta as pastas pelo numero REAL da folha
  - duplicata (mesma folha 2x) => a 1a fica, as outras vao para NNN/duplicada/
  - re-diagnostica o livro no fim
  - trava: livro que a importacao fechou como 'ok' nunca e rebaixado
    (abortado_guard) - mantem a estrutura e marca para conferencia manual

Modo simulacao: monta o plano e nao move nada.
"""
from __future__ import annotations

import csv
import logging
import re
import shutil
from pathlib import Path
from typing import Optional

from models.conferencia import ConferenciaLivro, ItemConferido
from services.codigo_folha_service import CodigoFolhaService

logger = logging.getLogger("pdfsuite")

_RE_PASTA = re.compile(r"^\d+$")

# anexo que a PROPRIA conferencia criou (de uma pagina sem codigo). Numa nova
# rodada precisa ser RELIDO - se agora o OCR le o codigo, era folha e e resgatada.
_RE_ANEXO_CONFERENCIA = re.compile(r"^anexo_\d+\.pdf$", re.IGNORECASE)

# ranking dos diagnosticos (menor = melhor) para a trava anti-regressao
_ORDEM_DIAG = {"ok": 0, "quase": 1, "revisar": 2, "manual": 3, "incompleto": 3, "vazio": 4}


def _eh_folha_gerada(nome: str, numero_livro: int) -> bool:
    """True so para o arquivo que o split gerou: <livro>_folha_NNN.pdf.
    Anexos (2_livroNNNN_folha_..., pasta_..., L.####..., anexo_NN.pdf) -> False.
    """
    return bool(re.match(rf"^{numero_livro}_folha_\d+\.pdf$", nome, re.IGNORECASE))


def _precisa_ler_codigo(nome: str, numero_livro: int) -> bool:
    """Arquivos em que vale a pena tentar ler o codigo: as folhas geradas pelo
    split E os 'anexo_NN.pdf' que a conferencia criou (podem ter sido folha
    classificada errada por falha de leitura numa rodada anterior).
    Anexos pre-existentes de verdade (2_, 3_, pasta_, L.####) nao tem codigo.
    """
    return _eh_folha_gerada(nome, numero_livro) or bool(_RE_ANEXO_CONFERENCIA.match(nome))


class ConferenciaService:
    def __init__(
        self,
        leitor: CodigoFolhaService,
        folhas_por_livro: int = 400,
    ) -> None:
        self._leitor = leitor
        self._total = folhas_por_livro
        self._ultima_conteudo = folhas_por_livro - 1

    # ------------------------------------------------------------------ #

    def conferir(
        self,
        pasta_livro: Path,
        numero_livro: int,
        diagnostico_antes: str,
        import_csv: Optional[Path],
        executar: bool,
    ) -> ConferenciaLivro:
        res = ConferenciaLivro(
            numero=numero_livro, pasta_livro=pasta_livro,
            diagnostico_antes=diagnostico_antes,
        )
        primeira_folha_da_origem = self._mapa_origem(import_csv)

        # 1. varre as pastas NNN e le o codigo de cada arquivo de folha
        pastas = sorted(
            (p for p in pasta_livro.iterdir() if p.is_dir() and _RE_PASTA.match(p.name)),
            key=lambda p: int(p.name),
        )
        for pasta in pastas:
            n_pasta = int(pasta.name)
            for arquivo in sorted(pasta.glob("*.pdf"), key=lambda a: a.name.lower()):
                item = ItemConferido(
                    caminho_atual=arquivo,
                    pasta_atual=n_pasta,
                    eh_folha_gerada=_eh_folha_gerada(arquivo.name, numero_livro),
                )
                if not _precisa_ler_codigo(arquivo.name, numero_livro):
                    item.classe = "anexo"          # anexo pre-existente (2_, 3_, ...)
                else:
                    self._classificar_pelo_codigo(item, numero_livro, res)
                res.itens.append(item)

        # 1b. reabsorve o que rodadas anteriores isolaram em _conflitos/ e
        #     NNN/duplicada/ - rele cada um; com o OCR novo, o que era folha
        #     mal-lida e resgatado. O que continuar conflito/duplicata volta pra la.
        for arquivo, n_pasta in self._itens_reprocessaveis(pasta_livro):
            item = ItemConferido(
                caminho_atual=arquivo,
                pasta_atual=n_pasta,
                eh_folha_gerada=_eh_folha_gerada(arquivo.name, numero_livro),
            )
            self._classificar_pelo_codigo(item, numero_livro, res)  # sempre rele
            res.itens.append(item)

        # 2. decide o destino de cada item
        vistos: dict[int, int] = {}      # folha_real -> quantas ja vistas
        for item in res.itens:
            if item.classe == "folha":
                f = item.folha_lida
                vistos[f] = vistos.get(f, 0) + 1
                item.destino_folha = f
                if vistos[f] == 1:
                    item.acao = "mantem" if item.pasta_atual == f else "move"
                else:
                    item.acao = "duplicada"
                    res.duplicadas[f] = res.duplicadas.get(f, 0) + 1
                res.folhas_reais.add(f)
            elif item.classe == "sem_codigo":
                # pasta da 1a folha do MESMO arquivo de origem (via Importacao_livro<N>.csv)
                pasta_1a = primeira_folha_da_origem.get(item.pasta_atual, item.pasta_atual)
                # ...e a folha REAL dessa pasta (pode ter derivado tambem)
                folha_real = self._folha_real_da_pasta(res, pasta_1a)
                item.destino_folha = folha_real if folha_real is not None else (pasta_1a or None)
                if item.destino_folha:
                    item.acao = "vira_anexo"
                else:
                    # veio de _conflitos/ e continua ilegivel: sem onde posicionar
                    item.acao = "conflito"
            elif item.classe == "outro_livro":
                item.destino_folha = None
                item.acao = "conflito"
            else:  # anexo pre-existente: segue a folha da propria pasta
                seguir = self._folha_real_da_pasta(res, item.pasta_atual)
                item.destino_folha = seguir if seguir is not None else item.pasta_atual
                item.acao = "mantem" if item.destino_folha == item.pasta_atual else "move"

        # 3. calcula caminhos de destino (para o relatorio / simulacao)
        contador: dict = {}
        for item in res.itens:
            item.caminho_destino = self._caminho_destino(pasta_livro, res.numero, item, contador)

        # 4. lacunas na sequencia de conteudo
        if res.folhas_reais:
            conteudo = sorted(f for f in res.folhas_reais if 1 < f < self._total)
            if conteudo:
                res.faltando = [
                    n for n in range(2, self._ultima_conteudo + 1) if n not in res.folhas_reais
                ]
        for termo, rotulo in ((1, "abertura"), (self._total, "encerramento")):
            if termo not in res.folhas_reais:
                res.avisos.append(f"sem folha {termo} (termo de {rotulo})")

        res.diagnostico_depois = self._rediagnosticar(res)

        # 4b. trava anti-regressao: a conferencia NUNCA pode piorar um livro que a
        # importacao ja fechou como 'ok' (398 folhas exatas + os dois termos). Quando
        # isso acontece e quase sempre falha de leitura de codigo (barcode/OCR que nao
        # decodificou), nao problema real do livro. Mantem a estrutura como veio e
        # sinaliza para conferencia manual.
        if (diagnostico_antes == "ok"
                and _ORDEM_DIAG.get(res.diagnostico_depois, 9) > _ORDEM_DIAG["ok"]):
            res.abortado_guard = True
            res.avisos.insert(0, (
                "CONFERENCIA NAO APLICADA: a leitura de codigo daria '%s' "
                "(sem_codigo=%d, duplicadas=%d, faltando=%d), mas a importacao "
                "validou este livro como 'ok'. Estrutura mantida como veio; "
                "conferir manualmente." % (
                    res.diagnostico_depois, res.sem_codigo,
                    sum(res.duplicadas.values()), len(res.faltando),
                )
            ))
            res.diagnostico_depois = "ok"

        # 5. executa (move de verdade)
        if executar and not res.abortado_guard:
            self._executar(res)

        return res

    # ------------------------------------------------------------------ #

    def _executar(self, res: ConferenciaLivro) -> None:
        base = res.pasta_livro
        staging = base / "_conferencia_tmp"
        staging.mkdir(exist_ok=True)

        # 5a. tira tudo das pastas NNN para o staging (rename = instantaneo, mesmo disco)
        movidos: list[tuple[Path, ItemConferido]] = []
        for i, item in enumerate(res.itens):
            if item.acao == "conflito":
                destino = base / "_conflitos" / item.caminho_atual.name
                if item.caminho_atual == destino:
                    continue                      # ja esta em _conflitos/, nada a fazer
            elif item.acao == "duplicada":
                destino = staging / f"dup_{i}_{item.caminho_atual.name}"
            else:
                destino = staging / f"{i:04d}_{item.caminho_atual.name}"
            destino.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(item.caminho_atual), str(destino))
                movidos.append((destino, item))
            except OSError as erro:
                res.avisos.append(f"falha ao mover '{item.caminho_atual.name}': {erro}")

        # 5b. apaga as pastas NNN antigas (agora vazias), inclusive a subpasta
        #     duplicada/ que ja foi esvaziada no passo 5a
        for pasta in list(base.iterdir()):
            if pasta.is_dir() and _RE_PASTA.match(pasta.name):
                dup = pasta / "duplicada"
                if dup.is_dir():
                    try:
                        dup.rmdir()
                    except OSError:
                        pass
                try:
                    pasta.rmdir()
                except OSError:
                    pass

        # 5c. recoloca cada arquivo na pasta certa
        contador: dict = {}
        for origem_tmp, item in movidos:
            if item.acao == "conflito":
                continue
            alvo = self._caminho_destino(base, res.numero, item, contador)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(origem_tmp), str(alvo))
                item.caminho_destino = alvo
            except OSError as erro:
                res.avisos.append(f"falha ao recolocar '{origem_tmp.name}': {erro}")

        try:
            staging.rmdir()
        except OSError:
            pass

    def _caminho_destino(
        self, base: Path, numero_livro: int, item: ItemConferido, contador: dict
    ) -> Optional[Path]:
        if item.acao == "conflito" or item.destino_folha is None:
            return base / "_conflitos" / item.caminho_atual.name
        pasta = base / f"{item.destino_folha:03d}"
        livro = item.livro_lido or numero_livro

        if item.classe == "folha":
            if item.acao == "duplicada":
                contador.setdefault(("dup", pasta), 0)
                contador[("dup", pasta)] += 1
                return pasta / "duplicada" / f"{livro}_folha_{item.destino_folha:03d}_{contador[('dup', pasta)]}.pdf"
            return pasta / f"{livro}_folha_{item.destino_folha:03d}.pdf"

        if item.acao == "vira_anexo":
            contador.setdefault(("anx", pasta), 0)
            contador[("anx", pasta)] += 1
            return pasta / f"anexo_{contador[('anx', pasta)]:02d}.pdf"

        return pasta / item.caminho_atual.name    # anexo pre-existente: mantem o nome

    def _classificar_pelo_codigo(
        self, item: ItemConferido, numero_livro: int, res: ConferenciaLivro
    ) -> None:
        """Le o codigo do arquivo e define item.classe (folha/outro_livro/sem_codigo)."""
        lido = self._leitor.identificar(item.caminho_atual)
        if lido is None:
            item.classe = "sem_codigo"
            res.sem_codigo += 1
        elif lido[0] != numero_livro:
            item.classe = "outro_livro"
            item.livro_lido, item.folha_lida = lido
            res.outro_livro += 1
        else:
            item.classe = "folha"
            item.livro_lido, item.folha_lida = lido

    @staticmethod
    def _itens_reprocessaveis(pasta_livro: Path):
        """PDFs que rodadas anteriores isolaram em _conflitos/ ou NNN/duplicada/.
        Devem ser SEMPRE relidos: com o OCR novo, uma folha antes mal-lida
        volta a ser identificada e e resgatada. Yield (caminho, pasta_atual).
        """
        conflitos = pasta_livro / "_conflitos"
        if conflitos.is_dir():
            for pdf in sorted(conflitos.glob("*.pdf"), key=lambda a: a.name.lower()):
                yield pdf, 0
        for sub in sorted(pasta_livro.iterdir()):
            if sub.is_dir() and _RE_PASTA.match(sub.name):
                dup = sub / "duplicada"
                if dup.is_dir():
                    for pdf in sorted(dup.glob("*.pdf"), key=lambda a: a.name.lower()):
                        yield pdf, int(sub.name)

    @staticmethod
    def _folha_real_da_pasta(res: ConferenciaLivro, pasta_num: int) -> Optional[int]:
        for it in res.itens:
            if it.classe == "folha" and it.pasta_atual == pasta_num and it.folha_lida:
                return it.folha_lida
        return None

    @staticmethod
    def _mapa_origem(import_csv: Optional[Path]) -> dict[int, int]:
        """{pasta_numero -> primeira_folha_do_mesmo_arquivo_de_origem}."""
        if import_csv is None or not import_csv.exists():
            return {}
        try:
            linhas = list(csv.DictReader(open(import_csv, encoding="utf-8-sig"), delimiter=";"))
        except OSError:
            return {}
        primeira_por_origem: dict[str, int] = {}
        pasta_por_origem: dict[str, list[int]] = {}
        for lin in linhas:
            if lin.get("Tipo") != "conteudo":
                continue
            origem = lin.get("Origem", "")
            try:
                folha = int(lin.get("FolhaDestino") or lin.get("PastaDestino") or 0)
            except ValueError:
                continue
            pasta_por_origem.setdefault(origem, []).append(folha)
            primeira_por_origem[origem] = min(primeira_por_origem.get(origem, folha), folha)
        mapa: dict[int, int] = {}
        for origem, pastas in pasta_por_origem.items():
            primeira = primeira_por_origem[origem]
            for p in pastas:
                mapa[p] = primeira
        return mapa

    def _rediagnosticar(self, res: ConferenciaLivro) -> str:
        conteudo = sorted(f for f in res.folhas_reais if 1 < f < self._total)
        tem_abertura = 1 in res.folhas_reais
        tem_encerr = self._total in res.folhas_reais
        if res.outro_livro:
            return "revisar"
        if not conteudo:
            return "vazio"
        if len(conteudo) < (self._total - 2) * 0.9:
            return "incompleto"
        if (conteudo == list(range(2, self._ultima_conteudo + 1))
                and tem_abertura and tem_encerr and not res.duplicadas):
            return "ok"
        if res.duplicadas:
            return "revisar"
        return "quase" if len(res.faltando) <= 3 else "revisar"
