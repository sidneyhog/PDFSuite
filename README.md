# PDFSuite

Suíte de gerenciamento de acervos de PDF (inventário, cópia, renomeação, separação, união, auditoria, relatórios e, no futuro, OCR), construída em Python seguindo Clean Architecture/SOLID para crescer por módulos sem reescrever o que já existe.

O `CopiarPDFs.ps1` (PowerShell) continua existindo, intocado, como ferramenta legada em seu próprio repositório — o PDFSuite o invoca como uma ponte na opção **2 - Copiar PDFs** do menu, em vez de reescrever a lógica de cópia agora.

> Arquitetura detalhada, padrões de projeto e roteiro dos próximos módulos: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status dos módulos

| # | Módulo | Status |
|---|---|---|
| 1 | Inventário | ✅ Completo e funcional |
| 2 | Copiar PDFs | ✅ Ponte para o `CopiarPDFs.ps1` |
| 3 | Renomear PDFs | ✅ Completo e funcional |
| 4 | Separar páginas | ✅ Completo e funcional |
| 5 | Unir PDFs | 🔜 Próxima sessão |
| 6 | Auditoria | 🔜 Próxima sessão |
| 7 | Relatórios | 🔜 Próxima sessão |
| 8 | Configurações | ✅ Exibição somente-leitura |
| 9 | Preparar livros de escrituras para importação | ✅ Completo e funcional |
| 10 | Conferir folhas pelo código do rodapé | ✅ Completo e funcional |
| — | OCR | 🔜 Apenas interface preparada (`services/ocr_engine.py`) |

## Requisitos

- Python 3.12+ (testado com 3.14)
- Windows 11 (compatibilidade alvo; o código em si é multiplataforma)

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Para rodar os testes, instale também as dependências de desenvolvimento:

```bash
pip install -r requirements-dev.txt
```

## Configuração

Edite [`config.json`](config.json):

```json
{
  "Origem": "O:/",
  "Filtro": ".*\\.pdf$",
  "EnableHash": true,
  "Threads": 8,
  "LivroPattern": null,
  "PowerShellScriptPath": "C:/caminho/para/CopiarPDFs.ps1",
  "PowerShellConfigPath": "C:/caminho/para/config.json",
  "ReportsDir": "reports",
  "LogsDir": "logs",
  "ProgressDir": "progress",
  "SaveProgressEveryNFiles": 100,
  "SaveProgressEverySeconds": 15,
  "RenameDestino": null,
  "RenamePaginaDigits": 4,
  "RenameDataFormato": "%Y%m%d",
  "SplitDestino": null,
  "EscrituraOrigem": null,
  "EscrituraDestino": null,
  "EscrituraNomeTemplate": "{Livro}_folha_{Pagina}",
  "EscrituraFolhaDigitos": 3,
  "EscrituraFolhasPorLivro": 400
}
```

| Campo | Descrição |
|---|---|
| `Origem` | Pasta/unidade de rede a ser inventariada. |
| `Filtro` | Regex (case-insensitive) aplicada ao nome do arquivo. Padrão: todos os `.pdf`. |
| `EnableHash` | Calcula SHA-256 de cada arquivo (necessário para detectar duplicados por conteúdo). |
| `Threads` | Threads usadas para inspecionar/hashear arquivos em paralelo (1–128). |
| `LivroPattern` | Regex opcional com grupo nomeado `(?P<livro>...)` para extrair o identificador do "Livro" a partir do nome do arquivo — usado pelo Inventário e necessário para o módulo de Renomeação agrupar os arquivos. |
| `PowerShellScriptPath` / `PowerShellConfigPath` | Caminhos usados pela opção "Copiar PDFs" para invocar o `CopiarPDFs.ps1`. |
| `ReportsDir` / `LogsDir` / `ProgressDir` | Pastas de saída (relativas ao `config.json` se não forem absolutas). |
| `RenameDestino` | Pasta padrão sugerida no módulo de Renomeação (editável na hora; pode ficar `null`). |
| `RenamePaginaDigits` | Quantidade de dígitos dos placeholders `{Pagina}` / `{TotalPaginas}` nos templates de Renomeação **e de Separação** (padrão 4 → `0001`). |
| `RenameDataFormato` | Formato `strftime` do placeholder `{Data}` nos templates (padrão `%Y%m%d` → `20260730`). |
| `SplitDestino` | Pasta padrão sugerida no módulo de Separação de páginas (editável na hora; pode ficar `null`). |
| `EscrituraOrigem` / `EscrituraDestino` | Pasta raiz dos livros de escrituras na origem (`...\2_Livros`) e a pasta local onde a estrutura normalizada é gerada. |
| `EscrituraNomeTemplate` | Template do nome do arquivo de folha no destino. Placeholders: `{Livro}`, `{Pagina}` (nº da folha). Padrão `{Livro}_folha_{Pagina}`. |
| `EscrituraFolhaDigitos` | Dígitos do nº da folha na pasta e no nome (padrão 3 → `002`). |
| `EscrituraFolhasPorLivro` | Total de folhas por livro, incluindo os dois termos (padrão 400). |
| `EscrituraPaginasCache` | (Opcional) CSV `Caminho;PaginasPDF` com a contagem de páginas já feita (ex.: saída da fase 2). Se informado, o módulo não reabre cada PDF só para contar — um dry-run sobre todos os livros fica quase instantâneo. |
| `EscrituraAgruparPorDiagnostico` | Se `true` (padrão), a saída fica em `<destino>/<diagnóstico>/<livro>/…` (`ok/`, `quase/`, `revisar/`); se `false`, direto em `<destino>/<livro>/…`. |

