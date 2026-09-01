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
  4. OCR do rodape (le os digitos impressos ao lado do barcode) - so
     entra quando 1-3 falham; recupera folhas cujo barcode nao decodifica

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


def _finalizar(digitos: str) -> Optional[tuple[int, int]]:
    """Dos 7-9 digitos depois de 'SP0869', devolve (livro, folha) se plausivel."""
    if not digitos.isdigit() or not (7 <= len(digitos) <= 9):
        return None
    folha = int(digitos[-3:])
    livro = int(digitos[-7:-3])
    if not (1 <= livro <= 9999 and 1 <= folha <= 999):
        return None
    return (livro, folha)


def _extrair(texto: str) -> Optional[tuple[int, int]]:
    """De um texto limpo (camada de texto do PDF ou barcode), acha 'SP0869...'."""
    if not texto:
        return None
    m = _RE_CODIGO.search(texto.replace(" ", "").upper())
    if not m:
        return None
    return _finalizar(m.group(1))


# O OCR confunde letra <-> digito. So normalizamos o TRECHO de 7-9 chars
# depois do "869" (nao a string toda, pra nao criar codigo do nada).
_OCR_DIGITOS = str.maketrans({
    "O": "0", "Q": "0", "D": "0", "U": "0",
    "I": "1", "L": "1", "|": "1", "!": "1",
    "Z": "2", "S": "5", "G": "6", "T": "7", "B": "8",
})
_RE_CODIGO_OCR = re.compile(r"(?:5|S)[PF]?(?:0|O|D|Q)?869([0-9OIQDULZSGTB!|]{7,9})")


def _extrair_ocr(texto: str) -> Optional[tuple[int, int]]:
    """Igual a _extrair, mas tolerante aos erros classicos de OCR no rodape."""
    if not texto:
        return None
    bruto = re.sub(r"[^0-9A-Za-z]", "", texto).upper()
    limpo = _extrair(bruto)               # tenta primeiro sem normalizar
    if limpo is not None:
        return limpo
    for m in _RE_CODIGO_OCR.finditer(bruto):
        achou = _finalizar(m.group(1).translate(_OCR_DIGITOS))
        if achou is not None:
            return achou
    return None


