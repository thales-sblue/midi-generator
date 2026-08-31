# CLAUDE.md

Guia operacional do Claude Code para o `midi-generator`. A direção de produto,
as regras de admissão de dependências e o protocolo de trabalho continuam
canônicos em [`AGENTS.md`](AGENTS.md); este arquivo não os substitui, apenas
adiciona o que é específico do ambiente Claude Code nesta máquina.

**Antes de qualquer alteração de código, leia `AGENTS.md` inteiro.** Ele define
restrições de licenciamento, limites entre camadas, garantias de segurança e
determinismo, o "Protocolo para continue" e as fronteiras de validação manual no
Ableton Live. Nada abaixo tem precedência sobre `AGENTS.md`.

## Ambiente local (Windows)

- Repositório: `C:\GIT\midi-generator`. Clonado de
  `C:\Users\Thales\Documents\ChatGPT\midi-generator` em 30/08/2026, quando o
  trabalho migrou do Codex para o Claude Code.
- `origin` = `https://github.com/thales-sblue/midi-generator.git` (reapontado e
  com push validado em 30/08/2026). `git fetch origin` para conferir acesso.
- Python 3.12.13. Não há `python` no PATH; o `.venv` local foi criado a partir de
  `C:\Users\Thales\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.
- Use sempre o interpretador do `.venv`: `.venv\Scripts\python.exe`.
- Pendência: migrar o `.venv` para um Python 3.12 instalado normalmente antes que
  o cache `codex-runtimes` pare de ser mantido ou seja removido.

## Comandos

Instalação:

```powershell
python -m venv .venv          # ou o python base indicado acima
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Suíte de testes (204 testes; espelha o GitHub Actions):

```powershell
$env:PYTHONPATH = "src"
python -m pytest --basetemp=.pytest-tmp
```

`--basetemp=.pytest-tmp` é necessário nesta máquina: o diretório temporário
padrão do pytest (`%LOCALAPPDATA%\Temp\pytest-of-Thales`) está bloqueado por
outro processo e provoca `PermissionError` em ~5 testes que usam `tmp_path`. O
diretório `.pytest-tmp/` é ignorado pelo Git.

CLI do gerador heurístico:

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator --bpm 124 --root A --scale minor --bars 8 --seed 2026 --output output/example.mid
```

Servidor MCP (stdio):

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator.mcp
```

Integração Ableton (só com o Live 12 aberto e o Remote Script ativo):

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator.ableton install-script
python -m midi_generator.ableton doctor
```

## Mapa rápido das camadas

| Caminho | Papel |
| --- | --- |
| `src/midi_generator/domain/` | estruturas MIDI imutáveis, tabela de escalas (maior, menor, modos gregos, harmônica/melódica), requests, report — sem Mido/MCP/Live |
| `src/midi_generator/generation/` | backend heurístico (`melody.py`) e geração contextual (`contextual.py`) |
| `src/midi_generator/analysis/` | perfil objetivo de clip e ranking de compatibilidade (todas as escalas × 12 centros) |
| `src/midi_generator/transformations/` | transformações puras em ticks (transpose, invert, retrograde, quantize, legato, staccato, humanize, escala, diatônicas, velocity ramp) |
| `src/midi_generator/integration/` | conversão beats/ticks e `Integration Payload v1` (JSON-safe, `schema_version = 1`) |
| `src/midi_generator/exporters/` | `MidiExporter` — única camada que usa Mido |
| `src/midi_generator/mcp/` | tools tipadas e orquestração; sem algoritmo musical |
| `src/midi_generator/ableton/` | client TCP/JSON Lines para o Remote Script |
| `ableton_remote_script/MidiGeneratorBridge/` | Control Surface Python 3 que roda dentro do Live |
| `experiments/`, `docs/POC_SKYTNT*` | POC isolada do SkyTNT; **não integrada** ao runtime |

## Estado atual

Fonte única de status vivo: [`docs/STATE.md`](docs/STATE.md) — feito, validações
manuais no Live pendentes, gate de escuta do SkyTNT, decisões em aberto e fila de
incrementos. Comece cada ciclo por ele.

## Lembretes de fluxo (ver detalhe em `AGENTS.md`)

- Comece o ciclo lendo `docs/STATE.md` (contexto) e `AGENTS.md` (regras).
- Um único incremento coeso por ciclo; a menor capacidade útil, determinística,
  independente do Ableton e testável isoladamente.
- Reprodutibilidade em dois níveis: bit-exato (heurístico, contextual,
  transformações — aleatoriedade só de `random.Random(seed)`, nunca estado
  global); ambiente fixado (futuro backend de modelo registra device/dtype/libs).
- Operações sobre material existente são não destrutivas por padrão; proteja
  mutações concorrentes com fingerprint e recuse estado obsoleto (`CLIP_CHANGED`).
- MIDI gerado vai para `output/` e não é versionado.
- Não quebre o `Integration Payload v1` silenciosamente; evolua por versão.
- Rode a suíte completa antes e depois de alterar código; revise o próprio diff.
  `/code-review` antes do commit é auxílio recomendado; `security-review` antes de
  mexer na bridge ou no Remote Script.
- Não registre validação manual do Live sem evidência real. Ao parar numa
  fronteira de validação, deixe o status explicitamente pendente em `docs/STATE.md`
  com os payloads e conferências mínimas.
- Encerre cada ciclo com uma estimativa do avanço percentual contra o escopo do
  v1 (ver "Escopo da primeira versão utilizável" em `AGENTS.md`).
- Após suíte verde, revisão feita e commit criado, publique o HEAD validado
  direto em `origin/main` (fast-forward apenas), confirmando que o push terminou
  sem erro.
