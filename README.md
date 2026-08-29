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

A camada `transformations/` reutiliza `NoteEvent` e acrescenta somente o contêiner imutável `EditableMidiClip`, necessário para carregar o comprimento do clip e validar suas bordas. `NoteEvent` inclui `mute=False`, preservando compatibilidade com a geração e permitindo representar fielmente as notas lidas do Live. As transformações operam em ticks inteiros, com 480 ticks por beat, sem Mido, Live API ou efeitos colaterais.

O domínio também oferece `velocity_ramp`, uma transformação expressiva pura
para crescendo e diminuendo. Ela interpola velocities inteiras entre o primeiro
e o último onset real do clip, aplica o mesmo valor às notas de um acorde e
preserva pitch, timing, duração, mute, canal, track, ordem e o clip original:

```python
from midi_generator.transformations import velocity_ramp

expressive_clip = velocity_ramp(clip, start_velocity=45, end_velocity=105)
```

O arredondamento é inteiro, explícito e simétrico nas duas direções. Clips
vazios permanecem vazios; quando todos os eventos compartilham um único onset,
usa-se `start_velocity` em todas as notas. A mesma operação está disponível no
fluxo não destrutivo do Ableton descrito abaixo.

A primeira capacidade de análise musical é `analyze_clip`. Ela produz um perfil
objetivo e determinístico do conteúdo audível: notas totais, ativas e mutadas,
onsets distintos, tessitura, velocity e duração médias, densidade por beat,
polifonia máxima, histograma das 12 classes de altura e movimento melódico.
O movimento usa a nota audível mais aguda de cada onset como voz superior e
mede quantos intervalos sobem, descem ou repetem, além do tamanho médio absoluto
e do maior salto. Com menos de dois onsets, os tamanhos permanecem desconhecidos
em vez de serem inventados como zero. Notas mutadas são contabilizadas, mas não
influenciam as métricas musicais. A análise é pura, imutável e reutiliza
`EditableMidiClip`, sem Live API, MCP ou Mido.

O perfil também classifica as 24 escalas maior/menor por cobertura das notas
audíveis e, em empate, pela quantidade de ocorrências da tônica. Cada candidato
informa `matching_note_count`, `tonic_note_count` e `coverage`. O resultado é
deliberadamente apresentado como compatibilidade: clips curtos e escalas
relativas podem ter evidência idêntica, portanto o motor não inventa uma
tonalidade única quando os dados não permitem distingui-la.

`generate_contextual_plan` cria uma nova melodia monofônica determinística a
partir de um `EditableMidiClip`. A tonalidade continua sendo uma decisão
explícita do chamador; do clip de referência vêm a densidade e a distribuição
de fase dos onsets, o registro, a duração média, a distribuição de classes de
altura e os valores reais de velocity. Acordes contam como um único ataque, por
isso a polifonia do source não infla a densidade de uma saída monofônica. Os
onsets são projetados na grade de colcheias pela posição dentro do compasso e
amostrados sem repetição. As proporções de movimentos ascendentes, descendentes
e repetidos da voz superior também orientam cada nova altura; quando a borda da
tessitura impede o movimento sorteado, a nota atual é repetida em vez de inverter
silenciosamente a direção. Classes de altura incompatíveis com a tonalidade
escolhida são ignoradas; se nenhuma for compatível, o gerador usa todas as
alturas permitidas no registro como fallback uniforme. Notas mutadas não
influenciam nenhum desses atributos. A saída evita sobreposição e limita a
densidade ao máximo possível na grade. Se a tonalidade escolhida não tiver
nenhuma nota dentro da tessitura do source, usa-se a altura permitida mais
próxima, com desempate para baixo.

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

Para clips existentes, a separação é:

