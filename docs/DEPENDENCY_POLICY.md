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

## Registro inicial — 30 de agosto de 2026

| Candidato | Código | Pesos/dados | Uso comercial | Decisão atual |
| --- | --- | --- | --- | --- |
| SkyTNT/midi-model | Apache-2.0 | checkpoint `midi-model-tv2o-medium` marcado Apache-2.0; dataset declarado: Los Angeles/Monster MIDI, ainda exige revisão própria antes de treino | não há `NonCommercial` declarado no código ou no model card | POC isolada; não está no runtime |
| EleutherAI/aria | Apache-2.0 | projeto declara modelos e MIDI tooling Apache-2.0; Aria-MIDI deve ser auditado separadamente se usado para treino | permitido pelos termos declarados, com risco de memorização apontado pelo próprio projeto | candidato futuro especializado em piano |
| MIDI-GPT | código MIT | pesos oficiais `Metacreation/MIDI-GPT` sob CC-BY-NC-4.0; GigaMIDI é o dataset declarado | **incompatível** com backend comercial padrão | pesos rejeitados enquanto permanecerem NC |
| wstierhout/ableton-live-mcp | MIT | sem pesos; opera sobre Live local | permitido pela licença do código | avaliar como adapter futuro; nenhuma migração agora |
| AbletonOSC | MIT | sem pesos; opera sobre Live local | permitido pela licença do código | alternativa de transporte/API; nenhuma migração agora |
| music21 | BSD para o toolkit | corpus possui termos por obra e pode conter restrições não comerciais | toolkit elegível; corpus não é automaticamente elegível | congelado até teoria avançada justificar |
| MusPy | MIT | datasets têm licenças próprias | biblioteca elegível; datasets dependem de auditoria | congelado até benchmark entre backends |
| MidiTok | MIT | não inclui um checkpoint necessário ao projeto | biblioteca elegível | congelado até haver necessidade de tokenização/treino |

Fontes primárias consultadas:

- SkyTNT: [repositório](https://github.com/SkyTNT/midi-model), [checkpoint](https://huggingface.co/skytnt/midi-model-tv2o-medium)
- Aria: [repositório e termos declarados](https://github.com/EleutherAI/aria)
- MIDI-GPT: [código](https://github.com/Metacreation-Lab/MIDI-GPT), [pesos e licença NC](https://huggingface.co/Metacreation/MIDI-GPT)
- Ableton: [Ableton Live MCP](https://github.com/wstierhout/ableton-live-mcp), [AbletonOSC](https://github.com/ideoforms/AbletonOSC)
- Bibliotecas: [music21](https://music21.org/music21docs/about/about.html), [MusPy](https://github.com/salu133445/muspy), [MidiTok](https://github.com/Natooz/MidiTok)

## Proveniência mínima de uma geração futura

Um novo contrato versionado deverá poder relacionar, sem alterar o Payload v1:

- identificador da execução e timestamps;
- backend e versão do adapter;
- modelo/checkpoint e revisão ou hash;
- licenças verificadas na data da execução;
- seed e todos os parâmetros de amostragem;
- hash e cópia/referência do MIDI de contexto;
- MIDI bruto gerado e seu hash;
- transformações ordenadas com parâmetros e seeds;
- versões intermediárias e seus hashes;
- seleção, descarte, edição e aprovação humanas.

Os artefatos gerados permanecem em `output/` e fora do Git. O manifesto poderá
ser versionado como schema próprio quando existir uma POC aprovada; adicionar
campos ad hoc ao Integration Payload v1 está proibido.
