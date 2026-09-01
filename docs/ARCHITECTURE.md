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
     │         (Scanner, Hasher, PdfInspector, Inventory, RenameTemplate,
     │          Naming, PdfSplitter, OCR-stub, Logging,
     │          EscrituraScanner / EscrituraPlanner / EscrituraImporter,
     │          CodigoFolha, Conferencia)
     │
repositories/  persistência: Inventory (CSV+JSON), Config, Progress, Rename,
     │         Split, EscrituraImport, Conferencia. A parte "suja" (I/O).
     │
models/        dataclasses + enums puros. Zero dependências de outras camadas.
```

`main.py` é a **composition root**: instancia repositories e services concretos e os injeta nos modules via construtor (Dependency Injection manual — sem framework, sem service locator, sem globais). É isso que torna cada camada testável isoladamente com dublês/fakes.

## Padrões de projeto aplicados

| Padrão | Onde | Motivo |
|---|---|---|
| **Repository** | `repositories/inventory_repository.py`, `repositories/rename_repository.py` | Isola persistência (CSV/JSON hoje, SQLite amanhã se necessário) da lógica de negócio. Os services não sabem como os dados são salvos. |
| **Strategy** | `repositories/report_writer.py` (`ReportWriter` Protocol, `CsvReportWriter`/`JsonReportWriter`) | Trocar/adicionar formato de saída sem tocar no `InventoryService`. |
| **Strategy (templates)** | `services/rename_template_service.py` | Templates de nome (`{Livro}_{Pagina}`, `{NomeOriginal}_p{Pagina}` etc.) usam `str.format()` do próprio Python — nenhum parser customizado. Trocar/adicionar um placeholder é mudar o dicionário de valores, não reescrever um motor de template. **Compartilhado** pelos módulos de Renomeação e de Separação (este último usa `{Pagina}`/`{TotalPaginas}` como número físico da página). |
| **Factory / Registry** | `modules/menu.py` (`MenuOption` + lista) | Cada opção do menu é registrada como `(número, rótulo, callable)` em `main.py`. Adicionar um módulo novo é uma linha, sem tocar no loop do menu (Open/Closed). |
| **Protocol + stub** | `services/ocr_engine.py` (`OcrEngine` Protocol + `UnavailableOcrEngine`) | Satisfaz o requisito "não implementar OCR agora, só preparar a arquitetura". Qualquer módulo futuro programa contra a interface, não contra uma biblioteca específica. |
| **Dependency Injection manual** | `main.py` | Sem framework de DI/ORM — over-engineering para este porte (viola KISS). Construtores explícitos bastam e mantêm o código rastreável. |

## Modelo de dados

- `models/pdf_record.py` — `PdfStatus` (enum: OK, Corrompido, Protegido, Vazio, ErroLeitura) e `PdfRecord` (um registro de inventário por arquivo).
- `models/inventory_stats.py` — `InventoryStats` (estatísticas agregadas de uma execução).
- `models/config.py` — `AppConfig` (equivalente tipado do `config.json`).
- `models/rename_plan.py` — `RenamePlanItem` (um item planejado do módulo de Renomeação: origem, livro, página, nome novo, destino, status).
- `models/split_plan.py` — `SplitPlanItem` (um item planejado do módulo de Separação: **uma página** a extrair — origem, livro, total de páginas, número da página, nome novo, destino, status).
- `models/escritura_import.py` — `LivroOrigem` (pasta de livro classificada), `LivroPlano` (plano completo de importação, com `conflitos`), `FolhaDestino` (com `duplicada`) / `AnexoDestino` (`pagina_origem=None` → copia o arquivo inteiro; `int` → extrai só aquela página). Compartilhado pelas opções 9 e 11.
- `models/conferencia.py` — `ItemConferido` (um PDF encontrado numa pasta de folha + o que foi lido dele), `ConferenciaLivro` (resultado da conferência de um livro: folhas reais, duplicatas, faltando, diagnóstico antes/depois, `abortado_guard`).
- `models/escritura_relatorio.py` — `LivroRelatorio` / `RelatorioEscrituras` (consolidação, para o escrevente, do que já está no disco de saída — folhas faltando, duplicadas, anexos, conflitos, rastreabilidade).

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

## Fluxo de execução — módulo de Renomeação

```
main.py → Menu → "3 - Renomear PDFs" → modules/rename_module.py
                                           │
   1. InventoryRepository.load_all() → le reports/Inventario.json direto.
      NAO reescaneia nada (e o payoff do "inventario permanente" da Fase 3).
      Se vazio/inexistente → orienta a rodar o Inventario primeiro.
   2. Separa os registros com "Livro" resolvido (via LivroPattern, no
      Inventario) dos sem "Livro" - estes ultimos sao IGNORADOS do plano
      (evita gerar "None_0001.pdf"), com contagem exibida ao usuario.
   3. Pergunta o template (3 pre-definidos ou customizado, validado antes
      de aceitar) e a pasta de destino.
   4. Monta o plano (RenamePlanItem por arquivo):
        ├─ Agrupa por "Livro", ordena por nome original dentro do grupo.
        ├─ Pagina = indice sequencial (1, 2, 3...) dentro do grupo.
        ├─ RenameTemplateService.render() monta o nome (str.format()).
        └─ NamingService garante nome unico no destino (mesmo algoritmo
           sequencial corrigido do CopiarPDFs.ps1 - nunca sobrescreve,
           nem entre execucoes diferentes: reserva os nomes ja existentes
           no destino antes de planejar os novos).
   5. PRE-VISUALIZACAO (Fase 7): mostra uma amostra ANTES -> DEPOIS e pede
      confirmacao [S]/[N]. Sem confirmacao, nada e copiado.
   6. Copia cada arquivo (shutil.copy2, preserva metadados) para o
      destino - os originais NUNCA sao tocados. Erro isolado por arquivo.
   7. RenameRepository.save(plano) -> reports/Renomeacao_<timestamp>.csv
      (rastreabilidade). Resumo no console.
