# Contrato de API — Assistente de IA (`/api/v1/multi-agent`, `/api/v1/reports`)

Documentação de contrato das rotas do `ms-artificial-intelligence-core` para os clientes (app mobile / web): **chat do assistente**, **histórico de conversas** e **PDF de relatório de descarte**.

O chat é um único endpoint (`POST /api/v1/multi-agent/process-message`). O roteamento interno (FAQ, inventário, predição de tempo até falha, relatório em linguagem natural) é decisão do grafo de agentes, não de rotas HTTP separadas.

## Autenticação e headers comuns

| Header | Obrigatório | Descrição |
|---|---|---|
| `Authorization` | Sim, em todas as rotas exceto `/health` | `Bearer <access_token>` — JWT emitido no login do `ms-administrative-core` (`POST /api/v1/auth/login`). O Kong já validou o token; este serviço só **lê o usuário** dele (claim `sub`) e encaminha o header **como veio** para o admin-core ao resolver a unidade. |
| `X-Unit-Id` | Não | A unidade **não** vem de header. O cliente manda `unit_id` no **body** de `process-message`. A autoridade é o `unitId` do usuário no `ms-administrative-core`. |

**O usuário nunca vem do body nem da query**, só do Bearer. Um `user_id` enviado no body ou na query é ignorado (compatível com clientes antigos). Isso impede que um usuário logado leia ou escreva como outro.

Token ausente: **`422`** (FastAPI: header `Authorization` é obrigatório). Bearer sem usuário legível: **`401`** `{"detail": "invalid bearer token"}`. Usuário irresolvível no admin-core / `unit_id` que não é o do usuário: **`403`**.

**Papel por tipo de rota** (não há checagem de `MANAGER`/`EMPLOYEE` neste MS):

| Autorização | Rotas (neste contrato) |
|---|---|
| Usuário do Bearer + `unit_id` conferido no admin-core | `POST /api/v1/multi-agent/process-message` |
| Usuário do Bearer + unidade do usuário no admin-core | `POST /api/v1/reports`, `GET /api/v1/reports/{disposal_id}` |
| Usuário do Bearer | `GET /api/v1/multi-agent/conversations`, `GET /api/v1/multi-agent/conversations/{thread_id}` |
| Público | `GET /health` |

Este microserviço **não** valida header `apiKey` nas rotas HTTP próprias. A chamada de saída para o admin-core usa `apikey` de serviço (config do backend). Se a chamada do app passar pelo gateway, o edge pode exigir `x-api-key` à parte.

JSON de request/response usa **snake_case** (`thread_id`, `unit_id`, `page_size`, `report_url`). Não é o camelCase do `ms-administrative-core`.

Há envelope de paginação em `GET /conversations` (`items` + `page` + `page_size` + `total`). `GET /conversations/{thread_id}` devolve um **array simples** de mensagens.

---

## 0. `GET /health` — liveness

Sem prefixo `/api/v1`. Sem autenticação.

### Request

```
GET /health HTTP/1.1
```

### Response — `200 OK`

```json
{ "status": "ok" }
```

---

## 1. `POST /api/v1/multi-agent/process-message` — um turno do chat

Endpoint único do assistente. Cria ou continua a thread `thread_id` do usuário do Bearer. A unidade proposta no body é validada contra o admin-core **antes** de qualquer agente rodar.

O cliente **não** escolhe o agente. Exemplos de intenção (texto livre em `content`):

- FAQ da plataforma Zera → agente `faq`
- Dado já existente no inventário (item, lote, bateria, garantia) → `inventory_agent`
- Estimativa de tempo até falha de equipamento → `predict_model`
- Texto de relatório (sem PDF) → `report`
- Fora de escopo / PII / injection → `blocked: true` (guardrail)

### Request

```
POST /api/v1/multi-agent/process-message HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "thread_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "unit_id": "aa11bb22-0000-0000-0000-000000000009",
  "content": "O que é o projeto Zera?"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `thread_id` | UUID | Sim | Id da conversa. **O app gera** (UUID v4). Mesmo `thread_id` = continua o histórico. Thread nova = UUID novo. |
| `unit_id` | UUID | Sim | Unidade **proposta**. Tem que coincidir com `unitId` do usuário no admin-core. Ausente: `422`. Errado: `403`. |
| `content` | string | Sim | Mensagem do usuário. Mínimo 1, máximo **8000** caracteres. |

```bash
curl -X POST "https://<host>/api/v1/multi-agent/process-message" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "unit_id": "aa11bb22-0000-0000-0000-000000000009",
    "content": "O que é o projeto Zera?"
  }'
