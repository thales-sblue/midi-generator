# STATE — status vivo do projeto

Fonte de contexto do Protocolo para "continue". Atualize a cada ciclo. Detalhe
de direção e regras fica em [`../AGENTS.md`](../AGENTS.md); ambiente local em
[`../CLAUDE.md`](../CLAUDE.md).

Última atualização: 02/09/2026 — Ciclo 11 (âncora de registro do gerador de
baixo: `octave` transpõe a linha inteira por oitavas inteiras).

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
- Análise: `analyze_clip` (perfil objetivo) + ranking de compatibilidade sobre
  todas as escalas × 12 centros (108 candidatos hoje) + `top_line_intervals`
  (contorno da voz superior) + `bass_line_pitches` (menor pitch soando por
  segmento de N batidas; nota sustentada conta em toda janela que cruza; `None`
  em janela muda) — insumo para geração ciente de papel pós-v1 (Ciclo 7).
- Transformações puras (ticks, 480 tpb): transpose, invert, retrograde, quantize,
  legato, staccato, humanize, constrain_to_scale, transpose_diatonic,
  harmonize_diatonic, velocity_ramp.
- Escalas: `major`, `minor` e mais os 7 modos gregos + `harmonic_minor` +
  `melodic_minor`, propagados por geração, contextual, análise e transformações
  diatônicas (Ciclo 2).
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
- Suíte: 352 testes verdes.
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
1. **Escalas não-heptatônicas** (pentatônicas, blues) — adiado do Ciclo 2 por
   mudarem a premissa "7 notas". Impacto avaliado no Ciclo 10: `transpose_diatonic`
   e `harmonize_diatonic` já indexam graus de `scale_pitches`, funcionam com
   qualquer cardinalidade; `nearest_scale_pitch` idem. O ponto sensível é
   `rank_scale_candidates`: uma escala de 5 notas tende a cobrir 100% de clips
   curtos e dominaria o ranking. Antes de admitir pentatônicas é preciso decidir
   a correção de cobertura (penalizar por tamanho, ranquear por cardinalidade,
   ou excluir não-heptatônicas do ranking).
2. **Acento métrico no heurístico** — 3/4 e 6/8 hoje só diferem no comprimento
   do compasso e no MetaMessage; modelar agrupamento de acentos (2×3 vs 3×2) é
   incremento próprio.
