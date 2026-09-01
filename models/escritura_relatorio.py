"""Modelos do relatorio de escrituras para o escrevente (opcao 12).

Nao processa nada: le a arvore de saida ja gerada
(`<base>/<diagnostico>/<livro>/<NNN>/...`) e os CSV de rastreabilidade
(`reports/Importacao_livro<N>_*.csv`) e consolida tudo o que o escrevente
precisa conferir - folha a folha faltando, duplicadas, conflitos, anexos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LivroRelatorio:
    numero: int
    diagnostico: str                       # nome da pasta: ok/quase/revisar/manual/incompleto/vazio
    pasta: Path
    folhas_presentes: list[int] = field(default_factory=list)
    folhas_faltando: list[int] = field(default_factory=list)
    folhas_sem_arquivo: list[int] = field(default_factory=list)   # pasta NNN existe, sem PDF de folha
    duplicadas: dict[int, int] = field(default_factory=dict)      # folha -> nº de copias extras
    anexos_por_folha: dict[int, int] = field(default_factory=dict)
    # (folha_lida, livro_do_codigo, origem, pagina, situacao, acao_sugerida)
    conflitos: list = field(default_factory=list)
    origem_por_folha: dict[int, str] = field(default_factory=dict)
    erros: list = field(default_factory=list)                     # (folha, origem, mensagem)
    tem_abertura: bool = False
    tem_encerramento: bool = False
    diagnostico_real: str = ""            # recalculado a partir do que esta no disco
    csv_rastreio: Optional[Path] = None
    avisos: list[str] = field(default_factory=list)

    @property
    def total_anexos(self) -> int:
        return sum(self.anexos_por_folha.values())

    @property
    def total_duplicadas(self) -> int:
        return sum(self.duplicadas.values())


@dataclass
class RelatorioEscrituras:
    base_dir: Path
    gerado_em: str
    livros: list[LivroRelatorio] = field(default_factory=list)
