# STATE — status vivo do projeto

Fonte de contexto do Protocolo para "continue". Atualize a cada ciclo. Detalhe
de direção e regras fica em [`../AGENTS.md`](../AGENTS.md); ambiente local em
[`../CLAUDE.md`](../CLAUDE.md).

Última atualização: 02/09/2026 — Ciclo 16 (kick exposto ao MCP/Ableton pelo
fluxo não destrutivo compartilhado: `create_kick_from_ableton_clip`).

## Escopo do v1

Motor determinístico: backend heurístico + geração contextual + bridge própria de
MIDI clips na Session View validada no Live. Backends de modelo generativo e
operações amplas no Live são pós-v1. Escopo Ableton do v1 = Session View MIDI
clips apenas.

## Feito

- Domínio: `NoteEvent`, `MelodyRequest`, `CompositionPlan`, `GenerationReport`;
  tabela de escalas; helpers puros `scale_pitch_classes` / `scale_pitches` /
  `nearest_scale_pitch` (empate para baixo) em `domain/music_theory.py`,
  consumidos por `transformations/operations.py` (Ciclo 8).
- Geração: backend heurístico determinístico; `generate_contextual_plan`
  (ritmo/pitch/movimento/duração/velocity herdados de um clip de referência);
  `generate_bass_line_plan` (`generation/bass_line.py`, Ciclo 9) — converte a
  linha de fundamentais de `bass_line_pitches` numa linha de baixo monofônica:
  uma nota por janela métrica soante, altura fixada na escala escolhida pelo
  chamador (`nearest_scale_pitch`, empate para baixo), janelas mudas viram
  pausa, `velocity` fixa (default 96). Sem RNG — determinístico por construção;
  `seed` só viaja para report/metadados. O plano cobre exatamente o clip de
  referência, então `request.bars`/`time_signature` têm de descrever esse mesmo
  comprimento. É a primeira geração ciente de papel, fundada no Ciclo 7.
  `sustain` (Ciclo 10): com `False` (default) cada janela soante vira uma nota
  (pulso na grade); com `True`, janelas consecutivas que fixam na *mesma* altura
  da escala viram uma nota presa (uma janela muda sempre corta a nota), então o
  ritmo harmônico da saída segue a referência e não o tamanho da janela.
  `metadata["note_grouping"]` = `per_window` | `sustained`.
  `octave` (Ciclo 11): `None` (default) mantém o registro do source; um inteiro
  −1..9 transpõe a linha inteira por um único deslocamento de oitavas para
  ancorar a nota mais grave nessa oitava MIDI (contorno/intervalos preservados),
  e recusa o deslocamento que levaria alguma nota acima de 127.
  `metadata["target_octave"]` / `metadata["octave_offset_semitones"]`.
  `generate_chord_bed_plan` (`generation/chords.py`, Ciclo 12) — segundo papel
  sobre a mesma fundação: cada janela soante vira um acorde em posição fechada,
  com a fundamental fixada na escala como voz mais grave e `chord_size` (2..5,
  default 3) graus tomados de dois em dois na escala acima dela. A qualidade
  vem do grau (maior no I, menor no ii), não de uma tabela de acordes.
  `sustain`, `octave`, `segment_beats` e `velocity` (default 80) têm o mesmo
  significado do gerador de baixo; `sustain` amarra janelas cujo acorde inteiro
  se repete e `octave` ancora a voz mais grave do leito, recusando o
  deslocamento em que algum acorde precisaria de nota acima de 127.
  `metadata["voicing"] = "stacked_scale_degrees"`, `chord_size`, `chord_count`.
  A leitura da fundação, o encaixe na escala e a âncora de registro vivem em
  `generation/foundation.py` (`build_foundation_line` → `FoundationLine`),
  compartilhado pelos dois geradores; nenhum deles duplica mais essa etapa.
  `generate_kick_plan` (`generation/drums.py`, Ciclo 15) — primeira percussão
  ciente de papel: um kick (`KICK_PITCH = 36`, bumbo do GM) em cada início
  distinto de nota audível do clip de referência. Acorde = um onset, nota muda
  não conta. Duração `KICK_DURATION_TICKS` (240) encurtada até o próximo onset
  ou a borda do clip. Voz sem altura → **não** passa pela `foundation.py` e
  ignora `root_note`/`scale` (carregados só para proveniência). Sem RNG;
  `velocity` fixa (default 100); `seed` só no report/metadados. O plano cobre
  exatamente o clip de referência (`request.bars`/`time_signature` iguais).
  `metadata["generation_mode"] = "kick"`, `onset_count`, `kick_pitch`. Flui pelo
  Payload v1 / exporter / evaluation / provenance como qualquer `CompositionPlan`.
  Ainda não ligado à CLI/MCP — fluxo Ableton é incremento próprio, atrás do gate
  do Live.
