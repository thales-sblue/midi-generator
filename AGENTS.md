# Direção do projeto

> Este arquivo é canônico para a direção de produto, o licenciamento e o
> protocolo de trabalho, qualquer que seja o assistente. No Claude Code, leia
> também [`CLAUDE.md`](CLAUDE.md), que cobre apenas o ambiente local (venv,
> comandos, `--basetemp` do pytest, estado do `origin`).

`midi-generator` deve evoluir de gerador/ponte MIDI para o motor musical de um
assistente de produção integrado ao Ableton Live. A infraestrutura não é o
produto final: cada incremento deve aproximar o sistema de análise,
transformação, geração contextual e composição assistida, sem antecipar
arquitetura que ainda não seja necessária.

O produto é um agente/orquestrador musical: combina domínio e transformações
próprias com bibliotecas maduras, modelos generativos locais e integração local
com o Ableton. Não é objetivo reimplementar um DAW, uma biblioteca universal de
teoria musical, um Transformer MIDI ou toda a Live API.

## Escopo da primeira versão utilizável

A "primeira versão utilizável" cobrada pelo Protocolo para "continue" é:
**backend heurístico + geração contextual + bridge própria de MIDI clips na
Session View, validada no Live real.** Backends de modelo generativo e operações
amplas no Live (tracks, mixer, devices, Arrangement, automação, transporte) são
explicitamente pós-v1. O escopo Ableton do v1 é apenas MIDI clips na Session
View. A estimativa de percentual de cada ciclo mede o avanço contra esse escopo.

Hipótese de trabalho para pós-v1: design **híbrido** — o modelo gera ideia bruta;
o heurístico, as transformações determinísticas e o assistente externo fazem o
controle fino. A confirmar no gate de escuta comparativa.

## Restrições de produto e licenciamento

- O runtime e a produção musical não podem depender de API comercial cobrada
  por uso, inferência remota paga ou SaaS obrigatório. Isso vale para qualquer
  API comercial de LLM/assistente (OpenAI, Anthropic, etc.): usar Codex, Claude
  ou outro assistente para desenvolver o projeto não autoriza dependência da API
  do respectivo provedor no runtime ou na produção musical.
- O assistente externo que interpreta linguagem natural e orquestra os ciclos é
  uma peça separada do motor. Ele pode ser uma API paga; o motor alcançado por
  ele via MCP tem de rodar standalone, local e offline, sem esse assistente.
- Pesos podem ser baixados inicialmente, mas a inferência deve funcionar
  localmente e, depois do download, offline sempre que o backend permitir.
- Toda dependência relevante exige avaliação separada da licença do código, dos
  pesos e, quando aplicável, do dataset. Registre restrições `NonCommercial`,
  condições de atribuição e qualquer incompatibilidade com lançamento,
  monetização, distribuição, registro ou licenciamento de música.
- Não presuma que “open source” autoriza uso comercial. Não torne padrão um
  backend cujos pesos sejam `NonCommercial`; em particular, os pesos oficiais
  atuais do MIDI-GPT sob `CC-BY-NC-4.0` não são elegíveis.
- Registre toda avaliação no formato de `docs/DEPENDENCY_POLICY.md` antes de
  integrar a dependência ao runtime. Dúvida de licença bloqueia integração, não
  a auditoria ou uma POC isolada sem distribuição.

## Integração antes de implementação

Antes de criar uma capacidade, verifique se ela já existe de forma madura,
gratuita, local e comercialmente utilizável. Se existir, avalie integração ou
adaptação antes de escrever uma implementação própria. Uma dependência só entra
quando resolve um problema musical ou operacional concreto; o projeto não deve
virar uma coleção de dependências.

- Preserve operações pequenas e claras no domínio próprio. Antes de ampliar
  teoria musical substancialmente, avalie `music21`.
- Considere MusPy para avaliação comparativa e MidiTok apenas quando treinamento
  ou tokenização independente realmente exigirem; não os adicione por padrão.
- Não expanda a bridge própria para grandes áreas novas do Live antes de avaliar
  as integrações externas (Ableton Live MCP, AbletonOSC, `ahujasid/ableton-mcp`,
  `Simon-Kansara/ableton-live-mcp-server`). A hipótese preferencial era manter
  nossa camada de segurança/orquestração sobre uma integração externa mais ampla;
  como nenhuma das opções pesquisadas oferece não-destrutividade, fingerprint ou
  controle de concorrência, "envolver externo" vs "estender a bridge própria"
  fica em aberto. Nenhuma avaliação de Live amplo está agendada para o v1.
- Faça POC isolada e reproduzível antes de integrar ou substituir. Fixe versão,
  checkpoint, licença, hardware, seed, entradas, parâmetros e outputs. Uma POC
  bem-sucedida ainda exige equivalência automatizada e validação real no Live
  antes de aposentar código funcional.

## Geração e proveniência

- Trate geração como backends desacoplados. O gerador atual permanece como
  backend heurístico leve, determinístico, testável e sem GPU obrigatória; o core
  não deve depender diretamente de um modelo específico.
- Modelos locais especializados podem complementar o heurístico. Não integre
  vários simultaneamente: prove primeiro um backend generativo útil no hardware
  real.