```

## Fluxo de execução — módulo de Separação de páginas

```
main.py → Menu → "4 - Separar paginas" → modules/split_module.py
                                            │
   1. InventoryRepository.load_all() → le reports/Inventario.json direto.
      NAO reescaneia nem reabre PDF nenhum (a contagem de paginas ja veio
      do Inventario - payoff do "inventario permanente").
   2. Filtra os registros com status OK e paginas > 1. Arquivos de 1
      pagina / corrompidos / protegidos / vazios ficam de fora, com
      contagem exibida ao usuario.
   3. Pergunta o template (3 pre-definidos ou customizado, validado) e a
      pasta de destino (padrao: SplitDestino do config.json).
   4. Monta o plano (1 SplitPlanItem por PAGINA):
        ├─ Para cada arquivo, ordena por caminho; para cada pagina 1..N:
        ├─ RenameTemplateService.render(..., total_paginas=N) monta o nome
        │   ({Pagina} = numero fisico da pagina; {TotalPaginas} = N).
        └─ NamingService garante nome unico no destino (reserva os ja
           existentes antes - nunca sobrescreve, nem entre execucoes).
   5. PRE-VISUALIZACAO: amostra "arquivo.pdf (pag 2/5) -> arquivo_p0002.pdf"
      + contagens + confirmacao [S]/[N]. Sem confirmacao, nada e gerado.
   6. PdfSplitterService.split(origem, [(pagina, destino), ...]): abre cada
      PDF de origem UMA vez (pypdf.PdfReader), grava cada pagina como um
      novo PdfWriter de 1 pagina. Erro isolado por pagina E por arquivo -
      um PDF que nem abre marca todas as suas paginas como ErroSeparacao
      sem derrubar os demais. Os originais NUNCA sao tocados.
   7. SplitRepository.save(plano) -> reports/Separacao_<timestamp>.csv
      (origem + numero da pagina -> novo arquivo + status). Resumo no console.
