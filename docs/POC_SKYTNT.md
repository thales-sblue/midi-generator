# POC isolada — SkyTNT midi-model

Status: matriz automática executada em 30 de agosto de 2026; escuta humana
pendente. Decisão atual: **investigar; não integrar ao runtime ainda**.

Os resultados, hashes, medições, limitações e comandos reproduzíveis estão em
[`POC_SKYTNT_RESULTS.md`](POC_SKYTNT_RESULTS.md).

## Hipótese

O checkpoint local `skytnt/midi-model-tv2o-medium` pode gerar e continuar MIDI
multitrack no Windows atual, de forma reproduzível e rápida o suficiente para um
fluxo iterativo, sem API paga e sem contaminar o runtime leve do projeto.

## Escopo e isolamento

- usar ambiente virtual separado, fora das dependências obrigatórias;
- fixar commit do código e revisão imutável do checkpoint;
- preferir `model.safetensors`; não baixar o `.bin` duplicado sem necessidade;
- não usar Gradio nem FluidSynth para provar inferência MIDI;
- gravar inputs, outputs e manifestos em `output/poc_skytnt/`;
- não importar SkyTNT no core, MCP ou bridge;
- não modificar nem substituir funcionalidades atuais.

## Pré-condições de licença

Antes do download, salvar no manifesto:

- URL, revisão e texto Apache-2.0 do código;
- URL, revisão e marcação Apache-2.0 do checkpoint;
- datasets declarados no model card;
- data da verificação e ausência/presença de termos adicionais;
- confirmação de que nenhuma API remota será chamada na inferência.

Se os pesos perderem licença comercial clara ou surgirem termos adicionais
incompatíveis, a POC para antes da inferência.

## Matriz mínima

Executar cada caso duas vezes em processos novos com a mesma seed e uma vez com
seed diferente:

1. geração do zero com piano, baixo, drums e um instrumento harmônico;
2. prompt de um MIDI próprio curto e continuação;
3. prompt multitrack preservando programas/canais relevantes;
4. geração curta em CUDA;
5. o mesmo caso em CPU, ainda que apenas como fallback funcional;
6. execução offline depois que código e checkpoint estiverem em cache.

Fixar BPM, compasso, tonalidade, instrumentos, número máximo de eventos,
temperature, top-p, top-k, seed, batch e versões de Python, PyTorch, CUDA,
Transformers e driver.

## Medições

- hardware: CPU, RAM total/pico, GPU, VRAM total/pico e espaço em disco;
- tempo de carregamento e de geração;
- tamanho exato dos artefatos baixados;
- determinismo dos eventos MIDI e diferenças entre CUDA/CPU;
- validade estrutural, duração, canais, programas, notes fora de faixa e notas
  presas;
- capacidade real de prompt, continuação, multitrack, instruments, drums,
  velocity, tempo e compasso, registrando explicitamente quais atributos são
  apenas gerados/preservados e quais são controláveis;
- qualidade musical por escuta humana registrada, sem confundir preferência com
  teste automatizado.

Hardware já observado: NVIDIA GeForce RTX 3070, 8192 MiB de VRAM, driver
616.56. A leitura de RAM/CPU foi bloqueada pelo ambiente atual e deve ser feita
na POC antes do download completo. Há aproximadamente 342 GB livres na unidade
de trabalho.

## Gates de aprovação

A POC só recomenda integração se:

- código e pesos permanecerem comercialmente elegíveis;
- rodar local e offline após o download;
- produzir MIDI válido em todos os casos essenciais;
- mesma seed e ambiente reproduzirem os mesmos eventos, ou qualquer limite de
  determinismo for medido e documentado;
- pelo menos um modo couber com margem no hardware atual;
- prompt/continuação e multitrack funcionarem programaticamente sem GUI;
- a qualidade justificar o custo sobre o heurístico;
- o adapter puder ficar opcional e fora do core.

## Saída esperada da POC

- relatório com revisões, licenças, hardware, tempos e memória;
- manifestos e hashes de input/output;
- pequenos scripts experimentais isolados, não uma API definitiva;
- recomendação `aprovar`, `rejeitar` ou `investigar`, com evidências;
- somente se aprovado, proposta mínima de contrato `GenerationBackend` e schema
  de proveniência, preservando `generate_plan()` como fallback heurístico.

Fontes primárias: [código SkyTNT](https://github.com/SkyTNT/midi-model),
[checkpoint tv2o-medium](https://huggingface.co/skytnt/midi-model-tv2o-medium).
