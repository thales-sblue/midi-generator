# Resultado da POC isolada — SkyTNT midi-model

Data da execução: 30 de agosto de 2026.

Decisão: **investigar; não integrar ao runtime ainda**.

## Resumo executivo

O checkpoint `midi-model-tv2o-medium` funcionou localmente no Windows, em CUDA
e CPU, sem Gradio, FluidSynth ou API paga. Geração do zero, continuação de MIDI
próprio, prompt multitrack e execução offline produziram arquivos MIDI
estruturalmente válidos. Repetições em processos novos foram idênticas para a
mesma seed, dispositivo e dtype; seeds diferentes mudaram o resultado.

O gate técnico automático foi satisfeito, mas a POC **não recomenda integração
ainda** por três motivos:

- a mesma seed divergiu entre CUDA/bfloat16 e CPU/float32, portanto dispositivo
  e dtype são parte obrigatória da proveniência;
- os controles observados são condicionamento por eventos MIDI, não garantias
  rígidas de instrumentação, densidade, duração ou dinâmica; numa geração CUDA
  de 32 notas, todas as velocities resultaram em `127`;
- a qualidade musical ainda não foi avaliada por escuta humana. Integrar antes
  dessa comparação com o backend heurístico anteciparia arquitetura sem provar
  valor musical.

## Revisões, licenças e artefatos

| Item | Evidência fixada |
| --- | --- |
| Código | `SkyTNT/midi-model` em `f504d5cb58f769ab0f2909c679238f6621034573` |
| Licença do código | Apache-2.0; `LICENSE` SHA-256 `313605fbac6945e9324d4825470796b5b7dbc012f523fdc181f6e6fd234eb88f` |
| Checkpoint | `skytnt/midi-model-tv2o-medium` em `0f8f265d4330f4e46527ac2313200254c5757f5f` |
| Licença dos pesos | model card e metadados: Apache-2.0; nenhum termo `NonCommercial` observado |
| `model.safetensors` | 467.701.064 bytes; SHA-256 `82ac8b2217f8f66f79737e444fe60c686d3cbfee54b0c8ef717f701213bbbb83` |
| Dados declarados | Los Angeles MIDI Dataset, Monster MIDI Dataset e SymphonyNet MIDI Dataset |
| Inferência | local; nenhuma API remota chamada |

Os datasets foram registrados por proveniência, mas não foram admitidos para
treino ou fine-tuning. Qualquer uso dos dados exige auditoria separada. A
licença declarada dos pesos permite esta POC de inferência segundo a política
técnica do projeto; isto não é parecer jurídico nem elimina risco de
memorização nos outputs.

Foram baixados somente `model.safetensors`, `config.json`,
`generation_config.json`, o model card e `.gitattributes`. O diretório do modelo
ocupou 467.706.491 bytes. O ambiente virtual isolado ocupou 4.917.549.178 bytes;
o wheel CUDA do PyTorch tinha 2,5 GB e levou 9min08s para baixar nesta execução.
Esse custo confirma que o backend deve permanecer opcional e fora do runtime
leve.