- Análise: `analyze_clip` (perfil objetivo) + ranking de compatibilidade sobre
  todas as escalas × 12 centros (144 candidatos hoje) + `top_line_intervals`
  (contorno da voz superior) + `bass_line_pitches` (menor pitch soando por
  segmento de N batidas; nota sustentada conta em toda janela que cruza; `None`
  em janela muda) — insumo para geração ciente de papel pós-v1 (Ciclo 7).
- Transformações puras (ticks, 480 tpb): transpose, invert, retrograde, quantize,
  legato, staccato, humanize, constrain_to_scale, transpose_diatonic,
  harmonize_diatonic, velocity_ramp.
- Escalas: `major`, `minor` e mais os 7 modos gregos + `harmonic_minor` +
  `melodic_minor` (Ciclo 2), e as não heptatônicas `major_pentatonic`,
  `minor_pentatonic` e `blues` (Ciclo 13) — propagadas por geração, contextual,
  análise, transformações diatônicas, geradores de papel e CLI. Nenhuma camada
  assume cardinalidade 7: "grau" é sempre grau da escala nomeada, então um grau
  de pentatônica não é o grau heptatônico de mesmo número. A ordem da tabela é
  carregada de significado — heptatônicas primeiro, não heptatônicas por último,
  porque `rank_scale_candidates` desempata por ordem de inserção.
- Compassos: `TimeSignature` (`numerator/denominator`, denominador em
  1/2/4/8/16) no domínio; `MelodyRequest.time_signature` (default `4/4`)
  propagado por `generate_plan`, `generate_contextual_plan`, metadados do
  Payload v1, `MidiExporter` (MetaMessage `time_signature`) e a CLI
  (`--time-signature`). O gerador heurístico exige compasso alinhado à grade de
  colcheias. A bridge Ableton continua recusando ≠ 4/4 (`UNSUPPORTED_TIME_SIGNATURE`)
  (Ciclo 3).
- Avaliação/seleção: módulo `evaluation/` — `derive_seeds` (seeds derivadas
  bit-exatas só de `random.Random(base)`), `score_profile`/`score_plan` (quatro
  proxies objetivos em `0..1`: entropia de movimento, cobertura de classes de
  altura, atividade rítmica, controle de saltos; agregado v0 = média simples),
  `rank_candidates`/`evaluate_request` (ranking por agregado, desempate por seed)
  e CLI `--candidates N` (um `.mid` ranqueado por candidato). Backend-agnóstico:
  aceita um callable `MelodyRequest -> CompositionPlan` (ex.: closure sobre
  `generate_contextual_plan`). Reusa `analyze_clip`; sem dependência nova
  (Ciclo 4).
- Proveniência: módulo `provenance/` — `build_manifest` gera o manifesto v0
  (`provenance_schema_version = 1`): backend + versão, seed, parâmetros, hash
  SHA-256 do contexto (só contextual) e da saída, timestamp ISO 8601 injetado
  pelo chamador. Schema próprio, ao lado do Payload v1 e nunca dentro dele;
  `validate_manifest` checa a estrutura. CLI `--provenance` grava
  `<saída>.provenance.json`. `docs/PROVENANCE.md`. (Ciclo 5).
- Verificação de gate: `midi_generator/mcp/verification.py` —
  `verify_transform_roundtrip` / `verify_contextual_roundtrip` rodam a
  orquestração real, releem source e target e conferem estruturalmente
  (nota a nota, via `clip_notes_to_ableton`) que o target contém o que o
  motor determinístico pretendia escrever e que o source ficou intacto.
  Reusa a orquestração de `ableton_transform` e as mesmas funções de
  domínio; não adiciona algoritmo musical. CLI
  `python -m midi_generator.mcp.verification --source T S --target T S`
  (roda as 5 operações do gate; `--json` para relatório colável; sai ≠ 0 e
  imprime "bridge unavailable" sem Live). `tests/test_ableton_verification.py`
  (8 testes) exercita o harness contra o `BridgeDispatcher` real sobre um
  contexto Live em memória. (Ciclo 6).
