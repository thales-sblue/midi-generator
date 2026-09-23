# Política de dependências, modelos e dados

## Regras de admissão

O `midi-generator` deve continuar operável sem APIs pagas por uso. Downloads
iniciais são permitidos; inferência e controle da DAW devem ser locais. Uma
dependência relevante só pode entrar no runtime depois de uma avaliação
registrada neste documento ou em um documento de POC que o referencie.

“Open source” descreve código, não necessariamente pesos, datasets ou outputs.
As quatro camadas devem ser verificadas separadamente:

1. licença e obrigações do código;
2. licença e obrigações dos pesos/checkpoints;
3. termos e proveniência do dataset, quando relevantes;
4. restrições sobre uso e distribuição dos outputs.

Uma marcação `NonCommercial`, ausência de licença dos pesos, termos ambíguos ou
incompatibilidade com monetização bloqueia o backend padrão. Esta política é uma
barreira técnica de produto, não um parecer jurídico.

## Ficha obrigatória

```text
Nome:
Função:
Código e versão/revisão:
Pesos e versão/revisão:
Dataset/proveniência:
Licença do código:
Licença dos pesos:
Restrições dos outputs:
Uso comercial permitido:
Executa localmente:
Funciona offline após download:
API paga necessária:
Hardware medido:
Motivo para inclusão:
O que substitui:
Riscos:
Fontes primárias e data da verificação:
Decisão: investigar | POC isolada | aprovado | rejeitado | congelado
Responsável/data da decisão:
```

Reavalie a ficha quando a revisão, o checkpoint ou os termos mudarem. A POC e o
backend integrado devem fixar revisões imutáveis e salvar os termos observados;
um nome flutuante como `main` ou `latest` não é proveniência suficiente.

Coerente com essa exigência, as dependências Python de runtime também devem ser
fixadas (`==` ou lock com hash), não por faixa. `requirements.txt` hoje usa
faixas; migrar para pins em ciclo próprio.

## Registro inicial — 30 de agosto de 2026

| Candidato | Código | Pesos/dados | Uso comercial | Decisão atual |
| --- | --- | --- | --- | --- |
| SkyTNT/midi-model | Apache-2.0 | checkpoint `midi-model-tv2o-medium` marcado Apache-2.0; datasets declarados: Los Angeles MIDI, Monster MIDI e SymphonyNet, ainda exigem revisão própria antes de treino | não há `NonCommercial` declarado no código ou no model card | POC automática passou em CUDA/CPU/offline; investigar qualidade por escuta antes de integrar; não está no runtime |
| EleutherAI/aria | Apache-2.0 | projeto declara modelos e MIDI tooling Apache-2.0; Aria-MIDI deve ser auditado separadamente se usado para treino | permitido pelos termos declarados, com risco de memorização apontado pelo próprio projeto | candidato futuro especializado em piano |
| stanford-crfm/music-medium-800k (Anticipatory Music Transformer) | Apache-2.0 | pesos marcados `apache-2.0` na tag e no `cardData` do HF; treinado no Lakh MIDI, que a Stanford CRFM marca como copyright presumidamente restritivo | sem `NonCommercial` nos pesos; risco de proveniência/memorização nos dados (camadas 3 e 4) | investigar — infilling/acompanhamento nativos; sequenciar após o gate de escuta do SkyTNT, não em paralelo |
| MIDI-GPT | código MIT | pesos oficiais `Metacreation/MIDI-GPT` sob CC-BY-NC-4.0; GigaMIDI é o dataset declarado | **incompatível** com backend comercial padrão | pesos rejeitados enquanto permanecerem NC |
| wstierhout/ableton-live-mcp | MIT | sem pesos; opera sobre Live local | permitido pela licença do código | avaliar como adapter futuro; nenhuma migração agora |
| AbletonOSC | MIT | sem pesos; opera sobre Live local | permitido pela licença do código | alternativa de transporte/API; nenhuma migração agora |
| ahujasid/ableton-mcp | MIT | sem pesos; Remote Script + socket JSON/TCP, arquitetura próxima à bridge atual | permitido pela licença do código | avaliar; sem salvaguardas não-destrutivas/fingerprint/concorrência; nenhuma migração agora |
| Simon-Kansara/ableton-live-mcp-server | MIT | sem pesos; mapeia AbletonOSC para tools MCP | permitido pela licença do código | avaliar junto do AbletonOSC; nenhuma migração agora |
| music21 | BSD para o toolkit | corpus possui termos por obra e pode conter restrições não comerciais | toolkit elegível; corpus não é automaticamente elegível | congelado até teoria avançada justificar |
| MusPy | MIT | datasets têm licenças próprias | biblioteca elegível; datasets dependem de auditoria | liberado apenas em venv isolada de avaliação/experimentos; nunca runtime ou default |
| MidiTok | MIT | não inclui um checkpoint necessário ao projeto | biblioteca elegível | congelado até haver necessidade de tokenização/treino |
| PDMX (dataset) | dataset MusicXML de domínio público (2025) | domínio público filtrado | rota de proveniência limpa | nota para fine-tuning futuro; nenhuma ação agora |

