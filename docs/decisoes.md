# Decisões

Cada entrada explica o problema que a escolha resolve e por que a alternativa foi descartada. O código citado só localiza onde isso está.

## Wrappers de estado

O agente devolve texto. O grafo precisa de campos (`formatted_response`, `approved`, `answer`, trechos do relatório) para decidir o próximo nó e para a resposta que sai da API. O schema do `create_agent` é só `messages`: o JSON do modelo está no texto da última mensagem. O wrapper interpreta esse texto e devolve o dict parcial. Sem ele, o runtime não tem chave para aplicar e o nó seguinte continua com o valor anterior ou vazio.

Um reducer não resolve isso. Ele combina, no canal, um valor que o nó já devolveu (`messages` via `add_messages`, `called_agents`, `judge_attempts`). Não lê mensagem, não faz parse e não cria `approved` ou `formatted_response`. Canal sem reducer, quando o wrapper devolve a chave, substitui o valor anterior.

O segundo motivo é o que chega ao modelo. Sem o wrapper, o estado inteiro entra no agente. Remover PII no guardrail de entrada perde o efeito se nome, unidade ou dado sensível voltam no turno seguinte porque ainda estavam no estado. O wrapper escolhe o recorte que o agente enxerga.

Para finalizar, usar wrappers foi uma escolha para ter maior controle sob o estado.

## HumanMessage no payload do sub-agente

O payload de um sub-agente (judge, guardrail de saída e os demais que recebem um turno serializado) vai em `HumanMessage`. A lista é local ao `.invoke()` e não entra no histórico da conversa.

`create_agent` já usa o system prompt do módulo como a única instrução de sistema. Uma segunda `SystemMessage` com o payload quebra a convenção que Gemini e a maioria dos provedores seguem: uma instrução de sistema e, em seguida, turnos human/AI. A segunda mensagem de sistema pode ser rejeitada ou descartada, e o agente responde sem o dado do turno. `HumanMessage` coloca esse dado no lugar que o provedor trata como conteúdo do usuário, sem disputar o papel de instrução.

## Integrações cross-repo via MCP

Inventário, predição e o contexto de unidade vivem em outros repositórios, cada um com o próprio deploy. A interface deles muda sem este repo coordenar o release. Acoplar por SDK ou HTTP fixo faria cada renomeação do outro lado virar alteração e redeploy aqui.

MCP entra quando as duas coisas são verdade: o modelo decide em runtime se chama a capacidade, e essa capacidade pertence a outro sistema. O cliente descobre as tools com `tools/list`. Uma tool nova ou um campo renomeado do outro lado não exige mudança de código neste processo.

Tool local fica para o que é deste repositório e só um agente usa. A busca do FAQ no Qdrant é esse caso: não há fronteira de sistema para desacoplar, e um servidor MCP só acrescentaria um processo e um contrato para manter.

O preditor tem tem dois consumidores, o ms-artificial-intelligence-core e o ms-administrative-core. Utilizar mcp aqui faz com que não precise atualizar o projeto em caso de mudança no contrato do modelo.

O cliente está em `_internal/mcp/clients.py`. Transporte `streamable_http`, URL `PREDICT_MODEL_MCP_URL`, header `apikey` com `PREDICT_MODEL_API_KEY` — o Kong exige api-key em toda rota. O boot exige três tools; falta uma e o processo não sobe, porque subir sem o vocabulário ou sem a tool de predição só falharia no primeiro turno do usuário:

| Tool | Por que está no boot |
|---|---|
| `list_valid_categories` | Vocabulário de `category`, lido uma vez |
| `list_valid_climate_zones` | Vocabulário de `climateZone`, lido uma vez |
| `predict_time_to_failure_batch` | Única tool passada ao agente |

As duas listas entram no prompt (`build_predict_model_system_prompt`). O agente não recebe as tools de listagem. Uma lista copiada no prompt já ficou desatualizada uma vez: o modelo passou a aceitar categorias que o prompt ainda não tinha, e a fonte passou a ser o próprio serviço, lida no boot. Copiar de novo no código deste repo repetiria o mesmo atraso.

Além de tudo isso, foi decisão de desing do projeto a escolha de separar os repositórios por **responsabilidade**, fazendo com que o mcp seja a melhor forma de integrar os diferentes sistemas. Isso não significa liberdade total do llm, pois os outros sistemas ainda fazem validações do lado deles, e o processo ainda é restrito (é bem diferente de simplesmente integrar um mcp ao banco, por exemplo).