Fontes primárias: [repositório SkyTNT](https://github.com/SkyTNT/midi-model) e
[checkpoint tv2o-medium](https://huggingface.co/skytnt/midi-model-tv2o-medium).

## Ambiente medido

| Componente | Valor |
| --- | --- |
| Sistema/Python | Windows 11, Python 3.12.13 |
| CPU/RAM | 6 processadores lógicos, 17.112.834.048 bytes de RAM |
| GPU/driver | NVIDIA GeForce RTX 3070, 8.589.410.304 bytes; driver 616.56 |
| PyTorch/CUDA | `2.4.1+cu124`, CUDA 12.4 |
| Transformers/PEFT | `4.44.2` / `0.13.2` |
| Checkpoint em CUDA | bfloat16 |
| Checkpoint em CPU | float32 |

O ambiente completo está fixado em
`experiments/requirements-skytnt-poc.txt`; cada manifesto também registra o
ambiente efetivo.

## Matriz executada

Cada cenário principal foi executado duas vezes em processos novos com a mesma
seed e uma vez com seed diferente. Os artefatos completos permanecem em
`output/poc_skytnt/runs/` e não são versionados.

| Cenário | Resultado objetivo |
| --- | --- |
| Do zero, CUDA, 32 eventos novos | quatro canais `0,1,2,9`, programas `0,32,88,0`, 32 notas, 5 tracks, 4/4, 120 BPM; 3,678 s na primeira execução |
| Prompt próprio monotrack, CUDA | prefixo preservado, 36 notas totais, 2 tracks, continuação válida; 3,101 s |
| Prompt próprio multitrack, CUDA | prefixo preservado, 48 notas totais, canais/programas preservados, 5 tracks; 3,029 s |
| Curto offline, CUDA | 8 notas, quatro canais, válido; 1,474 s |
| Curto offline, CPU | 4 eventos pedidos: 4 notas com seed 91; 0,991–1,022 s; ~1,82 GiB RSS |

Todos os 14 MIDIs gerados abriram com Mido, usaram pitches válidos e terminaram
sem notas presas. Os prompts, BPM, compasso, tonalidade e programas foram
representados como eventos MIDI explícitos. Velocities também são geradas e
preservadas, mas a POC não encontrou controle de alto nível para curva dinâmica;
os resultados observados variaram de faixas úteis a saturação completa em 127.

O modo offline foi executado com `HF_HUB_OFFLINE=1` e
`TRANSFORMERS_OFFLINE=1`, usando apenas paths locais, em comandos sem permissão
de rede do sandbox. Isso prova operação após o download, não instalação sem
rede.

## Determinismo

| Caso | Seed | Hash de eventos |
| --- | ---: | --- |
| scratch CUDA A/B | 2026 | `def3ec686323ef964486b5faf2d481c901a84003c0288197ff043d77fbb3eb35` nas duas execuções |
| prompt CUDA A/B | 2026 | `426fc239ddc7468f1ecdadb956edb67f12100fe294dfeb153ae66c353d9ba2de` nas duas execuções |
| multitrack CUDA A/B | 2026 | `14aada49f07af4f6e0afd2219e422d56354b6b921ed148da4177f312e150df50` nas duas execuções |
| CPU A/B | 91 | `f754ada336cfbc01ed082079075076c3dd209a36b84b1abaabcc4afc64b17ed0` nas duas execuções |
| CUDA, mesma seed 91 | 91 | `898a1fa920b10c798877ebac1d05b4e322f2f7ec4acfa395f5e2e238b219c2b3` |

Seeds diferentes produziram hashes diferentes em todos os grupos. CPU e CUDA
divergiram com seed 91, como esperado de caminhos numéricos/dtypes diferentes.
A reprodução deve fixar no mínimo revisão do código e pesos, versões, seed,
parâmetros, dispositivo e dtype.

## Memória e latência

Na primeira geração CUDA de 32 eventos, o modelo carregou em 3,478 s, gerou em
3,678 s, atingiu 478.366.720 bytes de memória CUDA alocada e 486.539.264 bytes
reservados. O processo chegou a aproximadamente 2,76 GiB RSS. A POC cabe com
grande margem na RTX 3070 de 8 GB, embora a instalação em disco seja pesada.

As medições cobrem sequências curtas e batch 1; não caracterizam contexto de
4.096 eventos, batches maiores, latência sustentada ou pico de RAM/VRAM em uma
sessão longa.

## Reprodução

O runner executa um caso por processo e recusa reutilizar um `run-id`:

```powershell
python -m venv output/poc_skytnt/venv
output/poc_skytnt/venv/Scripts/python.exe -m pip install -r experiments/requirements-skytnt-poc.txt
output/poc_skytnt/venv/Scripts/python.exe experiments/poc_skytnt.py `
  --case multitrack --device cuda --seed 2026 `
  --run-id multitrack-cuda-seed2026 --max-new-events 32 --offline
```

O código upstream deve estar em `output/poc_skytnt/upstream` na revisão fixada,
e os cinco arquivos permitidos do modelo em `output/poc_skytnt/model`. O runner
salva `prompt.mid`, quando aplicável, `generated.mid` e `manifest.json`.

## Gate humano pendente

Antes de propor `GenerationBackend`, comparar por escuta cega pelo menos estas
saídas com variações heurísticas contextuais de duração equivalente:

- `scratch-cuda-seed2026-a/generated.mid`;
- `prompt-cuda-seed2026-a/generated.mid`;
- `multitrack-cuda-seed2026-a/generated.mid`;
- `offline-cuda-seed77/generated.mid`.

Registrar coerência rítmica/harmônica, utilidade como material editável,
instrumentação, dinâmica, artefatos e preferência. Sem essa evidência, o estado
permanece `investigar` e nenhum contrato de runtime será criado.
