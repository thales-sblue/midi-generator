# midi-generator

MVP em Python para gerar melodias MIDI determinísticas para produção musical.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Uso

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator --bpm 124 --root A --scale minor --bars 8 --seed 2026 --output output/example.mid
```

Os parâmetros são BPM, nota raiz, escala (`major` ou `minor`), número de compassos e seed. A mesma configuração produz exatamente os mesmos eventos MIDI.

O gerador usa uma grade de colcheias em 4/4, inclui pausas, varia velocity e limita todas as alturas à escala escolhida. O projeto não inclui interface gráfica, integração com Ableton ou IA generativa.

## Arquitetura

O motor de composição é independente de bibliotecas MIDI: ele transforma um `MelodyRequest` em um `CompositionPlan` formado por `NoteEvent`s. O `MidiExporter` é a única camada que usa Mido para converter esse plano em arquivo `.mid`.

O serializer de integração converte o mesmo plano no `Integration Payload v1`, um dicionário JSON-safe e determinístico para integrações externas. `schema_version = 1` identifica esse contrato; ele preserva a requisição, todas as notas, o relatório e os metadados da composição.

O contrato v1 torna `time_signature` e `ticks_per_beat` campos obrigatórios de primeiro nível. Consumidores externos precisam desses valores para interpretar corretamente as posições e durações, expressas em ticks. O serializer extrai os valores do próprio `CompositionPlan`, valida o payload e falha explicitamente se o plano não fornecer essas informações temporais.

```text
                         ┌─> MidiExporter -> .mid
MelodyRequest -> geração -> CompositionPlan
                         └─> Integration Payload v1
                                      ↑
                                      │
                                  MCP Server
                                      ↑
                                  MCP Client
```

O contrato está em `midi_generator.integration` e pode ser usado sem exportar MIDI:

```python
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.integration import composition_to_payload

request = MelodyRequest(120, "C", "minor", 4, 42)
payload = composition_to_payload(generate_plan(request))
assert payload["schema_version"] == 1
```

## Servidor MCP

O servidor MCP expõe a tool `generate_melody` pelo transporte local `stdio`. Ele é somente uma camada de comunicação: constrói um `MelodyRequest`, reutiliza `generate_plan()` e serializa o resultado com `composition_to_payload()`. A composição continua pertencendo ao motor e não há integração com Ableton nesta etapa.

Com o ambiente virtual ativado, inicie o servidor:

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator.mcp
```

Um cliente MCP pode chamar `generate_melody` com:

```json
{
  "bpm": 120,
  "root_note": "C",
  "scale": "minor",
  "bars": 4,
  "seed": 42
}
```

A resposta estruturada usa diretamente o Integration Payload v1:

```json
{
  "schema_version": 1,
  "bpm": 120,
  "root_note": "C",
  "scale": "minor",
  "bars": 4,
  "seed": 42,
  "time_signature": "4/4",
  "ticks_per_beat": 480,
  "total_duration_ticks": 7680,
  "notes": [
    {"pitch": 74, "start": 2160, "duration": 240, "velocity": 60, "channel": 0, "track": 0}
  ],
  "report": {"note_count": 6, "pause_count": 9, "duration_ticks": 7680, "scale": "minor", "seed": 42, "warnings": []},
  "metadata": {"ticks_per_beat": 480, "time_signature": "4/4"}
}
```

O array `notes` acima está resumido; a resposta real contém todos os eventos gerados.

Além dos testes rápidos em processo, a suíte inicia o entry point real em um processo Python separado e valida por `stdio` o handshake MCP, descoberta da tool, resposta estruturada, determinismo e erros de entrada. Esse teste usa apenas Python e o SDK declarado em `requirements.txt`, portanto também é executável no GitHub Actions com Ubuntu e Python 3.12.

## Testes

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

O mesmo comando é executado pelo GitHub Actions em pushes e pull requests.