```text
Ableton snapshot em beats
        ↓ integration/ (conversão determinística para 480 ticks/beat)
EditableMidiClip + NoteEvent
        ↓ transformations/ (algoritmos musicais puros)
notas transformadas
        ↓ mcp/ (orquestração segura)
AbletonClient → Remote Script (somente primitivas de baixo nível)
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

O servidor MCP expõe `generate_melody` e as tools opcionais do Ableton pelo transporte local `stdio`. Para geração, ele constrói um `MelodyRequest`, reutiliza `generate_plan()` e serializa o resultado com `composition_to_payload()`. Para transformação, ele apenas orquestra adapters e o motor puro; a lógica musical continua fora do servidor.

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

O Remote Script usa `ClipSlot.create_clip()` e objetos `Live.Clip.MidiNoteSpecification` com `Clip.add_new_notes()`. A integração cobre clips MIDI na Session View; não controla transporte e não cria tracks, instrumentos ou devices.

### Leitura, edição e transformação segura de clips MIDI

As tools `get_ableton_midi_clip`, `replace_ableton_midi_clip_notes` e `duplicate_ableton_midi_clip` completam o fluxo de ida e volta para clips MIDI existentes:

```text
READ
get_ableton_midi_clip
        ↓
clip + notes + fingerprint

EDIT
clip + notes modificadas + fingerprint
        ↓
replace_ableton_midi_clip_notes

SAFE VARIATION
original
   ↓
duplicate_ableton_midi_clip (somente para slot vazio)
   ↓
edit copy

DOMAIN TRANSFORMATION
READ source clip
   ↓
fingerprint A + validate + dry-run no domínio
   ↓
duplicate protegido com expected_source_fingerprint=A
   ↓
bridge relê e compara o source imediatamente antes da criação
   ↓
READ copy + DOMAIN TRANSFORMATION
   ↓
replace copy com o fingerprint da cópia
```

`get_ableton_midi_clip` retorna nome, comprimento em beats, estado de loop e as propriedades mínimas de cada nota (`pitch`, `start_time`, `duration`, `velocity` e `mute`). As notas são ordenadas por posição, pitch e duração.

`analyze_ableton_midi_clip` recebe `track_index` e `scene_index`, lê o mesmo
snapshot e retorna seu fingerprint junto ao perfil musical produzido no domínio.
A operação é somente leitura e não cria, duplica ou substitui clips. O
fingerprint permite relacionar a análise ao estado exato observado no Live.

`generate_contextual_melody_from_ableton_clip` recebe o source, BPM, tonalidade,
número de compassos e seed. Ela lê o clip, chama o gerador contextual puro e
retorna o `Integration Payload v1` junto ao fingerprint analisado. A operação é
somente leitura: não cria nem substitui clips no Live. O chamador escolhe
explicitamente `root_note` e `scale`, podendo usar os candidatos retornados pela
análise sem transformar uma compatibilidade ambígua em decisão automática.

O `clip_fingerprint` é um SHA-256 de JSON canônico formado pelo comprimento do clip e pelas notas ordenadas, com floats normalizados a nove casas decimais. Toda substituição exige o fingerprint obtido na leitura. Se o conteúdo tiver mudado no Live desde então, o bridge recusa a operação com `CLIP_CHANGED`; o cliente deve ler novamente antes de editar. Requests inválidos são validados integralmente antes da remoção das notas existentes, e notas além do comprimento atual falham com `NOTE_OUTSIDE_CLIP`. O comprimento nunca é alterado implicitamente.

Exemplo de leitura:

```json
{"track_index": 0, "scene_index": 0}
```

Exemplo de substituição baseada na leitura:

```json
{
  "track_index": 0,
  "scene_index": 0,
  "expected_fingerprint": "<fingerprint retornado pela leitura>",
  "notes": [
    {"pitch": 72, "start_time": 0.0, "duration": 0.5, "velocity": 90, "mute": false}
  ]
}
```

Exemplo de duplicação não destrutiva:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1
}
```

Para vincular a duplicação ao estado previamente lido do source, inclua o
fingerprint retornado por `get_ableton_midi_clip`:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "expected_source_fingerprint": "<fingerprint do source>"
}
```

Esse campo permanece opcional na primitiva de baixo nível por compatibilidade.
Quando informado, o bridge obtém o snapshot atual e compara o fingerprint dentro
do mesmo comando, antes de `create_clip()`. Se o source mudou, retorna
`CLIP_CHANGED` e deixa o target vazio. A tool de alto nível
`transform_ableton_midi_clip` sempre usa essa proteção.

### Transformações determinísticas v1

`transform_ableton_midi_clip` executa o fluxo completo de leitura, validação, duplicação, nova leitura da cópia, transformação e substituição com controle de concorrência. O slot de destino deve estar vazio e ser diferente do source. O clip original nunca é enviado para `replace_midi_clip_notes`.

Transpose em uma oitava:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "transpose",
  "semitones": 12
}
```