## Histórico como contexto, não como pergunta

No começo, faq, report e predict_model recebiam só a pergunta já sem PII. O histórico inteiro persistia entre turnos. Reenviá-lo a um agente que executa uma tarefa única custava tokens e fazia o modelo misturar um turno antigo com a pergunta de agora — por exemplo, responder sobre o equipamento da mensagem anterior.

Isso quebrava referência conversacional ("o mesmo notebook", "gera o relatório disso"). A correção não foi voltar a passar `messages` como se fosse a pergunta. Orchestrator e especialistas recebem `request_with_history`: a pergunta atual continua sendo o que devem responder, e o histórico renderizado mais as preferências de longo prazo entram só como prefixo. O modelo vê o fio, mas a instrução deixa claro o que é pedido deste turno e o que é contexto.

O judge continua só com a pergunta deste turno. Ele julga se a resposta cabe nesse pedido. Com o histórico, uma resposta que conversa com o turno anterior e ignora o pedido atual pareceria coerente e seria aprovada. O guardrail de entrada lê a última mensagem bruta porque é ele quem produz a pergunta sem PII; os outros nós já consomem o resultado dessa limpeza.

## Hexagonal

Handlers, serviço e repositório separam a entrada HTTP da regra do turno para o grafo poder ser testado sem subir a API. As portas (`IMultiAgentService`, `IMultiAgentRepository`, `IUnitResolver`, `IStorageService`, `IPdfRenderer`) ficam em `multi_agent/multi_agent.py` e não importam Gemini, Redis, Mongo nem Supabase. Trocar o adaptador é mudar `app/api/composition.py`. O grafo em `multi_agent/graph.py` continua testável sem rede.

A escolha aqui foi por familiaridade, estamos habituados a mexer nessa estrutura, inclusive porque separa melhor o repositório por responsabilidade, o que facilita a manutenção e testes.

## Checkpoint único no Redis

Checkpointer em memória de processo não sobrevive a duas réplicas. Cada uma hidratava o Mongo por conta própria e divergia depois da primeira escrita: a réplica que não atendeu o turno anterior respondia com um fio mais curto. Um cache em processo ainda decidia sozinho quando limpar, então o TTL não era o mesmo nas duas.

`AsyncRedisSaver` (`multi_agent/async_redis_saver.py`), criado no composition root (`app/api/composition.py`), é a única cópia quente. As duas réplicas leem e escrevem o mesmo fio. O TTL nativo do `langgraph-checkpoint-redis` é `SESSION_TTL_SECONDS`, renovado a cada leitura, então a limpeza não depende de um mapa local que morre com o processo. `process_message` hidrata do Mongo (últimas mensagens e preferências) só quando o estado no Redis volta vazio. Duas réplicas no mesmo Redis não semeiam o mesmo fio duas vezes. Preferências de longo prazo atualizam em background nesse momento: um fio que ainda está quente não precisa ser resumido de novo, e resumir a cada turno gastaria uma chamada de modelo para um texto que não mudou. A unidade do usuário e o OAuth da fachada usam o mesmo Redis, com chaves e TTL próprios, para não manter um segundo store só por esses mapas.

## Integração com providers externos

A escolha de conectar com providers externos não é para cumprir requisitos do inter, até porque já seria cumprido nas outras integrações. Foi escolhido por uma linha de pensamento especifica: "No trabalho, é comum que tenha como conectar todas as ferramentas de trabalho em um único lugar (como o Nitro do picpay).", expor o mcp para provider externo é uma forma de garantir que os clientes possam utilizar as ferramentas do Zera com maior facilidade no dia a dia.

Por isso, foi escolhido o MCP para integrar com providers externos, pois é a melhor forma de garantir que os clientes possam utilizar as ferramentas do Zera com maior facilidade no dia a dia. Além disso, a integração deixa bem explicito que os melhores momentos para usar o mcp do zera é quando precisa rodar um caso de uso específico, já que o nosso mcp expõe apenas o oauth e o ask_zera (que roda o grafo).

Essa escolha também tem beneficios a nivel de custo, parte da conversa deixa de ser processada pelo nosso modelo, e passa a ser processada pelo provider externo.