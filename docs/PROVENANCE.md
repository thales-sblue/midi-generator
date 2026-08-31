# Manifesto de proveniência v0

Registro versionado que acompanha o `Integration Payload v1` **sem nunca ser
embutido nele**. Vive em schema próprio (`provenance_schema_version`) para
evoluir independentemente do contrato de integração. Módulo:
`midi_generator.provenance`.

## Campos

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `provenance_schema_version` | int | Versão deste schema. Hoje `1`. |
| `backend` | str | `heuristic` ou `contextual`. |
| `backend_version` | str | Versão do algoritmo do backend (`BACKEND_VERSIONS`). |
| `seed` | int | Seed efetiva do plano. |
| `parameters` | obj | `bpm`, `root_note`, `scale`, `bars`, `time_signature`. |
| `context_hash` | str \| null | SHA-256 do clip de referência (só contextual); `null` no heurístico. |
| `output_hash` | str | SHA-256 das notas geradas + `total_duration_ticks`. |
| `generated_at` | str | Timestamp ISO 8601 fornecido pela camada de I/O. |

`context_hash` e `output_hash` usam JSON canônico
(`sort_keys`, `separators=(",",":")`) sobre a representação inteira em ticks das
notas (`pitch, start, duration, velocity, channel, track, mute`), então são
bit-exatos e independentes de plataforma.

## Determinismo

O motor não inventa relógio: `generated_at` é injetado por quem executa a
geração (a CLI usa `datetime.now(timezone.utc)`). Tudo o mais no manifesto é
função determinística do plano e do contexto.

## Regra de versão do backend

Suba a versão em `BACKEND_VERSIONS` sempre que uma mudança altere as notas
produzidas para um par `(seed, parameters)` já suportado. Parâmetros aditivos
que mantêm as seeds existentes bit-idênticas não exigem bump.

## Uso

```python
from midi_generator.domain import MelodyRequest
from midi_generator.generation import generate_plan
from midi_generator.provenance import build_manifest

plan = generate_plan(MelodyRequest(120, "C", "minor", 4, 2026))
manifest = build_manifest(plan, generated_at="2026-08-31T12:00:00+00:00")
manifest.to_dict()  # dict JSON-safe, ao lado do payload, nunca dentro
```

Pela CLI, `--provenance` grava `<saída>.provenance.json` ao lado de cada `.mid`
(inclusive um por candidato quando combinado com `--candidates`).
