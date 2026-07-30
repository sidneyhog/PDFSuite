# Arquitetura do PDFSuite

## Contexto

O `CopiarPDFs.ps1` (repositório `sidneyhog/cartorio-migracao-pdfs`) resolveu um problema pontual — copiar PDFs `1_*.pdf` de uma rede para uma pasta local — e está validado em produção. O problema real por trás é maior: **gerenciar um acervo de dezenas/centenas de milhares de PDFs** (inventariar, renomear, separar páginas, unir, auditar, extrair estatísticas e, no futuro, OCR).

Decisão: o PowerShell **não é alterado** e continua existindo como ferramenta legada, independente, em seu próprio repositório. O **PDFSuite** nasce como um novo projeto em Python, pensado para crescer por anos sem precisar reescrever o que já existe.

## Camadas (Clean Architecture)

Dependência sempre aponta para dentro — uma camada só conhece a que está abaixo dela:

```
modules/       controllers finos: menu + 1 arquivo por funcionalidade.
               Leem input do usuário, mostram output, delegam tudo.
     │
services/      regra de negócio pura, testável, sem I/O de console.
     │         (Scanner, Hasher, PdfInspector, Inventory, OCR-stub, Logging)
     │
repositories/  persistência: Inventory (CSV+JSON), Config, Progress.
     │         Implementam a única parte "suja" (I/O de arquivo).
     │
models/        dataclasses + enums puros. Zero dependências de outras camadas.
```

`main.py` é a **composition root**: instancia repositories e services concretos e os injeta nos modules via construtor (Dependency Injection manual — sem framework, sem service locator, sem globais). É isso que torna cada camada testável isoladamente com dublês/fakes.

## Padrões de projeto aplicados

| Padrão | Onde | Motivo |
|---|---|---|
| **Repository** | `repositories/inventory_repository.py` | Isola persistência (CSV/JSON hoje, SQLite amanhã se necessário) da lógica de negócio. `InventoryService` não sabe como os dados são salvos. |
| **Strategy** | `repositories/report_writer.py` (`ReportWriter` Protocol, `CsvReportWriter`/`JsonReportWriter`) | Trocar/adicionar formato de saída sem tocar no `InventoryService`. Mesmo mecanismo será reaproveitado para templates de renomeação. |
| **Factory / Registry** | `modules/menu.py` (`MenuOption` + lista) | Cada opção do menu é registrada como `(número, rótulo, callable)` em `main.py`. Adicionar um módulo novo é uma linha, sem tocar no loop do menu (Open/Closed). |
| **Protocol + stub** | `services/ocr_engine.py` (`OcrEngine` Protocol + `UnavailableOcrEngine`) | Satisfaz o requisito "não implementar OCR agora, só preparar a arquitetura". Qualquer módulo futuro programa contra a interface, não contra uma biblioteca específica. |
| **Dependency Injection manual** | `main.py` | Sem framework de DI/ORM — over-engineering para este porte (viola KISS). Construtores explícitos bastam e mantêm o código rastreável. |

## Modelo de dados

- `models/pdf_record.py` — `PdfStatus` (enum: OK, Corrompido, Protegido, Vazio, ErroLeitura) e `PdfRecord` (um registro de inventário por arquivo).
- `models/inventory_stats.py` — `InventoryStats` (estatísticas agregadas de uma execução).
- `models/config.py` — `AppConfig` (equivalente tipado do `config.json`).

## Fluxo de execução — módulo de Inventário

