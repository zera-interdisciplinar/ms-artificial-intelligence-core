# contexto

Hoje em dia, a aplicação tem seu checkpointer em memoria, isso é um problema, já que quando for escalar o serviço para mais réplicas, cada checkpointer iria ficar desatualizado, principalmente depois da leitura no banco.

# solução

Para resolver esse problema, vamos utilizar redis para armazenar o checkpointer em memoria. Dessa forma, o memory saver iria ser compartilhado entre todas as réplicas. Ainda teriamos o ganho de colocar as mensagens em cache: evita ficar lendo a base toda hora, piorando a performance.

# implementação

Para a implementação, iremos criar um novo pacote checkpointer, que irá conter toda a lógica de leitura e escrita no redis. Ele deverá ser instanciado na main, e teria uma nova interface para o checkpointer, dentro de multi_agent/multi_agent.py

## infra

Será necessario criar tanto em compose, quanto nas pipelines de deploy, um novo service para o redis. Com um default no Environments apontando para ele (igual ao mongodb).

## Forma de implementação

A implementação deve ser feita usando TDD. Primeiro crie a interface e implemente testes para ele, certificando em não degradar nenhum fluxo.
Além disso, implemente usando subagent-driven, coloque subagente para a implementação com todo o plano, e um em seguida para validar. Tenha nesse segundo subagente, instrução para validar se não tem: funções atoa, código morto implementado, complexidade desnecessária, etc.
# atualização

Implementado com `AsyncRedisSaver` (`multi_agent/async_redis_saver.py`), criado no composition root (`app/api/composition.py`) com o TTL nativo do `langgraph-checkpoint-redis` (`SESSION_TTL_SECONDS`, renovado a cada leitura). O `ThreadCache` em memória, que ainda decidia hidratação e limpeza por processo, foi removido: a hidratação acontece quando `aget_state` volta vazio, e a limpeza é o próprio TTL do Redis. Com isso, nada do estado de conversa impede mais de uma réplica. Ver decisão 7 em `docs/this-project-overview.md`.