- MCP ciente de papel (Ciclo 14): `create_bass_line_from_ableton_clip` e
  `create_chord_bed_from_ableton_clip` levam `generate_bass_line_plan` /
  `generate_chord_bed_plan` ao fluxo não destrutivo já usado pela variação
  contextual. `mcp/ableton_transform.py` ganhou o helper compartilhado
  `_generate_into_protected_copy` (lê o source uma vez, checa 4/4 inteiro, gera
  o plano no preflight, duplica com `expected_source_fingerprint`, relê a cópia,
  confere o comprimento e substitui só a cópia); `create_contextual_midi_clip_copy`
  passou a usá-lo sem mudança de comportamento. As tools encaminham
  `segment_beats`/`velocity`/`sustain`/`octave` (e `chord_size` no leito) direto
  ao gerador — nenhuma validação ou algoritmo musical no MCP — e a resposta ecoa
  os parâmetros e os metadados do plano (`bars`, `note_grouping`,
  `octave_offset_semitones`, `chord_count`, `voicing`). `root_note`/`scale`
  continuam explícitos. Payload v1 intacto; determinismo bit-exato preservado.
- MCP kick (Ciclo 16): `create_kick_from_ableton_clip` leva `generate_kick_plan`
  ao mesmo `_generate_into_protected_copy` — `create_kick_midi_clip_copy` em
  `mcp/ableton_transform.py` só lê o source, monta a requisição (comprimento =
  clip, 4/4 inteiro), chama o gerador do core e escreve só na cópia protegida
  por fingerprint. Encaminha `velocity` (default 100) direto ao gerador; nenhum
  algoritmo/validação musical no MCP. `root_note`/`scale` seguem no request só
  para proveniência — a tonalidade não é inferida. A resposta (`KickClipResult`)
  ecoa `bars`/`velocity` e os metadados do plano (`onset_count`, `kick_pitch`,
  `reference_length_ticks`) sem recalcular. Payload v1 intacto; determinismo
  bit-exato preservado. Criação e conteúdo no Live **pendentes de validação
  manual**.
- Suíte: 437 testes verdes.
- Integração: `Integration Payload v1` (`schema_version = 1`), conversão
  beats↔ticks.
- MCP: servidor stdio (`mcp==2.1.1`, `MCPServer`) com `generate_melody`, tools
  Ableton e orquestração segura; teste de subprocesso real.
- Bridge Ableton: Remote Script + socket JSON/TCP `127.0.0.1:20812`, fingerprint
  SHA-256, `CLIP_CHANGED`.
- Suíte roda com `--basetemp=.pytest-tmp` nesta máquina.
- Validado manualmente no Live 12.4.5: geração, edição, duplicação protegida e
  transpose, invert, retrograde, quantize, humanize, legato, staccato.

## Pendente de validação manual no Live (gate humano, não é ciclo)

- `constrain_to_scale`
- `transpose_diatonic`
- `harmonize_diatonic`
- `velocity_ramp` (via `transform_ableton_midi_clip`)
- `create_contextual_variation_from_ableton_clip`
- `create_bass_line_from_ableton_clip` (Ciclo 14)
- `create_chord_bed_from_ableton_clip` (Ciclo 14)
- `create_kick_from_ableton_clip` (Ciclo 16)

Domínio, preflight e orquestração MCP já cobertos por testes; falta conferir a
escrita no piano roll do Live contra o Ableton real. Ableton indisponível nesta
máquina em 31/08/2026 (`python -m midi_generator.ableton doctor` →
`unavailable`, `127.0.0.1:20812` recusou a conexão; Live 12 não estava aberto /
Remote Script inativo). Nenhuma das 5 foi executada contra o Live neste ciclo —
seguem **não validadas no Live**.

Cobertura automatizada conferida neste ciclo (não duplicar):

| Operação | Domínio bit-exato | Orquestração (preflight/fingerprint/CLIP_CHANGED/não-destrutivo) | MCP tool | Bridge dispatcher (fake Live) |
| --- | --- | --- | --- | --- |
| `constrain_to_scale` | `test_transformations.py`, `test_scales.py` | `test_ableton_transform.py` | `test_ableton_mcp.py` | `test_ableton_bridge_core.py` |
| `transpose_diatonic` | idem | idem | idem | idem |
| `harmonize_diatonic` | idem | idem (+ rejeita pitch fora da escala antes do duplicate) | idem | idem |
| `velocity_ramp` | idem | idem | idem | idem |
| `create_contextual_variation_from_ableton_clip` | `test_contextual_generation.py` | `test_ableton_transform.py` (preflight, determinismo, 4/4, cópia protegida) | `test_ableton_mcp.py` | idem |
| `create_bass_line_from_ableton_clip` | `test_bass_line_generation.py` | `test_ableton_role_generation.py` (preflight, determinismo, 4/4, source intacto, encaminhamento de `segment_beats`/`velocity`/`sustain`/`octave`, `CLIP_CHANGED`) | `test_ableton_mcp.py` | idem |
| `create_chord_bed_from_ableton_clip` | `test_chord_bed_generation.py` | `test_ableton_role_generation.py` (idem + `chord_size`) | `test_ableton_mcp.py` | idem |
| `create_kick_from_ableton_clip` | `test_kick_generation.py` | `test_ableton_role_generation.py` (preflight, determinismo, 4/4, source intacto, encaminhamento de `velocity`, tonalidade ignorada, `CLIP_CHANGED`, erro do replace) | `test_ableton_mcp.py` (registro, default de `velocity`, delegação, `ToolError`) | idem |

