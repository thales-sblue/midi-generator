# Análise de áudio — o "ouvido" do motor

Estado: MVP implementado em 23/09/2026. Validado com gravações sintéticas de
violão (testes automatizados). **Validação com gravação real e escuta no
Ableton: pendente** (ver "Validação" no fim).

## Onde a camada se encaixa

```
gravação (wav/flac/ogg/mp3)
   │  audio/            ← única camada que importa librosa/numpy
   ▼
MusicAnalysis           ← domain/music_analysis.py, dados puros, sem numpy
   │  generation/accompaniment.py
   ▼
MelodyRequest + clip de referência harmônica (EditableMidiClip)
   │  geradores já existentes: bass_line.py, drums.py
   ▼
CompositionPlan (baixo, bateria)
   │  exporters/ (mapa de tempo da gravação)
   ▼
.mid alinhado ao áudio  ──►  Ableton (hoje: arquivo; bridge: incremento futuro)
```

Decisões:

- **Nenhum gerador novo de baixo ou bateria.** Os geradores de papel já recebem
  um `EditableMidiClip` de referência. A análise vira exatamente isso: um clip
  cuja nota em cada trecho é a fundamental do acorde detectado (registro E1–D#2),
  posicionada na grade de beats. `generate_bass_line_plan` segue esse clip e
  encaixa as fundamentais na tonalidade detectada; `generate_kick_plan`,
  `generate_snare_plan` e o novo `generate_hihat_plan` usam o comprimento/compasso.
- **`MusicAnalysis` é independente da origem.** Hoje só o áudio o produz; um
  `MIDI → MusicAnalysis` (a partir de `analyze_clip` + `bass_line_pitches`) pode
  alimentar o mesmo `generation/accompaniment.py` sem mudar os geradores.
- **Schema próprio versionado** (`schema: "music_analysis"`, `schema_version: 1`),
  ao lado do Integration Payload v1 e nunca dentro dele. O Payload v1 não mudou.
- **Determinismo:** a geração a partir de uma `MusicAnalysis` é bit-exata (sem
  RNG). A análise de áudio em si é nível "ambiente fixado": depende das versões
  de librosa/numpy/scipy, como qualquer DSP em ponto flutuante.

## Modelo `MusicAnalysis`

| Campo | Conteúdo |
| --- | --- |
| `grid: BeatGrid` | tempo de cada beat (segundos), índice do primeiro downbeat, beats por compasso |
| `detected_beats` | beats como o rastreador os entregou (antes de preencher lacunas/estender) |
| `tempo_confidence`, `meter_confidence` | 0..1 |
| `key: KeyEstimate` | tônica, modo (`major`/`minor`, nomes da tabela de escalas), confiança, alternativa |
| `chords: ChordSegment[]` | início/fim em segundos, fundamental, qualidade, confiança; `N` = sem acorde |
| `measures: Measure[]` | por compasso: acorde principal, acordes presentes, energia relativa |

Conversões (em `BeatGrid`): `seconds_to_beat`, `beat_to_seconds` (interpolação
beat a beat — acompanha variação de andamento, não depende de um BPM global),
`beat_to_bar`, `bar_bounds_seconds`. Beat `0.0` é o primeiro downbeat; beats
negativos são anacruse.

## Pipeline e escolhas técnicas

| Etapa | Implementação | Por quê |
| --- | --- | --- |
| Carga | `librosa.load`, mono, 22 050 Hz | lê wav/flac/ogg/mp3 localmente |
| Beats | `librosa.beat.beat_track` (Ellis 2007, programação dinâmica) | consolidado, dá a **posição** de cada beat |
| Ajuste fino | onsets com hop de 5,8 ms, backtrack ao início do ataque; ataques < 50 ms agrupados (um rasgueado = um evento); latência mediana beat→ataque removida; beats sem ataque interpolados entre vizinhos; beats iniciais cortados pelo rastreador recuperados se houver ataque | o rastreador chega ~30–60 ms atrasado e quantizado em 23 ms — bateria soaria "atrás" |
| Grade | lacunas > 1,5 período preenchidas; extensão até o fim do áudio; cauda silenciosa descartada | compassos completos até o fim |
| Tempo | média do vão total da grade | a mediana de intervalos quantizados enviesava (117,5 em vez de 120) |
| Compasso e downbeat | para cada hipótese (4 ou 3 tempos × fase): contraste de mudança harmônica + acento nos candidatos a tempo 1 | acordes costumam mudar e rasgueados costumam acentuar no tempo 1; sem modelo treinado |
| Acordes | chroma CQT da parte harmônica (HPSS) → mediana por beat → similaridade com 24 templates de tríade + estado "sem acorde" → bônus pequeno à fundamental dominante no registro grave (E2–D#3) → Viterbi com viés de permanência | baseline clássico de MIR, transparente e sem pesos; o bônus do baixo desempata casos como Fmaj7 (que contém Am inteiro) |
| Tonalidade | correlação Krumhansl–Kessler com o perfil de chroma; entre a melhor e a relativa, decide o acorde de tônica (abre, fecha, mais tempo) | tonalidades relativas têm as mesmas notas; o perfil sozinho não decide |

**Por que templates e não modelo treinado:** as opções treinadas avaliadas têm
pesos NonCommercial (madmom), licença AGPL e sem wheel no Windows (Essentia),
dependem de TensorFlow e de binários só para Linux (autochord, crema) ou
resolvem outro problema (basic-pitch transcreve notas). Para violão/guitarra
com progressões simples, template + Viterbi + bônus de baixo acertou 100 % dos
acordes nos testes sintéticos, inclusive com variação humana de tempo, ruído e
acordes com sétima. Registro completo em `DEPENDENCY_POLICY.md`.

## Confianças (ordinais, não probabilidades)

- **tempo:** regularidade dos intervalos detectados (1 − 4 × coeficiente de variação).
  Mede estabilidade, **não** garante a oitava correta do tempo.
- **compasso:** margem da hipótese vencedora sobre a melhor concorrente.
- **tonalidade:** (energia de chroma dentro da escala, reescalada de "ruído
  cromático" = 0 a "totalmente diatônico" = 1) × (clareza da escolha entre a
  tonalidade e sua relativa, 0,5–1). A `alternative` mostra a relativa.
- **acorde:** softmax da similaridade no beat, média no segmento.

## Alinhamento com a gravação

O plano MIDI começa no primeiro downbeat (tick 0 = compasso 1). O exporter
recebe um `MidiTempoMap`:

- **lead-in** de compassos inteiros esticado até o primeiro downbeat (as barras
  do MIDI continuam caindo nas barras da música);
- **um evento de tempo por beat** com a duração real daquele beat na gravação.

Resultado: o `.mid` tocado junto com o áudio a partir do tempo 0 cai nos beats
da gravação (teste automatizado: bumbo/caixa/baixo a ≤ 30 ms dos strums, com
andamento variando). Opção `--constant-tempo` / `follow_recording=False` grava a
BPM arredondada a partir do compasso 1 — útil quando a faixa de áudio for
*warpada* no Live; nesse caso alinhe o início do MIDI ao primeiro downbeat
informado.

## Uso

```powershell
$env:PYTHONPATH = "src"
python -m midi_generator.audio analyze guitar.wav            # resumo por compasso
python -m midi_generator.audio analyze guitar.wav --json     # MusicAnalysis v1
python -m midi_generator.audio accompany guitar.wav --output-dir output
# opções: --tempo-hint 70  --beats-per-bar 3  --pulse-bass  --constant-tempo  --seed N
```

Tools MCP: `analyze_audio_file(path, beats_per_bar?, tempo_hint?)` e
`generate_accompaniment_from_audio(path, style="basic", seed, sustain_bass,
follow_recording, ...)`, que grava em `output/accompaniment/`. Nenhuma das duas
escreve no Ableton.

Python:

```python
from midi_generator.audio import analyze_audio
from midi_generator.generation import generate_bass_from_analysis, generate_drums_from_analysis

analysis = analyze_audio("guitar.wav")
print(analysis.summary())
bass = generate_bass_from_analysis(analysis)
drums = generate_drums_from_analysis(analysis, style="basic")
```

## Limitações conhecidas

- **Oitava de tempo:** como todo beat tracker, pode ler música lenta (< ~70 BPM)
  em tempo dobrado, ou rápida pela metade (prior do librosa centrado em 120).
  Nenhum prior único resolveu a faixa 60–160 BPM nos testes; use `tempo_hint`
  (basta a oitava certa: 66 para uma música de 60 funciona).
- **Compasso:** só 4/4 e 3/4 são estimados; outros via `beats_per_bar`.
  Compassos compostos (6/8, 12/8) ainda não são tratados como tais.
- **Acordes:** só tríades maiores/menores. Sétimas e sus viram a tríade mais
  próxima; power chords (sem terça) têm qualidade incerta e confiança menor;
  inversões são lidas pela fundamental; acordes mudam só em beats.
- **Downbeat** inferido por mudança harmônica/acento: ambíguo se o acorde muda
  fora do tempo 1 ou se a gravação não tem acentuação.
- **Tempo livre/rubato forte** e gravações com voz ou banda completa não são
  alvo do MVP (sem separação de stems).
- Tonalidade só maior/menor natural, mesmo que a tabela de escalas tenha modos.
- Provenance v0 ainda rotula os geradores de papel como `heuristic` e não
  registra a análise; o `.analysis.json` gravado ao lado dos MIDIs é o contexto.

## Validação

Automatizada (`tests/test_audio_analysis.py`, `test_audio_interfaces.py`,
`test_accompaniment.py`, `test_music_analysis.py`): violão sintético em 64–120
BPM, colcheias, 3/4, anacruse, sétimas; tempo ± 2 BPM; beats ± 30 ms; acordes
por compasso; tonalidade; MIDI exportado nos beats da gravação.

**Pendente (humano):**

1. Gravar 8–16 compassos de uma progressão simples no violão (ex.: Am F C G a
   ~90 BPM, com metrônomo ou não) e salvar como WAV.
2. `python -m midi_generator.audio accompany take.wav --output-dir output`.
3. Conferir no resumo: tempo, compasso, tonalidade e acorde por compasso contra
   o que foi tocado.
4. No Live: arrastar o WAV e os dois `.mid` para três faixas na Arrangement
   View, todos no início (tempo do projeto irrelevante se o áudio **não** for
   warpado — o MIDI importado carrega o mapa de tempo; se o Live ignorar o mapa,
   usar `--constant-tempo`, warpar o áudio e alinhar o MIDI ao primeiro downbeat).
5. Ouvir: bumbo/caixa no tempo, baixo trocando de nota junto com os acordes.
   Registrar aqui o resultado com a gravação usada; só então marcar como validado.
