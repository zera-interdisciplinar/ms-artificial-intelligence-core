# Projeto Zera — Overview

Panorama da plataforma, alinhado à wiki do Confluence (espaço Backend), atualizada em 31/10/2026:

- [Zera Back-end v1](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/55803906)
- [2. Máquina de estados do item](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/55836674)
- [Zera Android App v1](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/63537175)
- [9. Scrapy](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/72810497)
- [8. IA — ms-artificial-intelligence-core](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/64847873)

O detalhe dos agentes deste repositório está em [this-project-overview.md](this-project-overview.md).

## O que é

O Zera gerencia o ciclo de vida de equipamentos eletrônicos por unidade de uma organização, do cadastro ao descarte, com alertas de regra e previsão de falha. O app Android é o ponto operacional de operários e gestores. Este repositório é o serviço de IA (chat e PDF de descarte).

## Serviços

| Serviço | Responsabilidade |
|---|---|
| ms-administrative-core | Identidade: organizações, unidades, usuários, convites, JWT, alertas entregues ao usuário, analytics e governança. PostgreSQL (Flyway). |
| ms-inventory | Categorias, modelos, itens, eventos, descartes, regras de alerta, painéis e tools MCP. Neo4j. |
| Este repositório | Assistente (FAQ, inventário, previsão, texto de relatório) e PDF de descarte. |
| Serviço preditivo (`sdk-ml-failure-predictor`) | Meses restantes até a falha. O ms-inventory chama num job diário; este serviço chama via MCP; o app só lê `predictedFailureDate`. |
| scrapy | Envs de boot, flags e markdown para o app (`POST /v1/boot`, `POST /v1/flags`). PostgreSQL próprio. Microserviços não são consumidores. |

Os dois serviços Spring não leem o banco um do outro. O acoplamento entre eles é o JWT que o admin-core emite e o inventário valida. No inventário a unidade chega no header `X-Unit-Id`, nunca no corpo: recurso de outra unidade, visto dali, não existe (`404`). O catálogo de materiais é a exceção, global, semeado por migração.

## Hierarquia

1. **Categoria** — recorte do catálogo da unidade (Notebook, Televisão).
2. **Modelo** — um modelo dessa categoria, com garantia, vida útil, materiais e peso (MacBook Air M2).
3. **Item** — uma unidade física, com código de barras, estado e histórico.

`displayCode` é um código curto de 6 dígitos na UI, único por unidade, atribuído uma vez no cadastro. Não é o código de barras. `usageIntensity` é inteiro de 0 a 10, a mesma escala do modelo preditivo.

## Papéis

A v1 tem dois papéis no claim `role`: `EMPLOYEE` (operário) e `MANAGER` (gestor). Não há administrador.

Leitura exige autenticação. O operário cadastra e edita itens e modelos. O gestor faz isso e ainda cuida de categorias, regras, aprovações, exclusões, convites e transferência de unidade. Cancelar um descarte e restaurar um item removido são só do gestor.

## Estados do item

Nove estados. Todo item nasce `DRAFT`. Submit do operário vai para `PENDING_APPROVAL`; submit do gestor vai direto para `IN_STOCK`. Os demais são `REJECTED`, `IN_USE` (emprestado: só o estado, sem quem pegou nem prazo), `IN_MAINTENANCE`, `AWAITING_EVALUATION`, `DISPOSED` e `REMOVED` (remoção lógica; sai das listagens).

`DISPOSED` volta para `IN_STOCK` ou `AWAITING_EVALUATION` se o gestor cancelar o descarte. A foto não é obrigatória para sair do rascunho. Cada transição grava um evento imutável. A tabela completa está na [máquina de estados](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/55836674).

## Descarte e alertas

Descarte é registro do que já aconteceu (destino, local, data). Não há agendamento, nem catálogo próprio de recicladoras: o local vem de uma API externa e o sistema guarda `placeId` e `placeName`. O PDF do descarte sai deste serviço (`POST /api/v1/reports`). No app, a tela "Descartes agendados" é o histórico.

Alertas nascem de regras da unidade. São oito tipos; toda unidade nasce com os oito. O alerta é entregue pelo admin-core.

## Fora da v1

- Agendar descarte futuro
- Perfil de administrador
- Galeria de várias fotos por item
- Meta de reciclagem
- O app chamar o serviço preditivo direto
- Responsável e prazo de um empréstimo (`IN_USE` não guarda isso)
