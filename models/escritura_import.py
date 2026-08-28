"""Modelos de dominio do modulo de Importacao de livros de escrituras.

Contexto: os livros de escrituras digitalizados vivem no servidor como
`livroNNNN\\fXXX\\<prefixo>_livroNNNN_folha_XXX.pdf` (+ anexos na mesma
pasta). O sistema do cartorio importa com **uma pasta por folha** e um
arquivo de folha em cada. Cada livro tem 400 folhas: a 1 e o termo de
abertura, a 400 o de encerramento, e as 398 do meio sao o conteudo.

Parte dos arquivos de folha traz mais de uma folha no mesmo PDF (o nome
as vezes diz - `folha_311_312` -, as vezes nao); a contagem real de
paginas de cada PDF e o que fecha a conta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ArquivoFolhaOrigem:
    """Um arquivo de folha na origem (prefixo `1_` ou sem prefixo
    `livroNNNN_folha_NNN`), com os anexos que estao na mesma pasta.
    """

    caminho: Path
    pasta_scan: str                     # "f002" (ou "(raiz)")
    folha_nome_ini: Optional[int]        # folha lida do nome (para ordenar/validar)
    folha_nome_fim: Optional[int]
    anexos: list[Path] = field(default_factory=list)


@dataclass
class LivroOrigem:
    """Conteudo bruto de uma pasta `livroNNNN`, ja classificado."""

    numero: int
    pasta: Path
    termo_abertura: Optional[Path]
    termo_encerramento: Optional[Path]
    folhas: list[ArquivoFolhaOrigem]    # ordenado por folha_nome_ini, depois pasta, depois nome
    anexos_orfaos: dict[int, list[Path]] = field(default_factory=dict)   # {numero_fXXX: [anexos]} sem folha na mesma pasta
    ignorados: list[Path] = field(default_factory=list)   # Thumbs.db, .lnk, nao classificaveis
    avisos: list[str] = field(default_factory=list)


@dataclass
class FolhaDestino:
    """Uma folha de destino: 1 arquivo, 1 pasta numerada."""

    numero: int                         # 1..400
    tipo: str                           # 'abertura' | 'conteudo' | 'encerramento'
    origem: Path
    pagina_origem: int                  # pagina (1-based) dentro do PDF de origem
    nome_destino: str = ""
    caminho_destino: Optional[Path] = None
    status: str = "Pendente"            # Pendente / Gerada / Erro
    erro: str = ""


@dataclass
class AnexoDestino:
    """Um anexo copiado para a pasta da primeira folha do seu arquivo `1_`."""

    origem: Path
    folha_destino: int
    nome_destino: str = ""
    caminho_destino: Optional[Path] = None
    status: str = "Pendente"            # Pendente / Copiado / Erro
    erro: str = ""


@dataclass
class LivroPlano:
    """Plano completo de importacao de um livro, pronto para executar ou
    para exibir num dry-run.
    """

    numero: int
    pasta_origem: Path
    pasta_destino: Path
    folhas: list[FolhaDestino]
    anexos: list[AnexoDestino]
    total_folhas_conteudo: int          # quantas folhas 2..N foram geradas
    ultima_folha_conteudo: int          # deveria ser 399
    diagnostico: str                    # 'ok' | 'revisar' | 'manual' | 'incompleto' | 'vazio'
    avisos: list[str] = field(default_factory=list)

    @property
    def automatizavel(self) -> bool:
        return self.diagnostico == "ok"