Procedimento mínimo para fechar o gate (com Live 12 aberto + Control Surface
`MidiGeneratorBridge` ativo):

1. `python -m midi_generator.ableton doctor` → deve dizer `connected`.
2. Numa track MIDI da Session View, criar um clip de origem de 4/4 com todas as
   notas dentro de C maior (pré-condição de `harmonize_diatonic`); anotar
   track/scene (ex.: `0 0`) e deixar 5 slots vazios logo abaixo.
3. `$env:PYTHONPATH = "src"; python -m midi_generator.mcp.verification --source 0 0 --target 0 1 --json`
   (roda as 5 operações em `0 1`..`0 5`).
4. Colar o JSON aqui. Gate fechado só se **todas** as operações reportarem
   `"passed": true` (checks `orchestration_succeeded`, `source_preserved`,
   `target_matches_expected`, `reported_fingerprint_matches_readback`).
5. Conferir a olho no piano roll do Live que o clip de origem em `0 0` continua
   idêntico e que cada cópia tem o conteúdo esperado.
6. Se algo falhar: abrir issue com o `first_note_diff` do relatório antes de
   marcar qualquer operação como validada.

Procedimento mínimo para o gate das tools cientes de papel do Ciclo 14
(`create_bass_line_from_ableton_clip` / `create_chord_bed_from_ableton_clip`) —
o harness `mcp.verification` ainda **não** as cobre, então a conferência é manual:

1. `python -m midi_generator.ableton doctor` → `connected`.
2. Numa track MIDI da Session View, criar um clip de referência de N compassos
   4/4 com uma linha de fundamentais audível (baixo ou acordes); anotar
   track/scene (ex.: `0 0`) e deixar `0 1` e `0 2` vazios.
3. Chamar `create_bass_line_from_ableton_clip` com `source 0 0`, `target 0 1`,
   `bpm`/`root_note`/`scale`/`seed` explícitos (ex.: `120 / C / minor / 42`),
   `octave` opcional.
4. Chamar `create_chord_bed_from_ableton_clip` com `source 0 0`, `target 0 2`,
   os mesmos `bpm`/tonalidade/`seed` e `chord_size` (ex.: 3).
5. Conferir no piano roll: `0 0` idêntico ao original; `0 1` com uma nota de
   baixo por janela soante fixada na escala; `0 2` com um acorde em posição
   fechada por janela soante. Repetir a chamada com a mesma seed e conferir que
   o conteúdo é bit a bit igual (comparar `target_clip_fingerprint`).
6. Repetir a chamada apontando `target` para um slot ocupado e confirmar a recusa
   (`TARGET_CLIP_SLOT_NOT_EMPTY`), com o source intacto.

Procedimento mínimo para o gate de `create_kick_from_ableton_clip` (Ciclo 16) —
mesmo fluxo `_generate_into_protected_copy`, também não coberto pelo harness
`mcp.verification`:

1. `python -m midi_generator.ableton doctor` → `connected`.
2. Numa track MIDI da Session View, criar um clip de referência de N compassos
   4/4 com um ritmo audível (qualquer voz); anotar track/scene (ex.: `0 0`) e
   deixar `0 3` vazio.
3. Chamar `create_kick_from_ableton_clip` com `source 0 0`, `target 0 3`,
   `bpm`/`root_note`/`scale`/`seed` explícitos (ex.: `120 / C / minor / 42`),
   `velocity` opcional (default 100). `root_note`/`scale` viajam só para
   proveniência.
4. Conferir no piano roll: `0 0` idêntico ao original; `0 3` com um kick
   (`pitch 36`) em cada início distinto de nota audível do source, duração
   encurtada até o próximo onset ou a borda do clip. Conferir que
   `onset_count` na resposta bate com o número de onsets distintos do source.
