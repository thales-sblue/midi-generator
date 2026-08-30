# Auditoria arquitetural — direção de agente produtor

Data da auditoria: 30 de agosto de 2026.

## Conclusão executiva

A arquitetura atual deve ser estendida, não substituída. Ela já contém o núcleo
que diferencia o produto: estruturas MIDI pequenas e independentes, geração e
transformação reproduzíveis, análise objetiva, contratos versionados e uma
barreira de segurança não destrutiva validada no Ableton Live 12 Lite.

As maiores lacunas para a primeira versão útil não são mais transformações
isoladas nem primitivas de Session View. São geração local multitrack de maior
qualidade, avaliação/seleção de alternativas, proveniência completa e operações
amplas de produção no Live. Geração e integração ampla com o Live têm candidatos
externos relevantes; reimplementá-las agora seria construir infraestrutura, não
capacidade musical.

Decisão deste ciclo: nenhuma refatoração de código. O menor incremento necessário
é tornar permanentes as regras de admissão e registrar a fronteira futura de
backends/proveniência. A POC isolada do SkyTNT foi executada depois desta
auditoria; os resultados estão em `docs/POC_SKYTNT_RESULTS.md` e ainda não
autorizam integração sem comparação auditiva.

## Mapa atual

| Camada | Capacidade existente | Avaliação |
| --- | --- | --- |
| Domínio | `NoteEvent`, `MelodyRequest`, `CompositionPlan`, `GenerationReport`, tabelas maior/menor | simples, testável e valiosa; preservar |
| Geração | heurística determinística e geração contextual por densidade, fase, registro, pitch class, movimento, duração e velocity | manter como backend heurístico conceitual; não tentar transformá-la em modelo complexo |
| Análise | perfil de clip, polifonia, tessitura, dinâmica, ritmo, movimento da voz superior e compatibilidade com 24 escalas | diferencial reutilizável; ampliar somente por demanda |
| Transformações | transpose, invert, retrograde, quantize, legato, staccato, humanize, escala, transposição/harmonia diatônica e velocity ramp | núcleo próprio puro e determinístico; preservar |
| Integração | conversão beats/ticks, Payload v1 JSON-safe, serialização de análise | manter contratos; criar schema novo para proveniência quando houver backend aprovado |
| MCP | tools tipadas e orquestração de geração, análise, preflight, duplicação e replace | camada correta; não mover algoritmos musicais para ela |
| Ableton client/bridge | loopback TCP/JSON, Session View, leitura/criação/duplicação/replace de clips, fingerprints e `CLIP_CHANGED` | estreita, mas segura e validada no Live 12 Lite; congelar expansão ampla |
| Export | Mido isolado em `MidiExporter` | adequado |
| Testes | 204 testes, incluindo processo MCP real e fakes da Live API; validações manuais registradas | forte proteção de regressão; não comprova novas integrações reais |

## Diferencial que não deve ser perdido

- domínio imutável e sem dependência de Live, MCP ou Mido;
- aleatoriedade local derivada de seed;
- dry-run/preflight antes de mutação;
- cópia não destrutiva como padrão;
- fingerprint do source no instante da duplicação e da cópia no replace;
- recusa explícita de estado obsoleto com `CLIP_CHANGED`;
- payload temporal versionado e conversão determinística para ticks;
- testes de fronteira e evidências reais no Live 12 Lite 12.4.5.

Essas garantias devem envolver qualquer adapter externo. “Mais tools” não é
equivalência de segurança.

## Duplicação de soluções externas e congelamentos

### Ableton

O `wstierhout/ableton-live-mcp` declara 154 tools locais para tracks, mixer,
clips/notas, devices, browser, Arrangement, automação, áudio e análise. Usa um
Remote Script local, socket loopback e MCP stdio; a licença é MIT e não há API
paga obrigatória. Ele cobre quase todas as grandes áreas que a bridge atual não
cobre. A própria documentação alerta que algumas operações apagam, substituem
ou sobrescrevem material.

AbletonOSC, também MIT e local, oferece uma API OSC ampla para song, tracks,
clips/notas, devices e mixer, com alguma leitura de Arrangement. É uma base de
transporte mais genérica e menos orientada a tools de agente.

Consequência: congelar criação própria de tracks, mixer, devices, browser,
Arrangement e automação. Antes de usar qualquer candidato, ainda é obrigatório:

- validar instalação e cada capacidade no Live 12 Lite real;
- comparar leitura/escrita MIDI, criação de tracks, devices, mixer, browser,
  Arrangement e automação numa matriz executável;
- verificar cobertura efetiva limitada pela edição Lite;
- envolver mutações com snapshot/fingerprint/preflight/cópia ou undo controlado;
- testar estado obsoleto, target ocupado, falha parcial e recuperação;
- manter a bridge atual até equivalência comprovada.

### Teoria, avaliação e tokenização