class CodigoFolhaService:
    """Identifica (livro, folha) de uma pagina de PDF pelo codigo do rodape."""

    def __init__(self, dpi: int = 200) -> None:
        self._dpi = dpi
        self._pdfium = None
        self._zxing = None
        self._ocr = None          # None = nao tentado; False = indisponivel

    # ------------------------------------------------------------------ #

    def identificar(self, pdf_path: Path, pagina: int = 0) -> Optional[tuple[int, int]]:
        """Retorna (numero_livro, numero_folha) ou None se a pagina nao tiver
        o codigo (ou seja, nao for folha de livro).
        """
        do_texto = self._pela_camada_de_texto(pdf_path, pagina)
        if do_texto is not None:
            return do_texto
        do_barcode = self._pelo_barcode(pdf_path, pagina)
        if do_barcode is not None:
            return do_barcode
        return self._pelo_ocr(pdf_path, pagina)

    def identificar_paginas(self, pdf_path: Path) -> list[Optional[tuple[int, int]]]:
        """Le o codigo de TODAS as paginas de um PDF, uma passada por metodo
        (abre o arquivo o minimo possivel). Retorna uma lista do tamanho do
        PDF: (livro, folha) ou None por pagina.
        """
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            paginas = reader.pages
            n = len(paginas)
        except Exception as erro:
            logger.debug("Nao consegui abrir '%s' para ler codigos: %s", pdf_path, erro)
            return []

        resultado: list[Optional[tuple[int, int]]] = [None] * n

        # 1. camada de texto (barata)
        for i in range(n):
            try:
                texto = paginas[i].extract_text() or ""
            except Exception:
                texto = ""
            resultado[i] = _extrair(texto)

        faltam = [i for i in range(n) if resultado[i] is None]
        if not faltam:
            return resultado

        # 2. barcode - abre o pdfium uma vez
        doc = None
        try:
            if self._zxing is None:
                import zxingcpp
                self._zxing = zxingcpp
            if self._pdfium is None:
                import pypdfium2 as pdfium
                self._pdfium = pdfium
            doc = self._pdfium.PdfDocument(str(pdf_path))
        except Exception as erro:
            logger.debug("Barcode indisponivel para '%s': %s", pdf_path, erro)
            doc = None

        ainda_faltam: list[int] = []
        for i in faltam:
            imagem = self._render_pagina_do_doc(doc, i) if doc is not None else None
            achou = self._ler_barcode_imagem(imagem) if imagem is not None else None
            if achou is not None:
                resultado[i] = achou
            else:
                ainda_faltam.append((i, imagem))

        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

        # 3. OCR do rodape - so no que sobrou
        engine = self._get_ocr()
        if engine is not None:
            try:
                import numpy as np
            except ImportError:
                np = None
            if np is not None:
                for i, imagem in ainda_faltam:
                    if imagem is None:
                        imagem = self._imagem_pagina(pdf_path, i)
                    if imagem is None:
                        continue
                    largura, altura = imagem.size
                    rodape = imagem.crop((0, int(altura * 0.80), largura, altura))
                    try:
                        linhas, _ = engine(np.array(rodape))
                    except Exception:
                        linhas = None
                    if linhas:
                        resultado[i] = _extrair_ocr("".join(str(l[1]) for l in linhas))

        return resultado

    def _render_pagina_do_doc(self, doc, indice: int):
        try:
            if indice >= len(doc):
                return None
            return doc[indice].render(scale=self._dpi / 72).to_pil()
        except Exception as erro:
            logger.debug("Falha ao renderizar pagina %d: %s", indice, erro)
            return None

    def _ler_barcode_imagem(self, imagem) -> Optional[tuple[int, int]]:
        if imagem is None or self._zxing is None:
            return None
        largura, altura = imagem.size
        rodape = imagem.crop((0, int(altura * 0.86), largura, altura))
        for regiao in (rodape, imagem):
            for codigo in self._zxing.read_barcodes(regiao):
                achou = _extrair(codigo.text)
                if achou is not None:
                    return achou
        return None

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

    @staticmethod
    def ocr_disponivel() -> bool:
        """True se o fallback de OCR pode ser usado (lib instalada)."""
        try:
            import rapidocr_onnxruntime  # noqa: F401
            return True
        except ImportError:
            return False

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

    def _imagem_pagina(self, pdf_path: Path, pagina: int):
        """Renderiza a pagina como PIL.Image (ou None). Cacheia o pypdfium2."""
        try:
            if self._pdfium is None:
                import pypdfium2 as pdfium
                self._pdfium = pdfium
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
            return doc[pagina].render(scale=self._dpi / 72).to_pil()
        except Exception as erro:
            logger.debug("Falha ao renderizar '%s' p%d: %s", pdf_path, pagina, erro)
            return None
        finally:
            try:
                doc.close()
            except Exception:
                pass

    def _pelo_barcode(self, pdf_path: Path, pagina: int) -> Optional[tuple[int, int]]:
        try:
            if self._zxing is None:
                import zxingcpp
                self._zxing = zxingcpp
        except ImportError:
            return None
        imagem = self._imagem_pagina(pdf_path, pagina)
        return self._ler_barcode_imagem(imagem)

    def _get_ocr(self):
        if self._ocr is False:
            return None
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            except Exception as erro:  # nao instalado ou falhou ao carregar modelos
                logger.debug("OCR indisponivel: %s", erro)
                self._ocr = False
                return None
        return self._ocr

    def _pelo_ocr(self, pdf_path: Path, pagina: int) -> Optional[tuple[int, int]]:
        engine = self._get_ocr()
        if engine is None:
            return None
        imagem = self._imagem_pagina(pdf_path, pagina)
        if imagem is None:
            return None
        try:
            import numpy as np
        except ImportError:
            return None
        largura, altura = imagem.size
        rodape = imagem.crop((0, int(altura * 0.80), largura, altura))
        try:
            resultado, _ = engine(np.array(rodape))
        except Exception as erro:
            logger.debug("Falha no OCR de '%s' p%d: %s", pdf_path, pagina, erro)
            return None
        if not resultado:
            return None
        texto = "".join(str(linha[1]) for linha in resultado)
        achou = _extrair_ocr(texto)
        if achou is not None:
            logger.debug("Codigo de '%s' recuperado por OCR: %s", pdf_path, achou)
        return achou