### Atenção com barras invertidas em JSON

Assim como no `CopiarPDFs.ps1`, se você colar um caminho do Windows direto do Explorer (`N:\NOTAS\Scanner`), o JSON fica inválido — toda barra invertida precisa ser duplicada (`N:\\NOTAS\\Scanner`) ou, mais simples, use barra normal (`N:/NOTAS/Scanner`). Se esquecer, o PDFSuite detecta e corrige automaticamente para aquela execução, avisando no console.

## Como executar

```bash
python main.py
```

Parâmetros opcionais:

```bash
python main.py --config caminho/outro-config.json --verbose
```

- `--config`: usa um `config.json` diferente do padrão (ao lado de `main.py`).
- `--verbose`: também exibe mensagens `INFO` no console (por padrão só `WARNING`/`ERROR` aparecem — tudo vai para o arquivo de log de qualquer forma).

## Módulo de Inventário

Escaneia a `Origem` configurada e gera, em `reports/`, `Inventario.csv` e `Inventario.json` com: nome, caminho, tamanho, hash SHA-256, número de páginas, data de modificação, "Livro" (se configurado), status (`OK`/`Corrompido`/`Protegido`/`Vazio`/`ErroLeitura`) e duplicidade (por conteúdo, via hash).

**Inventário permanente**: em execuções seguintes sobre o mesmo acervo, arquivos que não mudaram (mesmo caminho, tamanho e data de modificação) são reaproveitados do inventário anterior — não são reabertos, re-hasheados nem reinspecionados. Isso acelera muito re-varreduras de acervos grandes.

**Retomada**: se a execução for interrompida, `progress/progresso.json` guarda o que já foi processado; na próxima execução o PDFSuite pergunta se deseja continuar de onde parou.

## Módulo de Renomeação

Renomeia PDFs em lote a partir de **templates configuráveis**, sem programar regra nenhuma fixa. Reaproveita o último Inventário salvo (não escaneia a origem de novo) e **nunca toca nos arquivos originais** — sempre copia com o nome novo para uma pasta de destino.

Fluxo: escolha um template → escolha/confirme o destino → **pré-visualização** (ANTES → DEPOIS) → confirmação `[S]/[N]` → cópia.

Templates prontos (ou digite um customizado com os mesmos placeholders):

| Template | Exemplo |
|---|---|
| `{Livro}_{Pagina}` | `15_0001.pdf` |
| `Livro-{Livro}-Pag-{Pagina}` | `Livro-15-Pag-0001.pdf` |
| `{Data}_{Livro}_{Pagina}` | `20260730_15_0001.pdf` |

Placeholders disponíveis: `{Livro}` (extraído pelo `LivroPattern` do Inventário), `{Pagina}` (contador sequencial dentro de cada Livro, na ordem do nome original, zero-preenchido conforme `RenamePaginaDigits`), `{Data}` (formato `RenameDataFormato`), `{NomeOriginal}`, `{Extensao}`.

