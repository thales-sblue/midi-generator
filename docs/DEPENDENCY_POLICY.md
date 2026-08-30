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