5. Repetir a chamada com a mesma seed e `velocity` e conferir que o conteúdo é
   bit a bit igual (comparar `target_clip_fingerprint`). Repetir mudando só
   `root_note`/`scale` e conferir que o conteúdo não muda.
6. Repetir a chamada apontando `target` para um slot ocupado e confirmar a recusa
   (`TARGET_CLIP_SLOT_NOT_EMPTY`), com o source intacto.

## Gate de escuta do SkyTNT (gate humano, não é ciclo)

POC isolada executada (`POC_SKYTNT_RESULTS.md`); passou em CUDA/CPU/offline.
Bloqueado em escuta cega comparativa vs variações contextuais de duração
equivalente. O harness de avaliação (`evaluation/`, Ciclo 4) já existe e é o
instrumento para gerar e ranquear os candidatos da escuta; a escuta cega em si
continua sendo gate humano. Até lá: `investigar`, sem backend no runtime.

## Decisões em aberto

- Design híbrido pós-v1 (modelo gera ideia / heurístico + transformações +
  assistente controlam) — confirmar no gate de escuta.
- Ableton amplo: "envolver integração externa na nossa camada de segurança" vs
  "estender a bridge própria" — nenhuma opção externa pesquisada tem garantias
  não-destrutivas/fingerprint/concorrência. Decidir só quando o v1 fechar.
- Migração do `.venv` para um Python 3.12 fora do cache `codex-runtimes`.
- Pins de dependências de runtime (`requirements.txt` usa faixas).
- Lacunas de CI (mypy/lint/Windows/cobertura; Remote Script e bridge TCP sem
  cobertura).

## Fila de incrementos (revisável)

- [x] **Ciclo 2 — Escalas e modos.** `SCALE_INTERVALS` com 9 escalas; propagado
  por `generate_plan`, `generate_contextual_plan`, `constrain_to_scale`,
  `transpose_diatonic`, `harmonize_diatonic`, `rank_scale_candidates` e a CLI.
  `tests/test_scales.py` (15 testes). Payload v1 intacto.
- [x] **Ciclo 3 — Compassos variáveis.** `TimeSignature` no domínio;
  `MelodyRequest.time_signature` (default `4/4`) propagado por `generate_plan`,
  `generate_contextual_plan`, metadados do Payload v1, `MidiExporter` e a CLI
  (`--time-signature`). Grade de colcheias exigida pelo heurístico; bridge
  Ableton segue recusando ≠ 4/4. `tests/test_time_signature.py` (40 testes).
  Payload v1 intacto (string).
