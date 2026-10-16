# Projeto Zera — Overview

Panorama da plataforma, alinhado à wiki do Confluence (espaço Backend): [Zera Back-end v1](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/55803906) e [Zera Android App v1](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/63537175). O detalhe de agentes deste repositório está em [this-project-overview.md](this-project-overview.md).

## O que é

O Zera gerencia o ciclo de vida de equipamentos eletrônicos **por unidade** de uma organização: cadastro, estoque, manutenção, descarte e alertas de regra, com previsão de falha. O app Android é o ponto operacional de operários e gestores. Este repositório é o serviço de IA (chat e PDF de descarte).

## Serviços

| Serviço | Responsabilidade |
|---|---|
| ms-administrative-core | Identidade: organizações, unidades, usuários, convites, JWT, alertas entregues ao usuário |
| ms-inventory | Categorias, modelos, itens, eventos, descartes, regras de alerta, painéis e tools MCP |
| Este repositório | Assistente (FAQ, inventário, previsão, texto de relatório) e PDF de descarte |
| sdk-ml-failure-predictor | Meses restantes até a falha. O ms-inventory chama num job diário; o app só lê `predictedFailureDate` |

Os serviços de back-end não leem o banco um do outro. O acoplamento é o JWT que o admin-core emite e o inventário valida. A unidade é o limite de isolamento: recurso de outra unidade, visto daqui, não existe (`404`).

## Hierarquia

1. **Categoria** — recorte do catálogo da unidade (Notebook, Televisão).
2. **Modelo** — um modelo dessa categoria, com garantia, vida útil, materiais e peso (MacBook Air M2).
3. **Item** — uma unidade física, com código de barras, estado e histórico.

`displayCode` é um código curto de 6 dígitos na UI, único por unidade. Não é o código de barras.

## Papéis

A v1 tem dois papéis no claim `role`: `EMPLOYEE` (operário) e `MANAGER` (gestor). Não há administrador.

Leitura exige autenticação. O operário cadastra e edita itens e modelos. O gestor faz isso e ainda cuida de categorias, regras, aprovações, exclusões, convites e transferência de unidade. Cancelar um descarte é só do gestor.

## Estados do item

Todo item nasce `DRAFT`. Submit do operário vai para `PENDING_APPROVAL`; submit do gestor vai direto para `IN_STOCK`. Os demais estados são `REJECTED`, `IN_MAINTENANCE`, `AWAITING_EVALUATION` e `DISPOSED`. A foto não é obrigatória para sair do rascunho. Cada transição grava um evento imutável.

## Descarte e alertas

Descarte é registro do que **já aconteceu** (destino, local, data). Não há agendamento, nem catálogo próprio de recicladoras: o local vem de uma API externa e o sistema guarda `placeId` e `placeName`. O PDF do descarte sai deste serviço (`POST /api/v1/reports`).

Alertas nascem de regras da unidade (quantidade em estoque, tempo parado, garantia, vida útil, intensidade de uso, falha prevista, entre outras). Toda unidade nasce com o conjunto padrão. O alerta é entregue pelo admin-core.

## Fora da v1

- Agendar descarte futuro
- Perfil de administrador
- Galeria de várias fotos por item
- Meta de reciclagem
- O app chamar o serviço preditivo direto