```

### Response — `200 OK`

```json
{
  "content": "Zera é a plataforma de gestão de sucata eletrônica...",
  "blocked": false,
  "blocked_reason": null,
  "agent_trace": ["guardrail_in", "orchestrator", "faq", "formatter", "judge", "guardrail_out"],
  "report_url": null,
  "redirect_to": {"screen": "Scan", "message": "Escanear código de barras"}
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `content` | string | Texto para exibir no chat. Se `blocked` e o fluxo parou cedo, pode ser o `blocked_reason` (ou string vazia). |
| `blocked` | bool | `true` se guardrail/orquestrador recusou (off-topic, PII, intenção não classificada, etc.). Ainda assim o HTTP é **200**. |
| `blocked_reason` | string \| null | Motivo em linguagem natural quando `blocked`. |
| `agent_trace` | string[] | Nomes dos nós do grafo que rodaram neste turno (ordem de execução). Ver **Enums**. Não usar para UI de produto; é telemetria. |
| `report_url` | string \| null | **Sempre `null` neste endpoint.** O chat **não** sobe PDF. PDF de descarte é `POST /api/v1/reports`. |
| `redirect_to` | `{screen, message}` \| null | Atalho abaixo da mensagem. `screen` é o protocolo de encaminhamento (rota Android `Route.kt` sem prefixo, PascalCase). `message` é a mensagem de exibição no componente. Vem do FAQ. Fora do FAQ, inválido ou ausente: `null`. |

Pergunta e resposta são gravadas **juntas, só quando o turno inteiro termina**. Nada é gravado se o fluxo parou no `guardrail_in` (`blocked` e `orchestrator` ausente do `agent_trace`) ou se o turno falhou (`502`/`503`); nesses casos a mensagem também sai do histórico usado nos próximos turnos.

| Status | Quando |
|---|---|
| `200` | Processou (inclusive recusa lógica com `blocked: true`). |
| `401` | Bearer sem usuário legível. |
| `403` | `unit_id` ≠ unidade do usuário no admin-core, usuário inexistente, admin-core indisponível/não-200, ou JWT que o admin-core recusa. Body: `{"detail": "unit_id does not belong to this user"}`. |
| `422` | Body inválido (UUID, `content` vazio/`>8000`) **ou** header `Authorization` ausente. Envelope FastAPI `{"detail": [...]}`. |
| `502` | Um agente devolveu saída fora do formato esperado. |
| `503` | Falha no banco. |

---

## 2. Histórico de conversas

O recorte é o usuário do Bearer: cada um só vê as próprias conversas.

### 2.1 `GET /api/v1/multi-agent/conversations` — lista (tela de threads)

Página de threads do usuário, **mais recentemente ativas primeiro**. `preview` = primeiros **40** caracteres da **primeira** mensagem da thread.

### Request

```
GET /api/v1/multi-agent/conversations?page=1&page_size=20 HTTP/1.1
Authorization: Bearer <token>
```

| Query param | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `page` | int | Não (default `1`) | Paginação **1-based**. Mínimo `1`. |
| `page_size` | int | Não (default `20`) | Entre `1` e `100`. |

```bash
curl -X GET "https://<host>/api/v1/multi-agent/conversations?page=1&page_size=20" \
  -H "Authorization: Bearer eyJhbGciOi..."
```

### Response — `200 OK`

```json
{
  "items": [
    {
      "thread_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "last_message_at": "2026-07-16T13:00:00Z",
      "preview": "O que é o projeto Zera?"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

- `last_message_at`: ISO-8601 UTC (`Z`).
- `total`: quantidade de threads, não de mensagens.
- Lista vazia: `items: []` e `total: 0` (não é `404`).

### 2.2 `GET /api/v1/multi-agent/conversations/{thread_id}` — mensagens da thread

Todas as mensagens da thread, **mais antigas primeiro**, só se pertencerem ao usuário do Bearer. Array simples (sem envelope). As mensagens do usuário vêm como foram gravadas, com PII mascarada (`<CPF_0>`, `<EMAIL_0>`...).

### Request

```
GET /api/v1/multi-agent/conversations/{thread_id} HTTP/1.1
Authorization: Bearer <token>
```

| Path | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `thread_id` | UUID | Sim | Id da conversa. Thread de outro usuário: array vazio. |

```bash
curl -X GET "https://<host>/api/v1/multi-agent/conversations/3fa85f64-5717-4562-b3fc-2c963f66afa6" \
  -H "Authorization: Bearer eyJhbGciOi..."
```

### Response — `200 OK`

```json
[
  {
    "role": "user",
    "content": "O que é o projeto Zera?",
    "created_at": "2026-07-16T12:00:00Z"
  },
  {
    "role": "assistant",
    "content": "Zera é a plataforma...",
    "created_at": "2026-07-16T12:00:02Z"
  }
]
```

`role` na API é `user` / `assistant` / `system`. O rótulo de UI é mapeamento do app.

Thread inexistente ou sem mensagens para esse usuário: **`[]`** (não `404`).

---

## 3. Relatório de descarte (PDF)

O chat (`process-message` com intenção de relatório) devolve **texto** em `content` e **não** grava arquivo. PDF só neste grupo. Um relatório por `disposal_id` (índice neste MS, não no inventário).

O relatório pertence à **unidade** do usuário que o gerou (resolvida no admin-core). Outra unidade não lê nem reaproveita. Relatórios gravados antes desse campo existir só voltam para quem os gerou.

### 3.1 `POST /api/v1/reports` — gerar ou reutilizar PDF

Gera o HTML pelo mesmo `report_agent` do chat (sem o grafo inteiro: sem guardrail/orchestrator/judge), renderiza PDF, sobe no storage, persiste `{disposal_id, user_id, unit_id, report_url}`. Se já existir relatório da mesma unidade para aquele `disposal_id`, **devolve a URL existente** (não regenera). Dois POST simultâneos não dão erro: o primeiro gravado vale.

### Request

```
POST /api/v1/reports HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "disposal_id": "42"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `disposal_id` | string | Sim | Id do descarte (mínimo 1 caractere). Entra no pedido ao agente. |

```bash
curl -X POST "https://<host>/api/v1/reports" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -H "Content-Type: application/json" \
  -d '{"disposal_id":"42"}'
```

### Response — `200 OK`

Tanto geração nova quanto hit de relatório já existente.

```json
{
  "report_url": "https://cdn.example.com/disposal-42.pdf"
}
```

Nome do arquivo no storage: `disposal-{disposal_id}.pdf`. Falha de storage **não** grava no Mongo (o erro sobe como 5xx).

| Status | Quando |
|---|---|
| `200` | URL nova ou já persistida. |
| `401` | Bearer sem usuário legível. |
| `403` | Unidade irresolvível ou descarte de outra unidade. Body: `{"detail": "disposal does not belong to this user's unit"}`. |
| `422` | Body inválido (`disposal_id` vazio) ou `Authorization` ausente. |

### 3.2 `GET /api/v1/reports/{disposal_id}` — URL já gerada

Não gera. Só lê o que o POST gravou, se for da unidade do usuário.

### Request

```
GET /api/v1/reports/{disposal_id} HTTP/1.1
Authorization: Bearer <token>
```

```bash
curl -X GET "https://<host>/api/v1/reports/42" \
  -H "Authorization: Bearer eyJhbGciOi..."
```

### Response — `200 OK`

```json
{
  "report_url": "https://cdn.example.com/disposal-42.pdf"
}
```

| Status | Quando |
|---|---|
| `200` | Relatório existe e é da unidade do usuário. |
| `403` | Unidade irresolvível. Body: `{"detail": "the user's unit cannot be resolved"}`. |
| `404` | Nunca gerado, ou é de outra unidade (não revela qual). Body: `{"detail": "disposal report not found"}`. |

Fluxo típico na UI: após concluir um descarte, `POST /reports` e abrir `report_url`. Reabrir a tela: `GET /reports/{disposal_id}`; `404` → ainda não gerado, chamar o POST.

---

## Enums usados

- **`role`** (mensagem): `user`, `assistant`, `system`.
- **`agent_trace`** (nós do grafo): `guardrail_in`, `orchestrator`, `faq`, `report`, `predict_model`, `inventory_agent`, `formatter`, `judge`, `guardrail_out`.
- **`blocked`**: boolean. Recusa de conteúdo/intenção **não** vira status HTTP 4xx.

Não há enum de intenção na API HTTP: a intenção fica só no estado interno do grafo.

## Qual rota escolher

| Preciso de... | Rota |
|---|---|
| Enviar mensagem do chat / FAQ / inventário / predição / texto de relatório | `POST /api/v1/multi-agent/process-message` (`Authorization` + `unit_id` no body) |
| Saber se o turno foi recusado pelo guardrail | Mesmo POST: HTTP 200 + `blocked` / `blocked_reason` |
| URL do PDF de um descarte (gerar) | `POST /api/v1/reports` — **não** usar `report_url` do chat |
| URL do PDF já gerado | `GET /api/v1/reports/{disposal_id}` |
| Lista de conversas (inbox) | `GET /api/v1/multi-agent/conversations` (`page` 1-based, `preview` 40 chars) |
| Abrir uma conversa | `GET /api/v1/multi-agent/conversations/{thread_id}` |
| Health check | `GET /health` |