```

Toda a manipulação de PDF (pypdf) fica em `PdfSplitterService` — o módulo só orquestra (mesma divisão de `PdfInspectorService` no Inventário). `RenameTemplateService` e `NamingService` são reaproveitados sem alteração de comportamento para a Renomeação (o parâmetro `total_paginas` é opcional e default `0`).

**Limitação conhecida (aceita nesta versão)**: assim como a Renomeação, a Separação não tem checkpoint/retomada dedicados — reexecutar após uma interrupção regera o que já tinha sido feito, protegido apenas pela regra de não-sobrescrita do `NamingService` (gera cópias com sufixo `(N)`).

**Limitação conhecida (aceita nesta versão)**: o módulo de Renomeação não tem checkpoint/retomada dedicados (diferente do Inventário). Reexecutar após uma interrupção recopia o que já tinha sido feito — protegido apenas pela regra de não-sobrescrita do `NamingService` (gera uma cópia com sufixo `(N)`, nunca corrompe nada, mas duplica trabalho). Aceitável porque copiar é rápido comparado ao Inventário (sem hash/parsing de PDF); reavaliar se acervos muito grandes tornarem isso perceptível.

## Fluxo de execução — módulo de Preparação de livros de escrituras

```
main.py → Menu → "9 - Preparar livros ..." → modules/escritura_import_module.py
                                                 │
   1. Pergunta origem, destino, faixa de livros, simulacao?, so automatizaveis?
   2. Descobre as pastas 'livroNNNN' na faixa. Livro ja concluido
      (progress/escritura_importacao.json) e pulado.
   3. Para cada livro:
        ├─ EscrituraScannerService.scan_livro(): varredura iterativa, classifica
        │   cada arquivo (folha / anexo / termo / lixo) pelos 4 padroes de nome
        │   do acervo. Casa cada anexo com a folha da mesma pasta 'fXXX'.
        │
        ├─ EscrituraPlannerService.planejar() - LOGICA PURA (so depende de uma
        │   funcao que conta paginas, injetada = PdfInspectorService):
        │     - folha 1 = termo de abertura
        │     - folhas 2..N = paginas dos arquivos de folha, EM ORDEM. Um
        │       arquivo com P paginas ocupa P folhas consecutivas (resolve as
        │       "duplas implicitas" - o nome nem sempre diz quantas folhas tem).
        │     - anexos de um arquivo -> pasta da PRIMEIRA folha dele
        │     - folha 400 = termo de encerramento
        │     - diagnostico: ok (fecha exato) / revisar / manual / incompleto / vazio
        │
        ├─ (simulacao) mostra o plano completo e nao gera nada
        │
        └─ EscrituraImporterService.executar(): agrupa as folhas por PDF de
           origem (abre cada um UMA vez via PdfSplitterService), grava 1 pagina
           por pasta; copia os anexos (shutil.copy2). NamingService por pasta de
           destino - colisao nunca sobrescreve. Originais NUNCA tocados.
   4. EscrituraImportRepository: CSV de rastreabilidade por livro (folha a
      folha: origem -> destino -> status) + CSV-resumo + marca o livro como
      concluido.
```

**Retomada por livro** (mais grossa que a do Inventário, mais fina que a da Renomeação): a unidade e o livro inteiro, nao o arquivo. Um livro so entra em `concluidos` depois de gerado por completo.

**Por que a lógica de planejamento é um service puro**: a regra dos 400 (qual pagina vira qual folha, onde cai cada anexo, se o livro fecha ou nao) é exatamente o que precisa de teste exaustivo antes de rodar em ~40 GB de rede. `EscrituraPlannerService` não abre PDF nem toca em disco — recebe uma função `contar_paginas` e devolve um `LivroPlano`. `EscrituraFolhasPorLivro` (config, padrão 400) deixa os testes usarem livros pequenos.

## Fluxo de execução — módulo de Conferência (opção 10)

```
main.py → Menu → "10 - Conferir folhas ..." → modules/conferencia_module.py
                                                  │
   1. Garante as libs (pypdfium2 / zxing-cpp / pillow) - oferece pip install.
   2. Descobre <base>/<diagnostico>/<livro>/ na saida da importacao.
   3. Para cada livro (retomavel; progress/conferencia.json):
        ├─ CodigoFolhaService.identificar(pagina):
        │     1) camada de texto do PDF  -> regex SP0869(LLLL)(FFF)
        │     2) barcode Code 39 do rodape (render pypdfium2 + zxing-cpp)
        │     -> (livro, folha) ou None (= nao e folha do livro)
        │
        ├─ ConferenciaService.conferir() - decide, por item:
        │     folha com codigo do livro  -> vai para a pasta <folha real>
        │     folha com codigo de outro livro -> _conflitos/
        │     sem codigo (atestado escaneado junto) -> anexo da 1a folha do
        │        arquivo de origem (le o Importacao_livro<N>.csv)
        │     duplicata (mesma folha 2x) -> NNN/duplicada/ (nada e apagado)
        │
        ├─ (simulacao) so monta o de-para
        │
        └─ executa: move tudo para <livro>/_conferencia_tmp/, apaga as
           pastas NNN antigas, recoloca cada arquivo na pasta certa
           (rename na mesma unidade = instantaneo, zero disco extra).
           Re-diagnostica; se agora fecha 400, o modulo move a pasta do
           livro de 'revisar/' para 'ok/'.
   4. ConferenciaRepository: Conferencia_livro<N>_<ts>.csv (de-para item a
      item) + Conferencia_resumo_<ts>.csv (diagnostico antes -> depois).
