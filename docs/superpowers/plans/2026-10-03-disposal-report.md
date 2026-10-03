# Relatório de descarte Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistir no storage só o relatório gerado para um descarte, e expor a URL desse PDF por `disposal_id`.

**Architecture:** O `report_agent` continua único. O chat deixa de fazer upload. Um `POST /api/v1/reports` recebe `disposal_id` e `user_id`, gera o HTML pelo mesmo agente, renderiza o PDF, sobe para o storage e grava `{disposal_id, report_url}` no Mongo. Um `GET /api/v1/reports/{disposal_id}` devolve essa URL. Se o descarte já tiver relatório, o POST devolve a URL existente.

**Tech Stack:** FastAPI, MongoDB (pymongo), WeasyPrint (`PdfRenderer`), Supabase storage, LangGraph `report_agent`.

## Global Constraints

- Mesma capacidade de relatório nos dois cenários; só o gatilho muda.
- Sem id de descarte, nenhum upload.
- Índice fica neste serviço (coleção Mongo), não no ms-inventory.
- Um relatório por `disposal_id`.
- Solução mínima: sem segundo agente, sem segundo prompt, sem abstração nova de “tipo de relatório”.

## File structure

- `multi_agent/entity.py` — modelo `DisposalReport`.
- `multi_agent/multi_agent.py` — métodos na interface do repositório e do serviço.
- `repository/multi_agent.py` — coleção `disposal_reports`.
- `multi_agent/service.py` — tira o upload do chat; adiciona `create_disposal_report` e `get_disposal_report`.
- `_internal/api/dto.py` — bodies de request/response.
- `_internal/api/multi_agent_handlers.py` — `POST /reports` e `GET /reports/{disposal_id}`.
- Testes ao lado de cada módulo alterado.

---

### Task 1: Persistência

**Files:** `multi_agent/entity.py`, `repository/multi_agent.py`, `multi_agent/multi_agent.py`, testes do repositório.

- [ ] Modelo `DisposalReport`: `disposal_id: str`, `user_id: UUID`, `report_url: str`, `created_at: datetime`.
- [ ] Coleção `disposal_reports` com índice único em `disposal_id`.
- [ ] `save_disposal_report` e `get_disposal_report(disposal_id) -> DisposalReport | None`.
- [ ] Teste: salvar e ler; segundo save do mesmo id não duplica (upsert ou rejeição tratada no serviço — preferir leitura antes de gerar, então insert simples).

### Task 2: Chat não sobe PDF

**Files:** `multi_agent/service.py`, teste de `process_message` que cobre o upload.

- [ ] Remover o bloco que renderiza e faz upload quando `report_html` existe no fim do chat.
- [ ] `AgentResponse.report_url` do chat fica sempre `None`.
- [ ] Teste existente que espera upload no fluxo de mensagem passa a esperar que o storage não seja chamado.

### Task 3: Gerar e consultar

**Files:** `multi_agent/service.py`, `multi_agent/multi_agent.py`.

- [ ] `get_disposal_report(disposal_id) -> str | None` lê a URL.
- [ ] `create_disposal_report(user_id, disposal_id) -> str`:
  1. Se já existe, devolve a URL.
  2. Monta um `current_request` pedindo o relatório daquele descarte (o id entra no texto do pedido; o agente e as tools MCP continuam iguais).
  3. Invoca só o `report_agent` já compilado (não o grafo inteiro: sem guardrail, orchestrator, formatter, judge).
  4. Renderiza o HTML, faz upload `disposal-{disposal_id}.pdf`, grava e devolve a URL.
- [ ] Falha de storage propaga; nada é gravado no Mongo.
- [ ] Testes com storage e agente falsos: caminho novo gera e grava; caminho repetido não chama o agente; chat não chama upload.

### Task 4: HTTP

**Files:** `_internal/api/dto.py`, `_internal/api/multi_agent_handlers.py`, teste do handler se já existir o padrão.

- [ ] `POST /api/v1/reports` body `{ user_id, disposal_id }` → `201` `{ report_url }` (200 se já existia é aceitável; usar 200 nos dois casos para não distinguir).
- [ ] `GET /api/v1/reports/{disposal_id}` → `200` `{ report_url }` ou `404`.
- [ ] Teste do handler com serviço falso.

### Task 5: Verificação

- [ ] `make test` nos módulos tocados.
