"""Modulo 'Auditoria' - detecta PDFs corrompidos, protegidos, duplicados,
vazios, sem texto e muito grandes, com saida em CSV. Ainda nao implementado
como funcionalidade dedicada (o Inventario ja cobre corrompido/protegido/
vazio/duplicado - a Auditoria adicionara "sem texto" e "muito grande").
"""
from __future__ import annotations

from modules.placeholder_module import PlaceholderModule


class AuditModule(PlaceholderModule):
    def __init__(self) -> None:
        super().__init__("Auditoria de PDFs", "proxima sessao")
