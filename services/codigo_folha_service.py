"""Le o codigo de identificacao que fica no rodape de toda folha dos
livros de escrituras do 2o Tabeliao de Rio Claro:

    SP0869 [00] LLLL FFF        (ex: SP08691083140  ou  SP0869001103150)
           ^^   ^^^^ ^^^
           |    livro folha
           incremental opcional

Regra: os 3 ultimos digitos = folha, os 4 antes = livro. O prefixo
(SP0869 + "00" opcional) e ignorado.

Ordem de tentativa (da mais barata para a mais cara):
  1. camada de texto do PDF (livros de ~2013 sao PDFs pesquisaveis)
  2. barcode Code 39 do rodape (livros novos sao so imagem)
  3. barcode em qualquer lugar da pagina

Paginas SEM esse codigo NAO sao folha do livro (sao anexos/documentos
escaneados junto) - o chamador trata isso.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pdfsuite")

_RE_CODIGO = re.compile(r"SP0869(\d{7,9})", re.IGNORECASE)


def _extrair(texto: str) -> Optional[tuple[int, int]]:
    """De um texto qualquer, tenta achar 'SP0869...' e devolver (livro, folha)."""
    if not texto:
        return None
    m = _RE_CODIGO.search(texto.replace(" ", "").upper())
    if not m:
        return None
    digitos = m.group(1)
    folha = int(digitos[-3:])
    livro = int(digitos[-7:-3])
    if not (1 <= livro <= 9999 and 1 <= folha <= 999):
        return None
    return (livro, folha)


class CodigoFolhaService:
    """Identifica (livro, folha) de uma pagina de PDF pelo codigo do rodape."""

    def __init__(self, dpi: int = 200) -> None:
        self._dpi = dpi
        self._pdfium = None
        self._zxing = None

    # ------------------------------------------------------------------ #

    def identificar(self, pdf_path: Path, pagina: int = 0) -> Optional[tuple[int, int]]:
        """Retorna (numero_livro, numero_folha) ou None se a pagina nao tiver
        o codigo (ou seja, nao for folha de livro).
        """
        do_texto = self._pela_camada_de_texto(pdf_path, pagina)
        if do_texto is not None:
            return do_texto
        return self._pelo_barcode(pdf_path, pagina)

    def disponivel(self) -> tuple[bool, str]:
        """(ok, mensagem) - False se faltam as libs de render/barcode."""
        try:
            import pypdfium2  # noqa: F401
            import zxingcpp   # noqa: F401
            return True, ""
        except ImportError as erro:
            return False, (
                f"Faltam bibliotecas para ler o codigo das imagens ({erro}). "
                "Instale com:  pip install pypdfium2 zxing-cpp pillow"
            )

    # ------------------------------------------------------------------ #

    @staticmethod
    def _pela_camada_de_texto(pdf_path: Path, pagina: int) -> Optional[tuple[int, int]]:
        try:
            from pypdf import PdfReader
            texto = PdfReader(str(pdf_path)).pages[pagina].extract_text() or ""
        except Exception as erro:  # PDF ilegivel / pagina inexistente
            logger.debug("Sem camada de texto em '%s' p%d: %s", pdf_path, pagina, erro)
            return None
        return _extrair(texto)

    def _pelo_barcode(self, pdf_path: Path, pagina: int) -> Optional[tuple[int, int]]:
        try:
            if self._pdfium is None:
                import pypdfium2 as pdfium
                import zxingcpp
                self._pdfium, self._zxing = pdfium, zxingcpp
        except ImportError:
            return None

        try:
            doc = self._pdfium.PdfDocument(str(pdf_path))
        except Exception as erro:
            logger.debug("Falha ao abrir '%s' para render: %s", pdf_path, erro)
            return None
        try:
            if pagina >= len(doc):
                return None
            imagem = doc[pagina].render(scale=self._dpi / 72).to_pil()
        except Exception as erro:
            logger.debug("Falha ao renderizar '%s' p%d: %s", pdf_path, pagina, erro)
            return None
        finally:
            try:
                doc.close()
            except Exception:
                pass

        largura, altura = imagem.size
        rodape = imagem.crop((0, int(altura * 0.86), largura, altura))
        for regiao in (rodape, imagem):
            for codigo in self._zxing.read_barcodes(regiao):
                achou = _extrair(codigo.text)
                if achou is not None:
                    return achou
        return None