```

O `EscrituraDestino` (`C:\Temp`) é reescrito **no lugar** (restrição de disco do cartório). Os originais na rede continuam intocados — pior caso, refaz a importação do zero. O `CodigoFolhaService` é a implementação real do que a interface `OcrEngine` sempre previu, só que a fonte primária é o **barcode/código impresso**, não OCR de texto livre.

## Ideias reaproveitadas do CopiarPDFs.ps1

- Varredura iterativa (fila, não recursão) e tratamento de erro por item sem abortar o scan inteiro.
- Confirmação antes de operações pesadas, resumo antes/depois, barra de progresso em texto.
- `progresso.json` / retomada de execução → `ProgressRepository` equivalente.
- **Parser de `config.json` defensivo**: o mesmo erro comum do PowerShell (colar caminho do Windows com barra simples, JSON inválido) se repete aqui — `ConfigRepository.load()` aplica a mesma correção automática (dobra barras invertidas "soltas", preservando escapes já válidos) com aviso claro, e sugere usar `/` nos caminhos.
- **Resolução de colisão de nome sequencial**: `services/naming_service.py` é o port direto do `Get-NextAvailableName` do PowerShell, já com a correção que evita pular números (`(2), (3), (4)...` em vez de `(2), (4), (6)...`) — bug real encontrado e corrigido lá, replicado aqui de propósito.

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
2. ✅ Cópia — ponte (`subprocess`) para o `CopiarPDFs.ps1`; um módulo nativo em Python é um passo futuro, não urgente.
3. ✅ Renomeação — motor de templates configuráveis (`{Livro}_{Pagina}` etc.), agrupamento por Livro, pré-visualização + confirmação, CSV de rastreabilidade.
4. ✅ Separação de páginas — quebra PDFs multipágina em arquivos de 1 página, template configurável (reaproveita `NamingService`/`RenameTemplateService`), pré-visualização + confirmação, CSV de rastreabilidade. Manipulação de PDF isolada em `PdfSplitterService`.
5. União de PDFs.
6. Auditoria — estende o Inventário com "sem texto" e "muito grande" (corrompido/protegido/vazio/duplicado já são cobertos pelo Inventário).
7. Relatórios/estatísticas avançadas.
8. OCR — interface (`OcrEngine`) já preparada; implementação real fica para quando houver necessidade real.
9. ✅ Preparação de livros de escrituras para importação — módulo especializado no acervo `2_Livros` do cartório. Scanner + planejador puro + importador; diagnóstico por livro; faixa de livros; retomável; modo simulação. Reaproveita `PdfSplitterService`, `PdfInspectorService`, `NamingService`, `RenameTemplateService`.
10. ✅ Conferência de folhas pelo código do rodapé — lê o código impresso (`SP0869` + livro + folha) de cada página (texto do PDF → barcode Code 39 → OCR do rodapé), corrige a numeração das pastas no lugar, separa anexos escaneados dentro de arquivos de folha, trata duplicatas e re-diagnostica. Trava anti-regressão: livro que a importação fechou como `ok` nunca é rebaixado. É a implementação real da ideia por trás de `OcrEngine`.
11. ✅ Importação de escrituras **por código** — faz cópia + separação + conferência num passo só. Para cada página de cada arquivo de folha, `CodigoFolhaService.identificar_paginas()` lê o código do rodapé e o `EscrituraCodigoPlannerService` (puro) posiciona a página na folha real; página sem código vira anexo da folha corrente; código de outro livro é conflito. Elimina o "drift" posicional dos livros de 2013 e dispensa a etapa 10. Reaproveita scanner, `PdfSplitterService`, `NamingService`, `EscrituraImporterService` e o `EscrituraImportRepository` (progress próprio). Gera também `Importacao_pendencias_<ts>.csv` (folha faltando / duplicada / conflito, 1 por linha).
12. ✅ Relatório de escrituras para o escrevente — **não reprocessa**: lê a árvore de saída já gerada (`<base>/<diagnóstico>/<livro>/`) + os `reports/Importacao_livro*.csv` e consolida numa planilha `.xlsx` com abas (Resumo, Folhas Faltando, Duplicadas, Conflitos, Anexos por Folha, Rastreabilidade). Sem `openpyxl` instalado, sai um conjunto de `.csv` (um por aba). `EscrituraRelatorioService` (varre disco + CSV) → `EscrituraRelatorioRepository` (escreve xlsx/csv).