`transpose` preserva timing, duração, velocity e mute. Se qualquer pitch resultante ficar fora de `0..127`, toda a operação falha no dry-run, antes da duplicação.

Inversão melódica em torno do Dó central:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "invert",
  "axis_pitch": 60
}
```

`invert` reflete cada pitch em torno de `axis_pitch`: uma nota a três semitons
acima do eixo passa a três semitons abaixo, e vice-versa. Timing, duração,
velocity e mute são preservados. O eixo deve ser uma nota MIDI inteira em
`0..127`; se qualquer resultado sair desse intervalo, o dry-run recusa toda a
operação antes da duplicação. Com o mesmo eixo, duas aplicações recuperam
exatamente o clip original.

Retrograde temporal:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "retrograde"
}
```

`retrograde` espelha cada nota entre as bordas do clip: o novo início é o
comprimento do clip menos o fim original da nota. Assim, as durações são
preservadas e as pausas são invertidas no tempo, enquanto pitch, velocity, mute,
canal e track permanecem inalterados. A transformação não recebe parâmetros e
aplicá-la duas vezes recupera exatamente o clip original.

Quantize para semicolcheias:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "quantize",
  "grid": "1/16"
}
```

`quantize` aceita `1/4`, `1/8` e `1/16` em 4/4. O início é arredondado para a grade mais próxima em ticks inteiros; empates avançam para a próxima linha da grade. A duração original é preservada, exceto quando o novo início faria a nota ultrapassar o fim do clip: nesse caso ela é truncada até a borda. Se a grade arredondasse o início para o próprio fim do clip, usa-se a última linha válida anterior. Nenhuma nota começa antes de zero ou termina depois do clip.

Articulação legato:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "legato"
}
```

`legato` ajusta o fim de cada nota ao próximo início distinto. Notas de um
acorde que começam juntas recebem a mesma duração; pausas entre onsets são
fechadas, sobreposições são encurtadas e as notas do último onset alcançam o fim
do clip. Pitch, velocity, mute, canal e track são preservados. A transformação
não recebe parâmetros e reaplicá-la não altera novamente o resultado.

Articulação staccato com duração máxima de uma semicolcheia:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "staccato",
  "max_duration": 0.25
}
```

`staccato` limita a duração de cada nota a `max_duration`, expresso em beats,
sem alongar notas que já sejam mais curtas. Onset, pitch, velocity, mute, canal
e track são preservados. A duração é convertida deterministicamente para ticks,
deve resultar em pelo menos um tick e reaplicar o mesmo limite não altera
novamente o resultado.

Conformar uma melodia à tonalidade, preservando ritmo, velocity, mute, canal e
track:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "constrain_to_scale",
  "root_note": "C",
  "scale": "major"
}
```

`constrain_to_scale` mantém notas já pertencentes à escala e move cada nota
externa para a altura permitida mais próxima entre `0..127`. Empates escolhem a
altura inferior, evitando deriva melódica para cima. Aceita as mesmas raízes e
escalas `major` e `minor` usadas pelo gerador e é idempotente: reaplicar a mesma
tonalidade não muda novamente o clip.

Status da integração Live para `constrain_to_scale`: **PENDENTE DE VALIDAÇÃO
MANUAL**. A lógica de domínio, o preflight e a orquestração MCP são cobertos
automaticamente; a escrita no piano roll do Live deve ser conferida antes de
registrar validação manual.