Arquivos sem `Livro` identificado no Inventário são ignorados do plano (evita gerar `None_0001.pdf`) — o resumo mostra quantos foram ignorados. Colisão de nome no destino nunca sobrescreve: recebe sufixo `(2)`, `(3)`... como no `CopiarPDFs.ps1`. Cada execução grava `reports/Renomeacao_<timestamp>.csv` com a rastreabilidade completa (original → novo nome).

## Módulo de Separação de páginas

Quebra cada PDF **com mais de uma página** do Inventário em arquivos individuais de 1 página. Reaproveita o último Inventário salvo (a contagem de páginas já está lá — não reabre nada para descobrir) e, como a Renomeação, **nunca toca nos originais**: cada página é gravada como um novo arquivo na pasta de destino.

Fluxo: escolha um template → escolha/confirme o destino → **pré-visualização** (`arquivo.pdf (pag 2/5) → arquivo_p0002.pdf`) → confirmação `[S]/[N]` → separação.

Templates prontos (ou digite um customizado):

| Template | Exemplo |
|---|---|
| `{NomeOriginal}_p{Pagina}` | `contrato_p0001.pdf` |
| `{NomeOriginal}_{Pagina}-de-{TotalPaginas}` | `contrato_0001-de-0012.pdf` |
| `{Livro}_{NomeOriginal}_{Pagina}` | `15_contrato_0001.pdf` |

Placeholders: `{NomeOriginal}`, `{Pagina}` (número físico da página no PDF de origem, 1‑based, zero‑preenchido conforme `RenamePaginaDigits`), `{TotalPaginas}` (total de páginas do PDF de origem), `{Livro}` (se o Inventário identificou, via `LivroPattern` — senão fica vazio), `{Data}`, `{Extensao}`.

Só entram no plano PDFs com status `OK` e mais de uma página. Arquivos de 1 página, corrompidos, protegidos ou vazios são ignorados — o resumo mostra as contagens. Colisão de nome no destino nunca sobrescreve (sufixo `(2)`, `(3)`...). Uma página problemática (ou um PDF inteiro que não abre) vira status `ErroSeparacao` no relatório, sem interromper o restante. Cada execução grava `reports/Separacao_<timestamp>.csv` com a rastreabilidade (origem + página → novo arquivo + status).

## Módulo de Preparação de livros de escrituras

Normaliza os livros de escrituras digitalizados (`livroNNNN\fXXX\<prefixo>_livroNNNN_folha_XXX.pdf` + anexos) para o formato que o sistema do cartório importa: **uma pasta por folha** (`001`..`400`), com um arquivo de folha em cada e os anexos junto da primeira folha correspondente. Módulo especializado neste acervo — não é uma ferramenta de PDF genérica.

Fluxo, **por livro**:

1. **Varre** a pasta do livro (`EscrituraScannerService`) e classifica: folha (`1_` ou `livroNNNN_folha_NNN`), anexo (`2_`..`13_`, `pasta_`, `L.####,fls`), termo de abertura/encerramento, lixo (`Thumbs.db`, `.lnk`).
2. **Conta as páginas** de cada arquivo de folha (`PdfInspectorService`, ou o cache da fase de análise — ver `EscrituraPaginasCache`) — é o que resolve as folhas que vêm com 2+ páginas num só PDF sem dizer no nome.
3. **Planeja** (`EscrituraPlannerService`, lógica pura): folha 1 = termo de abertura, folhas 2..399 = as páginas dos arquivos de folha em ordem, folha 400 = termo de encerramento. Cada arquivo de folha com N páginas ocupa N folhas consecutivas; os anexos dele vão para a pasta da **primeira** dessas folhas. Anexo numa pasta `fXXX` sem arquivo de folha → vai para a folha XXX (com aviso).
4. **Diagnóstico** por livro: `ok` (fecha 400 na mosca), `quase` (±1 a ±3 folhas — revisão rápida), `revisar` (diferença maior), `manual` (folha + anexos no mesmo PDF), `incompleto`, `vazio`.
5. **Executa** (`EscrituraImporterService`): separa as páginas (reaproveita o `PdfSplitterService`) e copia os anexos (`NamingService` evita sobrescrita). **Os originais nunca são tocados.**
6. Grava `reports/Importacao_livro<N>_<timestamp>.csv` (rastreabilidade folha a folha) e um `Importacao_resumo_<timestamp>.csv`.

