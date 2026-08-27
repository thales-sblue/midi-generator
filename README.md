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

O gerador usa uma grade de colcheias em 4/4, inclui pausas, varia velocity e limita todas as alturas à escala escolhida. O projeto não inclui interface gráfica nem IA generativa.

O projeto inclui uma ponte opcional para Ableton Live 12 Lite. O motor, a exportação MIDI e `generate_melody` continuam funcionando normalmente sem Ableton; somente as operações descritas na seção "Ableton Live" exigem que o Live esteja aberto e com o Remote Script ativo.

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

## Ableton Live

A integração usa um MIDI Remote Script/Control Surface em Python 3 e não requer Max for Live, Suite, plugins, OSC ou automação de interface.

```text
Codex / MCP Client
        ↓
    MCP stdio
        ↓
  midi-generator
        ↓
Integration Payload v1
        ↓
   AbletonClient
        ↓  TCP + JSON Lines em 127.0.0.1:20812
MidiGeneratorBridge Remote Script
        ↓  fila drenada na thread principal
    Ableton Live
        ↓
Session View MIDI Clip
```

O protocolo usa uma conexão TCP por comando. Requests e responses são objetos JSON delimitados por newline e correlacionados por `request_id`:

```json
{"request_id":"abc","command":"ping","params":{}}
{"request_id":"abc","ok":true,"result":{"application":"Ableton Live","bridge":"MidiGeneratorBridge"}}
```

O bind é restrito a `127.0.0.1`. A porta padrão é `20812`. Para usar outra porta, crie `config.json` ao lado do Remote Script com base em `config.json.example` e configure o cliente externo com a mesma porta:

```powershell
$env:MIDI_GENERATOR_ABLETON_PORT = "20813"
```

### Instalação do Remote Script no Windows

Com o ambiente virtual ativado e na raiz do projeto:

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator.ableton install-script
```

O helper somente copia `ableton_remote_script/MidiGeneratorBridge` para:

```text
%USERPROFILE%\Documents\Ableton\User Library\Remote Scripts\MidiGeneratorBridge
```

Ele não modifica a instalação interna do Live nem remove outros scripts. Depois da cópia:

1. feche e reabra o Ableton Live;
2. abra `Preferences → Link, Tempo & MIDI`;
3. em `Control Surface`, selecione `MidiGeneratorBridge`;
4. deixe as portas MIDI de entrada e saída como `None`, pois a ponte usa somente TCP local.

### Diagnóstico

Com Live aberto e o Control Surface ativo:

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator.ableton doctor
```

O doctor verifica o endpoint, conecta ao bridge, executa `ping` e mostra a versão que o próprio Live reportar. Live fechado, script não instalado ou Control Surface inativo são apresentados como bridge indisponível, sem traceback.

### Tools MCP

`get_ableton_session` não recebe argumentos. Ela retorna apenas tracks, com `index`, `name` e `can_hold_midi`, e scenes, com `index` e `name`.

`generate_and_insert_melody` recebe:

```json
{
  "bpm": 120,
  "root_note": "C",
  "scale": "minor",
  "bars": 4,
  "seed": 42,
  "track_index": 0,
  "scene_index": 0
}
```

O fluxo reutiliza `generate_plan()`, `composition_to_payload()` e `validate_payload_v1()`. O Remote Script recusa tracks que não aceitam MIDI, índices inexistentes, schema diferente de `1`, assinatura diferente de `4/4` e slots ocupados. Não há opção de overwrite.

As posições e durações são convertidas com o `ticks_per_beat` do payload:

```text
start_time = start / ticks_per_beat
duration = duration_ticks / ticks_per_beat
clip_length = total_duration_ticks / ticks_per_beat
```

O Remote Script usa `ClipSlot.create_clip()` e objetos `Live.Clip.MidiNoteSpecification` com `Clip.add_new_notes()`. A implementação cobre somente clips MIDI novos na Session View. Não edita clips existentes, não controla transporte e não cria tracks, instrumentos ou devices.

Validação manual concluída em 26 de agosto de 2026 com Ableton Live 12 Lite 12.4.5 no Windows. O `doctor` confirmou a conexão e a compatibilidade do protocolo; `get_ableton_session` retornou duas pistas MIDI e oito cenas; e `generate_and_insert_melody` criou e exibiu corretamente um clip na primeira cena da pista `1-MIDI`, usando 120 BPM, Dó menor, quatro compassos e seed 42. O resultado teve 16 beats e seis notas. Status: **VALIDADO MANUALMENTE EM LIVE 12.4.5**.