As operações atuais são pequenas demais para justificar music21. Quando o core
precisar de análise harmônica, voice leading ou teoria substancial, avaliar o
toolkit BSD e evitar seu corpus sem auditoria por obra. MusPy oferece métricas
úteis para comparar backends, mas ainda não existe comparação que justifique o
custo de runtime. MidiTok resolve tokenização/treino; os candidatos SkyTNT e Aria
já possuem tokenizers próprios, portanto adicioná-lo agora seria antecipação.

## Candidatos generativos

### SkyTNT midi-model — prioridade de POC

- Código e checkpoint `midi-model-tv2o-medium` são marcados Apache-2.0.
- A linha recomendada para a POC é a versão v1.3/tokenizer v2 declarada pelo
  upstream com esse checkpoint `tv2o-medium`, sempre fixando commits/revisões em
  vez de depender desses nomes móveis.
- O checkpoint safetensors tem 468 MB; o repositório HF inteiro inclui formatos
  duplicados e artefatos e soma aproximadamente 1,92 GB.
- O código usa PyTorch/Transformers, oferece checkpoint/ONNX, app para Windows e
  geração programática; a síntese com FluidSynth é opcional para avaliar MIDI.
- Aceita MIDI existente como prompt, continuação do último output, múltiplos
  canais/instrumentos e drums, BPM, compasso, tonalidade, limite de eventos,
  temperature/top-p/top-k e `torch.Generator(...).manual_seed(seed)`.
- Não foi encontrada documentação de controles de alto nível explícitos para
  densidade, duração e curva de velocity. A POC deve distinguir preservação
  desses eventos de controle intencional; ausência desses controles é uma
  limitação, não algo a preencher antecipadamente no adapter.
- A RTX 3070 com 8 GB de VRAM foi detectada nesta máquina em 30/08/2026. O
  checkpoint parece caber com folga, mas VRAM de pico, RAM, latência, qualidade,
  determinismo completo e compatibilidade Windows só serão fatos após benchmark.
- O dataset declarado no model card precisa de uma revisão separada antes de
  treino/fine-tuning. Para inferência com os pesos publicados, os termos atuais
  não declaram restrição `NonCommercial`; ainda assim, a POC deve arquivar a
  revisão e os termos observados.

### Aria — candidato especializado posterior

O projeto declara código, modelos e tooling Apache-2.0. O modelo de cerca de
0,7B foi treinado majoritariamente em performance expressiva de piano, oferece
continuação por prompt MIDI, CUDA, MLX e uma implementação CPU. O próprio projeto
recomenda single-track piano, alerta para sensibilidade à qualidade do prompt e
risco de reproduzir obras clássicas representadas no treino. Isso o torna um
backend futuro de piano/keys, não o primeiro backend geral.

### MIDI-GPT — código elegível, pesos rejeitados

O código atual é MIT e oferece infill/multitrack programático, mas o model card
oficial licencia os checkpoints sob `CC-BY-NC-4.0`. Os pesos não podem ser
backend padrão de um produto orientado a lançamento e monetização.

## Riscos

| Risco | Impacto | Tratamento |
| --- | --- | --- |
| confundir licença do código com pesos/dados | inviabiliza uso comercial | ficha obrigatória e revisão fixada |
| output memorizar material de treino | risco artístico/autoral | prompts próprios, múltiplas alternativas, análise de similaridade futura e seleção humana |
| backend não determinístico apesar da seed | quebra reprodução | teste byte/evento a evento em processo novo e registro de ambiente |
| modelo cabe em disco, mas não em VRAM/RAM | POC impraticável | medir pico e CPU fallback antes de integrar |
| adapter Ableton amplo ser destrutivo | perda de trabalho | manter nossa camada de segurança e validação real |
| schema de proveniência quebrar Payload v1 | regressão de integração | schema novo e adapter explícito |
| dependências pesadas contaminarem runtime leve | instalação frágil | extras/processo isolado e backend opcional |

## Arquitetura-alvo incremental

```text
Codex / usuário
      ↓ intenção, seleção e decisões humanas
midi-generator — orquestração e contexto
      ├─ domínio/análise/transformações próprias
      ├─ backend heurístico atual
      ├─ backends locais opcionais aprovados
      └─ registro versionado de proveniência
      ↓ camada nossa de segurança
adapter Ableton validado (bridge atual ou externo)
      ↓
Ableton Live
```

Backends devem receber uma requisição explícita e produzir uma representação
adaptável ao domínio mais um manifesto. O core não importa PyTorch, tokenizer ou
classes específicas do modelo. Falha ou ausência do backend generativo não
remove a operação heurística existente.

## Experimento generativo executado

A POC SkyTNT foi escolhida porque testa a maior lacuna musical sem arriscar a
integração Live já funcional. A auditoria Ableton já é suficiente para impedir
expansão duplicada; migrar agora teria alto raio de regressão e menor ganho
imediato. A matriz automática passou localmente em CUDA, CPU e offline, com
determinismo dentro do mesmo dispositivo, mas divergência CPU/CUDA e controle
expressivo limitado. O protocolo está em `docs/POC_SKYTNT.md`, e as evidências
em `docs/POC_SKYTNT_RESULTS.md`. O próximo gate é escuta comparativa; até lá, o
estado permanece `investigar` e não existe backend novo no runtime.