Trabalha por **faixa de livros** (`1083-1100`), é **retomável** (livro concluído é pulado — `progress/escritura_importacao.json`) e tem **modo simulação** (mostra o plano completo sem gerar nada). Por padrão a saída fica **agrupada por diagnóstico** (`<destino>/ok/1103/…`, `<destino>/quase/1085/…`) para o escrevente saber de imediato o que revisar. Processa só os `ok` por padrão; pode incluir os `quase` e `revisar`. Os `manual`/`incompleto`/`vazio` ficam sempre de fora.

Configuração (`config.json`): `EscrituraOrigem`, `EscrituraDestino`, `EscrituraNomeTemplate` (padrão `{Livro}_folha_{Pagina}`), `EscrituraFolhaDigitos` (padrão 3 → `002`), `EscrituraFolhasPorLivro` (padrão 400), `EscrituraPaginasCache` (opcional), `EscrituraAgruparPorDiagnostico` (padrão `true`).

## Módulo de Conferência de folhas pelo código do rodapé

Roda **em cima da saída da importação** (`EscrituraDestino`) e corrige a numeração usando o **código impresso no rodapé de toda folha** (`SP0869` + livro + folha — ex.: `SP08691083140`, `SP0869001103150`). Os 3 últimos dígitos são a folha, os 4 antes são o livro.

Por página, tenta na ordem: (1) a **camada de texto** do PDF (livros antigos são PDFs pesquisáveis), (2) o **barcode Code 39** do rodapé (livros novos são só imagem — `pypdfium2` renderiza, `zxing-cpp` lê). Página **sem** esse código **não é folha do livro** — é anexo/documento escaneado junto.

Por livro (`CodigoFolhaService` + `ConferenciaService`):

- lê o código real de cada arquivo de folha e **remonta as pastas pelo número verdadeiro** (a `008` que na verdade é a folha 7 vira `007`);
- página sem código → vira **anexo da primeira folha do arquivo de origem** (usa o `Importacao_livro<N>.csv` da importação);
- página com código de **outro livro** → `_conflitos/`;
- **duplicata** (mesma folha 2×) → a 1ª fica, as outras vão para `NNN/duplicada/` (nada é apagado);
- **re-diagnostica** o livro; se agora fecha 400, move a pasta dele de `revisar/` para `ok/`.

Corrige **no lugar** (não duplica em disco — moves na mesma unidade são instantâneos). Os originais na rede **nunca são tocados**. Tem **modo simulação** (mostra o de-para, não move nada) e é **retomável por livro**. Gera `reports/Conferencia_livro<N>_<timestamp>.csv` (de-para) e um `Conferencia_resumo_<timestamp>.csv`.

Dependências (já no `requirements.txt`, ou o módulo se oferece para instalar): `pypdfium2`, `zxing-cpp`, `pillow`.

## Testes

```bash
python tests/generate_fixture_environment.py
python -m pytest
```

`generate_fixture_environment.py` cria, em `tests/fixtures/`, um ambiente fictício com PDFs de 1 página, múltiplas páginas, corrompido, protegido por senha, vazio e duplicados — usado tanto pelos testes automatizados quanto para um teste manual rápido:

```bash
python main.py --config tests/config.teste.json
```

## Estrutura do projeto

```
PDFSuite/
├── main.py                # composition root (monta e injeta as dependencias)
├── config.json
├── requirements.txt / requirements-dev.txt
├── modules/                # controllers finos (menu + 1 arquivo por funcionalidade)
├── models/                 # dataclasses/enums puros (PdfRecord, AppConfig, RenamePlanItem, ...)
├── services/                # regra de negocio (Scanner, Hasher, PdfInspector, Inventory,
│                            #   RenameTemplate, Naming, PdfSplitter, OCR-stub,
│                            #   EscrituraScanner/Planner/Importer, CodigoFolha, Conferencia)
├── repositories/            # persistencia (Inventory, Config, Progress, Rename, Split,
│                            #   EscrituraImport, Conferencia)
├── logs/ reports/ progress/ # saidas geradas em tempo de execucao
├── resources/                # reservado para recursos futuros (templates, icones de GUI)
├── docs/ARCHITECTURE.md      # arquitetura detalhada
└── tests/                    # pytest + gerador de ambiente ficticio
```
