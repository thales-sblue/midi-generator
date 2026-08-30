# STATE — status vivo do projeto

Fonte de contexto do Protocolo para "continue". Atualize a cada ciclo. Detalhe
de direção e regras fica em [`../AGENTS.md`](../AGENTS.md); ambiente local em
[`../CLAUDE.md`](../CLAUDE.md).

Última atualização: 30/08/2026 — Ciclo 1 (re-baseline pós-migração Codex → Claude).

## Escopo do v1

Motor determinístico: backend heurístico + geração contextual + bridge própria de
MIDI clips na Session View validada no Live. Backends de modelo generativo e
operações amplas no Live são pós-v1. Escopo Ableton do v1 = Session View MIDI
clips apenas.

## Feito

- Domínio: `NoteEvent`, `MelodyRequest`, `CompositionPlan`, `GenerationReport`;
  teoria maior/menor.
- Geração: backend heurístico determinístico; `generate_contextual_plan`
  (ritmo/pitch/movimento/duração/velocity herdados de um clip de referência).
- Análise: `analyze_clip` (perfil objetivo) + ranking de compatibilidade com 24
  escalas.
- Transformações puras (ticks, 480 tpb): transpose, invert, retrograde, quantize,
  legato, staccato, humanize, constrain_to_scale, transpose_diatonic,
  harmonize_diatonic, velocity_ramp.
- Integração: `Integration Payload v1` (`schema_version = 1`), conversão
  beats↔ticks.
- MCP: servidor stdio (`mcp==2.1.1`, `MCPServer`) com `generate_melody`, tools
  Ableton e orquestração segura; teste de subprocesso real.
- Bridge Ableton: Remote Script + socket JSON/TCP `127.0.0.1:20812`, fingerprint
  SHA-256, `CLIP_CHANGED`.
- Suíte: 204 testes verdes (`--basetemp=.pytest-tmp` nesta máquina).
- Validado manualmente no Live 12.4.5: geração, edição, duplicação protegida e
  transpose, invert, retrograde, quantize, humanize, legato, staccato.

## Pendente de validação manual no Live (gate humano, não é ciclo)

- `constrain_to_scale`
- `transpose_diatonic`
- `harmonize_diatonic`
- `velocity_ramp` (via `transform_ableton_midi_clip`)
- `create_contextual_variation_from_ableton_clip`

Domínio, preflight e orquestração MCP já cobertos por testes; falta conferir a
escrita no piano roll do Live. Registrar evidência real aqui ao validar.

## Gate de escuta do SkyTNT (gate humano, não é ciclo)

POC isolada executada (`POC_SKYTNT_RESULTS.md`); passou em CUDA/CPU/offline.
Bloqueado em escuta cega comparativa vs variações contextuais de duração
equivalente. Rodar de preferência pelo harness de avaliação (Ciclo 4). Até lá:
`investigar`, sem backend no runtime.

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

1. **Ciclo 2 — Escalas e modos.** Ampliar `SCALE_INTERVALS` (modos gregos, menor
   harmônica/melódica, escalas comuns); propagar por `generate_plan`,
   `generate_contextual_plan`, `constrain_to_scale`, `transpose_diatonic`,
   `harmonize_diatonic`, `rank_scale_candidates`. Testes por escala. Sem quebrar
   Payload v1.
2. **Ciclo 3 — Compassos 3/4 e 6/8.** Assinatura de tempo variável no domínio
   (`BEATS_PER_BAR` deixa de ser constante). Payload v1 já carrega
   `time_signature`. Bridge segue recusando ≠ 4/4 até validação manual.
3. **Ciclo 4 — Harness de avaliação/seleção (lacuna #2).** Módulo `evaluation/`:
   N candidatos (seeds derivadas) + pontuação objetiva + ranking. Também é o
   instrumento do gate de escuta.
4. **Ciclo 5 — Manifesto de proveniência v0 (lacuna #3).** Módulo `provenance/`:
   dict versionado (backend + versão, seed, params, hash do contexto e do output,
   timestamp) ao lado do Payload v1, nunca dentro.