```
main.py → Menu → "1 - Inventario" → modules/inventory_module.py
                                        │
   1. Pergunta a pasta de origem (padrão: config.json).
   2. ProgressRepository.load() → pergunta se retoma execução anterior.
   3. InventoryService.build(...)
        │
        ├─ ScannerService: varredura ITERATIVA (fila, sem recursão de pilha,
        │   os.scandir) → gera Paths sob demanda (generator — nunca
        │   materializa a árvore inteira em memória). Erro de permissão/rede
        │   numa pasta não aborta a varredura das demais.
        │
        ├─ Para cada arquivo compatível com o filtro:
        │     a) Consulta o inventário anterior (cache por
        │        caminho+tamanho+mtime). Se nada mudou → REAPROVEITA o
        │        registro (não reabre o arquivo, não re-hasheia, não
        │        reconta páginas). Este é o "inventário permanente":
        │        nenhum outro módulo futuro precisa reescanear do zero.
        │     b) Se mudou/é novo → PdfInspectorService roda em um
        │        ThreadPoolExecutor(max_workers=Threads):
        │           - HasherService.sha256() (streaming, se EnableHash=true)
        │           - contagem de páginas via pypdf.PdfReader (classifica
        │             OK / Corrompido / Protegido / Vazio / ErroLeitura)
        │           - extrai "Livro" via LivroPattern (regex configurável)
        │
        ├─ Deduplicação: agrupa por sha256 após o scan completo, marca
        │   duplicado=True nos registros que colidem (mantém o primeiro,
        │   em ordem alfabética de caminho, como original).
        │
        └─ ProgressRepository.save() a cada N arquivos (checkpoint).
   4. InventoryRepository.save(records) → reports/Inventario.csv + .json
        (Strategy: CsvReportWriter + JsonReportWriter) + cópia histórica
        com timestamp.
   5. Resumo no console + logging em cada etapa relevante.
```

## Ideias reaproveitadas do CopiarPDFs.ps1

- Varredura iterativa (fila, não recursão) e tratamento de erro por item sem abortar o scan inteiro.
- Confirmação antes de operações pesadas, resumo antes/depois, barra de progresso em texto.
- `progresso.json` / retomada de execução → `ProgressRepository` equivalente.
- **Parser de `config.json` defensivo**: o mesmo erro comum do PowerShell (colar caminho do Windows com barra simples, JSON inválido) se repete aqui — `ConfigRepository.load()` aplica a mesma correção automática (dobra barras invertidas "soltas", preservando escapes já válidos) com aviso claro, e sugere usar `/` nos caminhos.

## Riscos técnicos e mitigação

| Risco | Mitigação |
|---|---|
| `pypdf` é puro Python — parsing de página em 100k+ arquivos pode ser lento | Cache de inventário (pula arquivos inalterados) é a mitigação principal; `ThreadPoolExecutor` paraleliza I/O; a primeira varredura de um acervo grande é naturalmente mais lenta que as seguintes. |
| Arquivos corrompidos/protegidos derrubando o scan inteiro | Cada inspeção roda em try/except isolado por arquivo; falha vira status `Corrompido`/`Protegido`/`ErroLeitura` no registro, nunca interrompe o restante. |
| Caminhos longos (>260 chars) no Windows | `pathlib` + Python 3.12+ lidam bem nativamente quando o "long path support" do Windows está habilitado. |
| Ponte com o PowerShell depende de caminho local da máquina | `PowerShellScriptPath`/`PowerShellConfigPath` ficam em `config.json`, nada fixado no código; se ausente/não encontrado, a opção do menu explica o que configurar em vez de falhar silenciosamente. |
| Prompts interativos do `CopiarPDFs.ps1` (S/N) dentro da ponte | `subprocess.run(...)` **sem capturar stdin/stdout/stderr** (herda o console do processo pai) — os prompts continuam funcionando normalmente, sem reimplementar UI nenhuma em Python. |

## Por que não um framework de DI ou ORM

Um app CLI deste porte não justifica um framework de injeção de dependência nem ORM — violaria KISS. Repositórios simples (funções que leem/escrevem CSV/JSON) resolvem bem o volume esperado: centenas de milhares de registros cabem tranquilamente em CSV/JSON com leitura em streaming.

## Roteiro (visão do produto, um módulo por vez)

1. ✅ Fundação (config, logging, models, menu) + **Inventário** — completo e funcional.
2. Cópia — hoje é uma ponte (`subprocess`) para o `CopiarPDFs.ps1`; um módulo nativo em Python é um passo futuro, não urgente.
3. Renomeação — motor de templates configuráveis (`{Livro}_{Pagina}` etc.), reaproveitando o `ReportWriter`/Strategy já existente como padrão.
4. Separação de páginas — detecta PDFs com mais de uma página (o Inventário já traz essa contagem pronta) e separa mantendo rastreabilidade.
5. União de PDFs.
6. Auditoria — estende o Inventário com "sem texto" e "muito grande" (corrompido/protegido/vazio/duplicado já são cobertos pelo Inventário).
7. Relatórios/estatísticas avançadas.
8. OCR — interface (`OcrEngine`) já preparada; implementação real fica para quando houver necessidade real.