Transposição diatônica por graus da tonalidade:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "transpose_diatonic",
  "steps": 2,
  "root_note": "C",
  "scale": "major"
}
```

`transpose_diatonic` move cada nota por `steps` graus da escala; por exemplo,
em Dó maior, `steps = 2` move Dó para Mi. Notas externas à tonalidade são antes
alinhadas à altura permitida mais próxima, com desempate para baixo. Se qualquer
resultado exceder `0..127`, a operação inteira falha antes de duplicar o clip.
Status da integração Live: **PENDENTE DE VALIDAÇÃO MANUAL**.

Harmonia diatônica paralela, preservando a voz original:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "harmonize_diatonic",
  "steps": 2,
  "root_note": "C",
  "scale": "major"
}
```

`harmonize_diatonic` mantém todas as notas do source e acrescenta, na cópia,
uma voz paralela deslocada por `steps` graus da escala; em Dó maior,
`steps = 2` acrescenta Mi acima de Dó. Timing, duração, velocity, mute, canal e
track são preservados. O source precisa estar integralmente na tonalidade para
evitar alterar implicitamente a melodia antes da harmonização. Passos iguais a
zero e resultados fora de `0..127` falham no preflight, antes da duplicação.
Notas harmônicas que já existam com todas as mesmas propriedades não são
duplicadas. Status da integração Live: **PENDENTE DE VALIDAÇÃO MANUAL**.

