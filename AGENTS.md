# Direção do projeto

`midi-generator` deve evoluir de gerador/ponte MIDI para o motor musical de um
assistente de produção integrado ao Ableton Live. A infraestrutura não é o
produto final: cada incremento deve aproximar o sistema de análise,
transformação, geração contextual e composição assistida, sem antecipar
arquitetura que ainda não seja necessária.

## Limites das camadas

- **Assistente/raciocínio:** interpreta linguagem natural e converte intenção em
  decisões musicais; não exige que o usuário formule operações técnicas.
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
- Toda transformação deve ser reproduzível. Toda aleatoriedade vem de
  `random.Random(seed)` ou de mecanismo explicitamente derivado da seed; nunca
  use estado aleatório global.
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
4. Escolha um único incremento coeso que avance a visão musical. Prefira a menor
   capacidade útil, reutilizável, determinística, independente do Ableton e
   testável isoladamente; evite prolongar infraestrutura sem benefício musical.
5. Implemente o incremento na camada correta, crie/atualize testes e documentação
   e execute novamente `$env:PYTHONPATH = "src"; python -m pytest` (use o Python
   do `.venv` se necessário).
6. Revise o próprio diff procurando regressões, destruição involuntária,
   duplicação e vazamento de responsabilidades; então crie um commit coeso.
7. Ao encerrar, informe uma estimativa do avanço percentual obtido naquele
   `continue` e do percentual ainda restante para concluir a primeira versão
   utilizável do assistente musical integrado ao Ableton. Trate os valores como
   estimativas de capacidade, não como medições exatas, e mantenha consistente o
   critério de conclusão entre ciclos.

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