- [x] **Ciclo 4 — Harness de avaliação/seleção (lacuna #2).** Módulo
  `evaluation/`: `derive_seeds`, `score_profile`/`score_plan` (quatro proxies
  objetivos + agregado v0), `rank_candidates`/`evaluate_request`, CLI
  `--candidates N`. Backend-agnóstico, reusa `analyze_clip`, sem dependência
  nova. `tests/test_evaluation.py` (17 testes). Payload v1 intacto.
- [x] **Ciclo 5 — Manifesto de proveniência v0 (lacuna #3).** Módulo
  `provenance/`: `ProvenanceManifest` + `build_manifest` + `validate_manifest`
  (backend + versão, seed, params, `context_hash`/`output_hash` SHA-256,
  `generated_at` injetado). Schema próprio versionado, ao lado do Payload v1 e
  nunca dentro. CLI `--provenance`. `tests/test_provenance.py` (18 testes).
  `docs/PROVENANCE.md`. Payload v1 intacto.
- [x] **Ciclo 6 — Harness de verificação read-back do gate do Live.** Módulo
  `mcp/verification.py`: `verify_transform_roundtrip` / `verify_contextual_roundtrip`
  + `VerificationReport`/`VerificationCheck` + CLI
  `python -m midi_generator.mcp.verification`. Roda a orquestração real, relê
  source e target e compara nota a nota contra o resultado do domínio; confirma
  source intacto e fingerprint reportado == fingerprint relido. Reusa
  `ableton_transform` e as transformações de domínio; sem algoritmo musical
  novo; Payload v1 intacto. `tests/test_ableton_verification.py` (8 testes)
  contra o `BridgeDispatcher` real. Instrumento para fechar o gate humano das 5
  operações pendentes quando o Live estiver acessível.
- [x] **Ciclo 7 — Linha de fundamentais do clip (fundação da geração de papel).**
  `analysis/clip_profile.py`: `bass_line_pitches(clip, *, segment_beats=1)` —
  menor pitch soando por janela métrica, `None` em janela muda, nota sustentada
  contando em toda janela que cruza. Função pura, sem RNG, não toca `ClipProfile`
  nem o Payload v1. Export em `analysis/__init__.py`.
  `tests/test_clip_analysis.py` (+11 casos: polifonia, sustentação, silêncio,
  `segment_beats`, cauda parcial, `mute`, sem notas, validação). É o insumo do
  próximo incremento (gerador de baixo diatônico seguindo essa linha).
- [x] **Ciclo 8 — API de escala compartilhada no domínio.**
  `domain/music_theory.py` ganha `scale_pitch_classes`, `scale_pitches` e
  `nearest_scale_pitch` (empate para baixo, movido verbatim de
  `transformations/operations.py`). `constrain_to_scale`, `transpose_diatonic` e
  `harmonize_diatonic` passam a usar essa API; privados `_scale_definition` /
  `_nearest_scale_pitch` e as comprehensions `range(128)` inline removidos.
  Comportamento idêntico (`test_scales.py` / `test_transformations.py` verdes sem
  alteração). `tests/test_music_theory.py` (12 casos). `generation/` e
  `analysis/scale_compatibility.py` mantêm suas mensagens próprias — migração é
  incremento próprio. Payload v1 intacto; determinismo bit-exato preservado.
- [x] **Ciclo 9 — Gerador de baixo diatônico (primeira geração ciente de papel).**
  `generation/bass_line.py`: `generate_bass_line_plan(request, reference, *,
  segment_beats=1, velocity=96)`. Reusa `analysis.bass_line_pitches` (Ciclo 7) e
  `domain.nearest_scale_pitch` / `domain.scale_pitch_classes` (Ciclo 8); sem
  dependência nova, sem RNG (bit-exato por construção), sem algoritmo musical no
  MCP/bridge. Uma nota por janela soante, altura fixada na escala do chamador
  (empate para baixo), janela muda → pausa, nota sustentada alimenta toda janela
  que cruza, cauda parcial encurtada à borda. O plano flui pelo Payload v1,
  exporter, evaluation e provenance como qualquer `CompositionPlan`.
  `tests/test_bass_line_generation.py` (12 casos: contorno, determinismo/seed,
  snap de altura externa, empate para baixo, sustentação, `segment_beats`, cauda
  parcial, velocity, comprimento incompatível, tudo mudo, `segment_beats`
  inválido, serialização v1). Payload v1 intacto. Não integrado ao CLI/MCP —
  wiring e um fluxo Ableton não destrutivo são incremento próprio (fronteira de
  validação no Live).
- [x] **Ciclo 10 — Modo `sustain` do gerador de baixo.**
  `generate_bass_line_plan(..., sustain=False)`. Quando `True`, janelas
  consecutivas cuja fundamental fixa na mesma altura da escala são amarradas
  numa única nota presa; janela muda corta a nota. `metadata["note_grouping"]`
  passa a `per_window` | `sustained`; `report.note_count` conta as notas
  emitidas (pós-merge), `pause_count` continua contando janelas mudas.
  Determinístico, sem RNG, isolado — nenhuma outra camada muda.
  `tests/test_bass_line_generation.py` +5 casos (default é pulso, merge de
  alturas iguais, merge de fundamentais distintas que fixam na mesma altura,
  janela muda não é atravessada, `sustain` não-booleano). Payload v1 intacto.
- [x] **Ciclo 11 — Âncora de registro do gerador de baixo.**
  `generate_bass_line_plan(..., octave=None)`. Com um inteiro −1..9, calcula um
  único deslocamento de oitavas (ceil-division) que ancora a nota mais grave da
  linha fixada na escala dentro dessa oitava MIDI e aplica esse mesmo
  deslocamento a todas as notas — contorno e intervalos preservados; recusa
  (`ValueError`) o deslocamento que levaria alguma nota acima de 127. `None`
  mantém o registro do source (comportamento dos Ciclos 9-10). Determinístico,
  sem RNG, isolado — nenhuma outra camada muda. `metadata["target_octave"]` e
  `metadata["octave_offset_semitones"]` novos. `tests/test_bass_line_generation.py`
  +6 casos (default `None`, ancoragem para baixo em 3/4, elevação de source
  grave, recusa acima de 127, tipo/faixa de `octave`, combinação com `sustain`).
  Payload v1 intacto.
- [x] **Ciclo 12 — Leito de acordes diatônicos (segundo papel).**
  `generation/chords.py`: `generate_chord_bed_plan(request, reference, *,
  segment_beats=1, velocity=80, sustain=False, octave=None, chord_size=3)`.
  Empilha `chord_size` graus da escala de dois em dois acima da fundamental
  fixada de cada janela — a qualidade do acorde sai do grau, sem tabela de
  acordes, e vale para qualquer escala da tabela. Refatoração casada:
  `generation/foundation.py` (`build_foundation_line` → `FoundationLine` com
  `pitches`/`segment_ticks`/`total_ticks`/`octave_offset`, `window_bounds`,
  `sounding_count`) concentra validação, leitura de `bass_line_pitches`, encaixe
  na escala e âncora de oitava; `bass_line.py` passou a consumi-la e perdeu ~80
  linhas, com os 23 testes do Ciclo 9-11 verdes sem alteração (bit-exatidão
  preservada). Sem RNG, sem dependência nova, sem algoritmo musical no MCP.
  `tests/test_chord_bed_generation.py` (17 casos: tríade por janela, escala/grau,
  sétima, faixa de `chord_size`, sustain amarra todas as vozes, janela muda não
  é atravessada, âncora de oitava, teto de 127 por acorde e por leito,
  `segment_beats`, velocity, comprimento incompatível, tudo mudo, payload v1).
  Payload v1 intacto. Como o baixo, ainda não está ligado à CLI/MCP.
- [x] **Ciclo 13 — Escalas não heptatônicas.** `SCALE_INTERVALS` ganha
  `major_pentatonic` (0,2,4,7,9), `minor_pentatonic` (0,3,5,7,10) e `blues`
  (0,3,5,6,7,10), **anexadas ao fim** da tabela. O bloqueio registrado no Ciclo
  10 partia de uma premissa errada: `rank_scale_candidates` ordena por
  `matching_note_count` **absoluto**, não por `coverage`. Verificado
  experimentalmente antes de implementar — uma escala contida em outra maior
  nunca casa mais notas que ela, e o empate cai na ordem de inserção, então a
  leitura heptatônica continua vencendo (num clip C-E-G, `C major` vem antes de
  `C major_pentatonic`). Uma escala menor só lidera quando cobre o que nenhuma
  heptatônica cobre (riff com Solb **e** Sol → `C blues` primeiro, cobertura
  1.0), que é o comportamento desejado. Nenhuma correção de cobertura foi
  necessária; o ranking ficou intacto. `transpose_diatonic`,
  `harmonize_diatonic`, `constrain_to_scale`, `nearest_scale_pitch`, heurístico,
  contextual, baixo, leito de acordes e a CLI já eram agnósticos de
  cardinalidade e passaram a aceitar as três escalas sem mudança de código.
  Ajustes de honestidade que as novas escalas forçaram: o metadado do leito de
  acordes passou de `stacked_scale_thirds` para `stacked_scale_degrees` (em
  pentatônica os graus empilhados não são terças — Dó pentatônica dá C-E-A), e
  o teste que exigia 7 intervalos de *toda* escala virou dois (invariantes da
  tabela inteira × cardinalidade só das heptatônicas). Os dois testes que
  fixavam 108 candidatos passaram a derivar de `len(SCALE_INTERVALS)`; o perfil
  do `analyze_clip` (e a tool MCP) agora devolve 144 candidatos — crescimento
  aditivo, sem mudança de schema. `tests/test_non_heptatonic_scales.py`
  (13 casos). Payload v1 intacto; determinismo bit-exato preservado.
  Consequência conhecida e aceita: o proxy `pitch_class_diversity` de
  `evaluation/scoring.py` normaliza por 7, então material pentatônico satura em
  5/7. Como `rank_candidates` compara candidatos da *mesma* requisição (mesma
  escala), o teto é uniforme e não distorce o ranking; corrigir a normalização
  exigiria dar a escala ao scoring, que hoje só vê o `ClipProfile`.
- [x] **Ciclo 14 — Fluxo MCP não destrutivo para baixo e leito de acordes.**
  `mcp/server.py`: `create_bass_line_from_ableton_clip` e
  `create_chord_bed_from_ableton_clip` — localizam e leem o clip de referência,
  montam a requisição (comprimento = clip, 4/4 inteiro), chamam
  `generate_bass_line_plan` / `generate_chord_bed_plan` e escrevem só numa cópia
  protegida por fingerprint. `mcp/ableton_transform.py` extraiu o pipeline
  compartilhado `_generate_into_protected_copy` (lê o source uma vez → checa 4/4
  → gera o plano no preflight → duplica com `expected_source_fingerprint` → relê
  a cópia → confere comprimento → substitui só a cópia);
  `create_contextual_midi_clip_copy` foi religado a ele sem mudança de
  comportamento (23 testes de `test_ableton_transform.py` verdes sem alteração).
  As tools encaminham `segment_beats`/`velocity`/`sustain`/`octave` (e
  `chord_size` no leito) direto ao gerador — nenhuma validação nem algoritmo
  musical no MCP; erros do core/bridge viram `ToolError`. A resposta ecoa os
  parâmetros e metadados do plano. `root_note`/`scale` seguem explícitos.
  `tests/test_ableton_role_generation.py` (24 casos) +
  `tests/test_ableton_mcp.py` (+3). Payload v1 intacto; determinismo bit-exato
  preservado. Fronteira: criação e conteúdo no Live **pendentes de validação
  manual** (ver seção do gate acima).
- [x] **Ciclo 15 — Primeira percussão ciente de papel (kick).**
  `generation/drums.py`: `generate_kick_plan(request, reference, *,
  velocity=100)` — um kick (`KICK_PITCH = 36`) por início distinto de nota
  audível do clip de referência; acorde = um onset, nota muda não conta.
  Duração `KICK_DURATION_TICKS = 240` encurtada até o próximo onset ou a borda
  do clip. Sem `foundation.py`, sem RNG, sem tonalidade (voz sem altura;
  `root_note`/`scale` só para proveniência). Plano cobre exatamente o clip
  (`request.bars`/`time_signature` iguais). Rejeita comprimento incompatível,
  referência toda muda e `velocity` fora de 1..127. `metadata` = `kick`,
  `onset_count`, `kick_pitch`, `reference_length_ticks`. Flui pelo Payload v1
  como qualquer `CompositionPlan`. `tests/test_kick_generation.py` (12 casos:
  um kick por onset, pitch 36, acorde → um kick, clamp de duração, mudas
  ignoradas, determinismo, seed só no report, serialização v1, comprimento
  incompatível, referência muda, faixa de velocity). Payload v1 intacto;
  determinismo bit-exato preservado. Não ligado à CLI/MCP — fluxo Ableton é
  incremento próprio, atrás do gate do Live.
- [x] **Ciclo 16 — Kick exposto ao MCP/Ableton pelo fluxo não destrutivo
  compartilhado.** `mcp/ableton_transform.py`: `create_kick_midi_clip_copy` e o
  TypedDict `KickClipResult`; `mcp/server.py`: tool `create_kick_from_ableton_clip`
  (params `source_*`/`target_*`/`bpm`/`root_note`/`scale`/`seed`,
  `velocity` default `DEFAULT_KICK_VELOCITY` = 100). O algoritmo musical continua
  em `generation/drums.py::generate_kick_plan` — o MCP só orquestra: reusa
  `_generate_into_protected_copy` (lê o source uma vez → 4/4 inteiro → gera o
  plano no preflight → duplica com `expected_source_fingerprint` → relê a cópia →
  confere comprimento → substitui só a cópia). Source nunca vai a
  `replace_midi_clip_notes`; a cópia é protegida por fingerprint; `CLIP_CHANGED`
  propaga. `velocity` é encaminhada direto ao gerador; `root_note`/`scale` seguem
  no request só para proveniência (tonalidade não é inferida). A resposta ecoa
  `bars`/`velocity` e os metadados do plano (`onset_count`, `kick_pitch`,
  `reference_length_ticks`) sem recalcular. `tests/test_ableton_role_generation.py`
  (+12 casos de orquestração) e `tests/test_ableton_mcp.py` (+3: registro/expo,
  default de `velocity` e delegação, `ValueError`→`ToolError`). Payload v1
  intacto; determinismo bit-exato preservado. Suíte 437 verdes. Fronteira:
  criação e conteúdo no Live **pendentes de validação manual** (roteiro no gate
  acima). Nenhuma dependência nova; sem CLI de kick; sem snare/clap/hi-hat.
2. **Acento métrico no heurístico** — 3/4 e 6/8 hoje só diferem no comprimento
   do compasso e no MetaMessage; modelar agrupamento de acentos (2×3 vs 3×2) é
   incremento próprio.
3. **Percussão ciente de papel — próximos passos.** (a) [feito no Ciclo 16]
   Fluxo MCP não destrutivo para o kick, espelhando
   `create_bass_line_from_ableton_clip` (atrás do gate do Live). (b) Snare/clap
   na contramão métrica (backbeat) e hi-hat numa subdivisão da grade,
   condicionados ao compasso e à densidade de onsets. (c) Modos de colocação do
   kick (downbeat-only, four-on-the-floor) como parâmetro, já que a base por
   onset está pronta.