- Prepare cada fluxo para registrar backend, nome e versão do modelo, seed,
  parâmetros, contexto MIDI, resultado gerado, transformações, versões
  intermediárias e decisões humanas. Evolua contratos de integração por versão;
  não quebre silenciosamente o `Integration Payload v1`.
- Um manifesto de proveniência v0 para os geradores heurístico e contextual
  atuais é esperado antes ou junto do v1 (`generate_contextual_variation` já
  entrega material derivado com apenas fingerprint). Ele fica em schema próprio
  versionado, ao lado do Payload v1, nunca dentro dele.
- Favoreça geração de alternativas, avaliação, seleção, transformação e edição
  humana. Evite um fluxo opaco que trate a primeira geração como obra final.

## Limites das camadas

- **Assistente/raciocínio:** interpreta linguagem natural e converte intenção em
  decisões musicais; não exige que o usuário formule operações técnicas. É
  intencionalmente uma peça externa (hoje o Claude Code; antes o Codex),
  possivelmente uma API paga, fora do motor e substituível. O motor, alcançado
  por ele via MCP, não depende dessa camada.
- **Domínio/core:** concentra teoria, análise, geração e transformações musicais.
  Deve ser independente de Ableton, MCP, Mido e efeitos de I/O sempre que
  possível, para ser testável com estruturas MIDI próprias.
- **MCP:** expõe tools e orquestra fluxos; não contém algoritmos musicais
  complexos. Não introduza um MIDI MCP externo como dependência obrigatória
  entre o motor e o Ableton.
- **Ableton bridge/client:** camada de I/O sobre a Live API para localizar, ler,
  criar, duplicar e substituir clips. Não interpreta linguagem natural nem
  decide regras musicais.

## Segurança e determinismo

- Operações em material existente são não destrutivas por padrão: preserve o
  source e crie uma cópia/versão quando fizer sentido. Alteração destrutiva exige
  intenção explícita.
- Proteja fluxos sujeitos a edições manuais concorrentes com fingerprints (ou
  mecanismo equivalente) e recuse estado obsoleto antes da mutação.
- Reprodutibilidade tem dois níveis. **Bit-exato**, independente de plataforma:
  o backend heurístico, a geração contextual e todas as transformações — toda
  aleatoriedade vem de `random.Random(seed)` ou de mecanismo explicitamente
  derivado da seed, nunca de estado aleatório global. **Ambiente fixado**: um
  futuro backend de modelo só reproduz o mesmo output com seed + device + dtype +
  versões de bibliotecas iguais (a mesma seed diverge entre CUDA/bfloat16 e
  CPU/float32); esses valores passam a ser proveniência obrigatória. Nenhum
  backend de modelo pode degradar o nível bit-exato das capacidades atuais.
- Grave MIDI gerado em `output/` e não o versione, salvo exemplo intencional.
- Não adicione GUI, controle de DAW adicional ou recursos de IA sem pedido
  explícito.

## Protocolo para “continue”

Ao receber uma instrução curta para prosseguir:

1. Leia `AGENTS.md`, `README.md`, a árvore, o estado do Git, os commits recentes
   e o diff do HEAD.
2. Procure pendências e validações manuais; execute a suíte completa antes de
   alterar código.
3. Confirme o que já existe para não reimplementar capacidades.
4. Pergunte explicitamente: “Estou criando algo que já existe de forma madura,
   gratuita, local e comercialmente utilizável?”. Se sim, avalie integração.
5. Escolha um único incremento coeso que avance a visão musical. Prefira a menor
   capacidade útil, reutilizável, determinística, independente do Ableton e
   testável isoladamente; evite prolongar infraestrutura sem benefício musical.
6. Implemente o incremento na camada correta, crie/atualize testes e documentação
   e execute novamente `$env:PYTHONPATH = "src"; python -m pytest` (use o Python
   do `.venv` se necessário).
7. Revise o próprio diff procurando regressões, destruição involuntária,
   duplicação e vazamento de responsabilidades; então crie um commit coeso.
8. Ao encerrar, informe uma estimativa do avanço percentual obtido naquele
   `continue` e do percentual ainda restante para concluir a primeira versão
   utilizável, conforme a seção "Escopo da primeira versão utilizável". Trate os
   valores como estimativas de capacidade, não como medições exatas, e mantenha
   consistente o critério de conclusão entre ciclos.
9. Depois que a suíte estiver validada, a revisão concluída e o commit criado com
   sucesso, publique o HEAD validado diretamente em `origin/main`, sem exigir
   branch intermediária ou pull request. Antes do push, atualize a referência do
   remoto e recuse atualizações que não sejam fast-forward. Confirme que o push
   terminou sem erro antes de declarar o trabalho concluído. Nunca faça push de
   uma suíte com falhas ou de um worktree com alterações ainda não revisadas.

## Fronteiras de validação

Testes automatizados não comprovam comportamento da Live API. Quando o próximo
trabalho depender de uma hipótese ainda não validada no Ableton Live real, pare
nessa fronteira, mantenha o status explicitamente pendente e forneça os comandos,
payloads e conferências mínimas para validação humana. Nunca registre validação
manual sem evidência real.

Essa fronteira não bloqueia trabalho puro de domínio: capacidades musicais que
possam ser verificadas isoladamente devem continuar avançando. Depois de cada
incremento, o próximo deve ser escolhido pelo valor musical e pela fundação que
oferece a recursos futuros, não pela complexidade da integração.