Fontes primárias consultadas:

- SkyTNT: [repositório](https://github.com/SkyTNT/midi-model), [checkpoint](https://huggingface.co/skytnt/midi-model-tv2o-medium)
- Aria: [repositório e termos declarados](https://github.com/EleutherAI/aria)
- Anticipatory Music Transformer: [código](https://github.com/jthickstun/anticipation), [pesos](https://huggingface.co/stanford-crfm/music-medium-800k)
- MIDI-GPT: [código](https://github.com/Metacreation-Lab/MIDI-GPT), [pesos e licença NC](https://huggingface.co/Metacreation/MIDI-GPT)
- Ableton: [Ableton Live MCP](https://github.com/wstierhout/ableton-live-mcp), [AbletonOSC](https://github.com/ideoforms/AbletonOSC), [ahujasid/ableton-mcp](https://github.com/ahujasid/ableton-mcp), [Simon-Kansara/ableton-live-mcp-server](https://github.com/Simon-Kansara/ableton-live-mcp-server)
- Dados de proveniência limpa: [PDMX](https://github.com/pnlong/PDMX)
- Bibliotecas: [music21](https://music21.org/music21docs/about/about.html), [MusPy](https://github.com/salu133445/muspy), [MidiTok](https://github.com/Natooz/MidiTok)

## Análise de áudio — 23 de setembro de 2026

```text
Nome: librosa (+ dependências transitivas)
Função: análise de áudio local — onset/beat tracking, chroma CQT, HPSS e
  Viterbi, usados por src/midi_generator/audio (docs/AUDIO_ANALYSIS.md)
Código e versão/revisão: librosa 0.11.0 (faixa >=0.11,<0.12 no requirements)
Pesos e versão/revisão: nenhum — o módulo não carrega modelo treinado
Dataset/proveniência: não aplicável (os dados de exemplo do librosa, baixados
  via pooch sob demanda, não são usados)
Licença do código: librosa ISC. Transitivas (metadados do pip nesta máquina):
  numpy BSD-3, scipy BSD-3, numba BSD-2, llvmlite BSD-2 (embute LLVM,
  Apache-2.0 com exceção LLVM), scikit-learn BSD-3, soundfile BSD-3 (embute
  libsndfile, LGPL-2.1), soxr LGPL-2.1-or-later, audioread MIT, pooch BSD-3,
  joblib BSD-3, msgpack Apache-2.0, lazy_loader BSD-3, decorator BSD-2,
  threadpoolctl BSD-3
Licença dos pesos: não aplicável
Restrições dos outputs: nenhuma — a análise é medição do áudio do usuário
Uso comercial permitido: sim. As duas bibliotecas LGPL (libsndfile, soxr) são
  ligadas dinamicamente; redistribuir o runtime empacotado exige cumprir a
  LGPL (permitir substituição da biblioteca, fornecer a licença)
Executa localmente: sim
Funciona offline após download: sim (nada é baixado na análise)
API paga necessária: não
Hardware medido: CPU desta máquina (Windows 11). ~1–2 s por gravação de 20–30 s
  após o primeiro uso; a primeira execução compila funções numba (~40 s) e
  guarda o cache em __pycache__
Motivo para inclusão: tempo, posição dos beats, chroma e acordes a partir de
  gravação — capacidade madura que não deve ser reimplementada
O que substitui: nada (capacidade nova)
Riscos: scipy 1.18.1 teve a DLL bloqueada pelo Controle de Aplicativo do
  Windows desta máquina, por isso scipy <1.17; numba/llvmlite pesam na
  instalação; o erro de oitava de tempo é inerente ao beat tracking
  (mitigado por tempo_hint)
Fontes primárias e data da verificação: metadados dos pacotes instalados
  (pip show / importlib.metadata) em 23/09/2026; https://github.com/librosa/librosa
Decisão: aprovado para o runtime (camada audio/ apenas)
Responsável/data da decisão: ciclo de análise de áudio, 23/09/2026
```

Alternativas avaliadas para acordes/beats (23/09/2026, nesta máquina):

| Candidato | Código | Pesos/dados | Situação | Decisão |
| --- | --- | --- | --- | --- |
| madmom | BSD (código) | modelos declarados CC BY-NC-SA 4.0 pelo projeto (a reconfirmar na fonte) | só sdist 0.16.1 (2018) no PyPI, sem wheel para Python 3.12/Windows | rejeitado: pesos NonCommercial e build inviável |
| Essentia | AGPL-3.0 | vários modelos TF com termos próprios | `pip download essentia` sem distribuição para Windows/Python 3.12 | rejeitado: AGPL e indisponível no Windows |
| Chordino / NNLS Chroma | plugin Vamp (GPL, a reconfirmar) | sem pesos | exige host Vamp; binário nativo | rejeitado para o runtime |
| autochord | MIT (metadado) | modelo próprio | exige TensorFlow; embute `nnls-chroma.so` só para Linux | rejeitado |
| crema | ISC | modelo pré-treinado incluído | exige Keras + TensorFlow; projeto sem atividade recente | congelado |
| basic-pitch (Spotify) | Apache-2.0 declarado | modelo incluído | exige TensorFlow <2.15.1 no Windows; transcreve notas, não acordes | candidato futuro para transcrever riffs/melodias, não para esta etapa |

## Proveniência mínima de uma geração futura

Um novo contrato versionado deverá poder relacionar, sem alterar o Payload v1:

- identificador da execução e timestamps;
- backend e versão do adapter;
- modelo/checkpoint e revisão ou hash;
- licenças verificadas na data da execução;
- seed e todos os parâmetros de amostragem;
- para backend de modelo: device, dtype e versões das bibliotecas (a mesma seed
  não reproduz o mesmo output entre CUDA/bfloat16 e CPU/float32);
- hash e cópia/referência do MIDI de contexto;
- MIDI bruto gerado e seu hash;
- transformações ordenadas com parâmetros e seeds;
- versões intermediárias e seus hashes;
- seleção, descarte, edição e aprovação humanas.

Os artefatos gerados permanecem em `output/` e fora do Git. O manifesto poderá
ser versionado como schema próprio quando existir uma POC aprovada; adicionar
campos ad hoc ao Integration Payload v1 está proibido.

Um manifesto de proveniência **v0**, cobrindo já os geradores heurístico e
contextual atuais (backend + versão, seed, todos os parâmetros, hash do clip de
contexto quando houver, hash do output, timestamp), é esperado antes ou junto do
v1: `create_contextual_variation` já entrega material derivado com apenas
fingerprint. Ele nasce como schema próprio, ao lado do Payload v1, e os campos de
modelo acima são acrescentados quando um backend de modelo for aprovado.