Rampa expressiva de velocity:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "velocity_ramp",
  "start_velocity": 40,
  "end_velocity": 100
}
```

`velocity_ramp` cria um crescendo ou diminuendo linear entre o primeiro e o
último onset real. Notas do mesmo acorde recebem a mesma velocity; pitch,
timing, duração, mute, canal e track são preservados. Os extremos devem ser
inteiros entre `1..127` e são validados antes da duplicação. Status da integração
Live: **PENDENTE DE VALIDAÇÃO MANUAL**.

Humanize determinístico:

```json
{
  "source_track_index": 0,
  "source_scene_index": 0,
  "target_track_index": 0,
  "target_scene_index": 1,
  "transform": "humanize",
  "seed": 42,
  "max_timing_shift": 0.05,
  "max_velocity_delta": 5
}
```

Na API MCP, `max_timing_shift` é expresso em beats e convertido deterministicamente para o tick mais próximo. `humanize` exige `seed` e usa exclusivamente `random.Random(seed)`. O deslocamento de timing e a variação de velocity são sorteados dentro dos limites informados; pitch, duração e mute são preservados, velocity é limitada a `1..127`, e o timing é limitado às bordas do clip.

Todos os parâmetros e o snapshot source são validados, e a transformação completa é simulada, antes de criar a cópia. O target vazio ainda é garantido atomicamente pela primitiva `duplicate_midi_clip` no bridge. Existe um limite de atomicidade inevitável entre comandos: se a duplicação funcionar e uma falha externa ocorrer depois (por exemplo, o usuário alterar a cópia e causar `CLIP_CHANGED`, o Live fechar ou a conexão cair), a cópia não transformada pode permanecer no target. Não há rollback ou deleção implícita; o source continua intacto e a ocorrência deve ser resolvida explicitamente pelo usuário no Live.

### Validação manual de `transform_ableton_midi_clip` no Live 12

O roteiro e as evidências desta seção cobrem `transpose`, `invert`, `retrograde`,
`quantize`, `humanize`, `legato` e `staccato`, incluindo conferência dos
conteúdos pela ponte e no piano roll do Live.

Status desta etapa: **VALIDADO MANUALMENTE EM LIVE 12.4.5** em 27 de agosto de
2026. O procedimento abaixo permanece como roteiro reproduzível.

1. Ative o ambiente, reinstale o Remote Script atualizado e confirme a conexão:

   ```powershell
   . .\.venv\Scripts\Activate.ps1
   $env:PYTHONPATH = "src"
   python -m midi_generator.ableton install-script
   ```

   Feche e reabra o Live, selecione `MidiGeneratorBridge` em **Preferences >
   Link, Tempo & MIDI > Control Surface** e execute:

   ```powershell
   python -m midi_generator.ableton doctor
   python -m midi_generator.mcp
   ```

2. Na Session View, crie um source MIDI conhecido no track `0`, scene `0`, e
   deixe vazios os targets usados abaixo. Execute a tool MCP
   `transform_ableton_midi_clip` com este payload para transpose:

   ```json
   {
     "source_track_index": 0,
     "source_scene_index": 0,
     "target_track_index": 0,
     "target_scene_index": 1,
     "transform": "transpose",
     "semitones": 12
   }
   ```

   Confirme no piano roll: source intacto; target criado; pitches exatamente
   `+12`; timings, velocities e durações idênticos aos do source.

3. Com o mesmo source e o target `0/2` vazio, execute quantize:

   ```json
   {
     "source_track_index": 0,
     "source_scene_index": 0,
     "target_track_index": 0,
     "target_scene_index": 2,
     "transform": "quantize",
     "grid": "1/16"
   }
   ```

   Confirme visualmente que os inícios estão alinhados à grade de semicolcheias
   e que o source permanece intacto.

4. Prepare duas cópias idênticas do mesmo source em slots distintos, ou use o
   mesmo source ainda intacto com dois targets vazios. Execute humanize para o
   primeiro target:

   ```json
   {
     "source_track_index": 0,
     "source_scene_index": 0,
     "target_track_index": 0,
     "target_scene_index": 3,
     "transform": "humanize",
     "seed": 42,
     "max_timing_shift": 0.05,
     "max_velocity_delta": 5
   }
   ```

   Repita com exatamente os mesmos parâmetros, alterando apenas
   `target_scene_index` para outro slot vazio. Confirme pequenas mudanças de
   timing/velocity, source intacto, nenhuma nota fora do clip e conteúdo de notas
   idêntico nos dois targets produzidos com seed `42`.

Validação executada no Windows com o Remote Script reinstalado e o Live
reiniciado. Os sources `0/0` e `1/0` foram preservados. `transpose` em `0/6`
alterou os pitches de `75, 74, 63, 65, 74` para `87, 86, 75, 77, 86` e manteve
timings, durações, velocities e mute. `quantize` em `0/7` moveu o primeiro início
de `0.129999948` para `0.25` beat e alinhou todos os inícios à grade `1/16`.
`humanize` em `1/7`, com seed `42`, reproduziu exatamente as notas e o fingerprint
`aacd6b198d61c8f561463d4e1699fd6f8927217ac70a4f6109533be9fc56ef64` de outra
execução com a mesma seed. Todos os targets permaneceram dentro dos limites dos
clips e foram conferidos no piano roll.

Na mesma instalação do Live 12.4.5, `invert` e `retrograde` também foram
**VALIDADOS MANUALMENTE** em 27 de agosto de 2026. Duas cenas vazias foram
adicionadas sem remover clips existentes. Com o source `0/0` de oito beats e
fingerprint
`409d2d298e626b75bd6086f89b9d173660dea13c01ce415e01308cd880b4ab73`,
`invert` em `0/1`, usando `axis_pitch = 69`, alterou os pitches
`75, 74, 63, 65, 74` para `63, 64, 75, 73, 64` e produziu o fingerprint
`79c0d8dfe228fb0e7f703e7e0a9f5a54e681eaf3e65e25f612d624ac95fced23`.
Timing, duração, velocity e mute permaneceram idênticos ao source.

`retrograde` em `0/2` produziu, em ordem temporal, as notas
`74@0.0+2.0`, `65@2.0+0.5`, `63@3.5+1.5`, `74@6.0+0.5` e
`75@6.5+1.5`, exatamente o espelho temporal esperado dentro do clip, com
fingerprint
`53579797580d3ffa57060ac513feb1f2a3e66c64593baeadd7c5780ff1478ea0`.
As respostas estruturadas da tool MCP, as leituras posteriores da ponte e a
comparação no piano roll coincidiram. Uma leitura final confirmou que o source
continuou com as cinco notas e o fingerprint original.

`legato` também foi **VALIDADO MANUALMENTE** na mesma instalação. A tool MCP
transformou o source `1/0`, de oito beats, no target vazio `1/1`. As durações
`1.5, 0.5, 1.5, 0.5, 2.0` passaram a
`1.370833333, 1.5, 2.5, 0.5, 2.0` após a conversão determinística para ticks:
as sobreposições foram encurtadas, as pausas foram fechadas no próximo onset e
a nota final permaneceu até o fim do clip. Pitch, velocity e mute foram
preservados. O source manteve o fingerprint
`b7d38d63cf815b1e0df2f299f8d118edaa9d14648dd77be6d7aa1ce64af871a2`,
enquanto o target produziu
`fe127ee43f2549900082e81aa68c7bb17833726f3db5e2e51301cfe11730b6bb`.
A resposta estruturada da tool MCP, a leitura posterior da ponte e a conferência
visual no piano roll coincidiram; o projeto de validação foi salvo no Live.

`staccato` também foi **VALIDADO MANUALMENTE** na mesma instalação. A tool MCP
transformou o source `1/0` no target vazio `1/2`, usando
`max_duration = 0.25`. As durações `1.5, 0.5, 1.5, 0.5, 2.0` passaram todas a
`0.25` beat. Pitch, velocity e mute foram preservados; os onsets permaneceram
nos mesmos ticks, com o primeiro serializado de `0.129999948` para
`0.129166667` após a conversão determinística para 480 ticks por beat. O source
manteve o fingerprint
`b7d38d63cf815b1e0df2f299f8d118edaa9d14648dd77be6d7aa1ce64af871a2`, e o
target produziu
`347313c618b593dcf28cf281bf275f813fa5edbc9879dc84079e53869295f1c3`. A
resposta estruturada da tool MCP, as leituras posteriores da ponte e o piano
roll da cena 3 da pista `2-MIDI` coincidiram; o set foi salvo no Live.

A proteção da duplicação também foi validada na instância atualizada do bridge:
um `expected_source_fingerprint` inválido retornou `CLIP_CHANGED`, e uma leitura
imediata confirmou que o target continuava vazio.

As tools de baixo nível continuam apenas encaminhando primitivas ao `AbletonClient`. A nova tool de alto nível orquestra o fluxo, mas os algoritmos musicais ficam exclusivamente em `transformations/`. Não existe interpretação de linguagem natural, aleatoriedade global ou lógica musical no Ableton bridge.

**VALIDADO AUTOMATICAMENTE:** a suíte cobre leitura e ordenação das notas, estabilidade e mudança do fingerprint, substituição com controle de concorrência, validação anterior à mutação, limite do clip, duplicação para slot vazio, protocolo/client e delegação das tools MCP de baixo nível.

A suíte também cobre transpose positivo e negativo, inversão melódica por eixo, reflexão temporal e involução exata de invert e retrograde, articulações legato por grupos de onset e staccato por duração máxima, transposição e harmonia diatônicas, preservação da voz original na cópia harmonizada, rampas expressivas de velocity, as três grades de quantize, regras de borda e duração, determinismo e limites do humanize, imutabilidade dos inputs, preflight antes da duplicação, uso do fingerprint da cópia, propagação de `CLIP_CHANGED`, descoberta e chamada MCP estruturada da tool de transformação.

As transformações desta versão operam somente sobre MIDI clips da Session View. Não criam tracks, instrumentos ou devices e não controlam transporte, Arrangement View, automações, mixagem ou áudio.

Validação manual concluída em 26 de agosto de 2026 com Ableton Live 12 Lite 12.4.5 no Windows. O `doctor` confirmou a conexão e a compatibilidade do protocolo; `get_ableton_session` retornou duas pistas MIDI e oito cenas; e `generate_and_insert_melody` criou e exibiu corretamente um clip na primeira cena da pista `1-MIDI`, usando 120 BPM, Dó menor, quatro compassos e seed 42. O resultado teve 16 beats e seis notas. Status: **VALIDADO MANUALMENTE EM LIVE 12.4.5**.

Em 27 de agosto de 2026, o fluxo de edição também foi **VALIDADO MANUALMENTE EM LIVE 12.4.5**: o bridge leu as cinco notas de um clip de oito beats, duplicou o original para um slot vazio, elevou somente a última nota da cópia de pitch 74 para 86 e preservou o fingerprint do original. A leitura posterior confirmou o novo conteúdo e uma repetição da escrita com o fingerprint anterior foi recusada com `CLIP_CHANGED`. A comparação no editor MIDI do Live confirmou visualmente o original intacto e a última nota uma oitava acima somente na cópia.
