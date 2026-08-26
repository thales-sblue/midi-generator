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

```text
                         ┌─> MidiExporter -> .mid
MelodyRequest -> geração -> CompositionPlan
                         └─> Integration Payload v1
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

## Testes

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

O mesmo comando é executado pelo GitHub Actions em pushes e pull requests.
