# Zera MCP + ChatGPT plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor o grafo multi-agente já existente como servidor MCP (Streamable HTTP no FastAPI) e empacotar um plugin ChatGPT (manifest + skill) que manda o modelo só chamar o Zera quando o pedido cabe num especialista.

**Architecture:** Fachada fina no mesmo FastAPI. Só duas tools MCP: `login` (proxy para `POST` de login do ms-administrative-core) e `ask_zera` (`process_message`). O grafo continua opaco. Relatório PDF (`POST /api/v1/reports`) **não** vira tool nem rota nova no plugin — quem quiser PDF usa o app Zera; no chat, texto de relatório ainda pode sair pelo `report_agent` via `ask_zera` se o orquestrador escolher. Sessão MCP guarda JWT/`user_id`/`unit_id` **no servidor**; o modelo não recebe o token. Sem banco de senha neste MS.

**Tech Stack:** FastAPI já existente, pacote `mcp` (FastMCP + `streamable_http_app`), pytest, pacote Agent Plugins (`plugin.json` + `mcp.json` + `skills/`).

## Global Constraints

- Tools MCP: `login` e `ask_zera` apenas. Sem `create_disposal_report`, sem nós do grafo.
- Login não inventa identidade: `AdminCoreClient` chama o login do admin-core (mesmo contrato dos testes de integração). Este MS continua sem validar JWT localmente.
- Resultado de `login` para o LLM: `{ ok, user_id, unit_id }` — **nunca** `accessToken` / Bearer. Token só em memória por sessão MCP (TTL curto, ex. igual `SESSION_TTL_SECONDS`).
- `ask_zera` exige sessão logada; argumentos: `content` + `thread_id`. `user_id`/`unit_id`/Bearer saem da sessão, não do modelo.
- Não apontar ChatGPT/Claude para o MCP do ms-inventory / predict_model.
- Sem A2A, sem OAuth CIMD nesta entrega.
- Testes `test_*.py` ao lado do código.
- Copy: chamar `ask_zera` só se o objetivo alinhar a FAQ, inventário, TTF ou texto de relatório; senão não chamar. PDF de descarte: fora do MCP.
- Credenciais no tool `login` passam pelo host (ChatGPT/Claude). A skill manda pedir login uma vez e não repetir senha. 403 de unit mismatch continua erro da tool.

## File structure

- `requirements.txt` — adicionar `mcp`.
- `_internal/mcp/server.py` — FastMCP, `login` + `ask_zera`, sessão em memória.
- `_internal/mcp/session.py` — mapa session_id → {authorization, user_id, unit_id, expires_at}.
- `_internal/mcp/test_server.py` — login proxy fake; ask_zera sem sessão falha; token não aparece no dict de retorno.
- `_internal/admin_core/client.py` — `login(email, password)` → resposta do `POST /api/v1/auth/login` do admin-core.
- `_internal/api/router.py` — monta `/mcp`, lifespan do session manager.
- `_internal/api/test_mcp_mount.py` — app montado responde no path `/mcp` (initialize ou 406/400 MCP, não 404).
- `plugin/plugin.json`, `plugin/mcp.json`, `plugin/skills/zera/SKILL.md`.
- `docs/this-project-overview.md` — uma decisão técnica: fachada MCP/plugin.
- `config/environments.py` — `PUBLIC_MCP_URL` opcional só para documentar o URL no `mcp.json` de exemplo (o arquivo do plugin usa placeholder; não gerar JSON em runtime).

---

### Task 1: Dependência `mcp`

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nada
- Produces: pacote `mcp` instalável (`from mcp.server.fastmcp import FastMCP`)

- [ ] **Step 1: Adicionar a dependência**

Em `requirements.txt`, depois de `langchain-mcp-adapters`:

```
mcp
```

Não pin de major se o resto do repo não pina; se `FastMCP` tiver sido removido na v2 local, usar `MCPServer` do mesmo pacote com a mesma API de `streamable_http_app()` — o teste da Task 2 trava o import.

- [ ] **Step 2: Instalar**

Run: `pip install mcp`

Expected: exit 0; `python -c "from mcp.server.fastmcp import FastMCP"` ou, se falhar, `from mcp.server.mcpserver import MCPServer`.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "$(cat <<'EOF'
chore: add mcp SDK to serve Streamable HTTP

EOF
)"
```

---

### Task 2: Tools MCP sobre `IMultiAgentService`

**Files:**
- Create: `_internal/mcp/__init__.py` (vazio ou docstring de uma linha)
- Create: `_internal/mcp/server.py`
- Create: `_internal/mcp/test_server.py`

**Interfaces:**
- Consumes: `IMultiAgentService.process_message(message, user_id, thread_id, unit_id, authorization) -> AgentResponse`; `create_disposal_report(user_id, disposal_id) -> str`; `UnitMismatchException`
- Produces: `build_mcp(service, admin_core) -> FastMCP`; tools **somente** `login` e `ask_zera`. Sem tool de PDF.

Texto obrigatório na description de `ask_zera` (e ecoado na skill depois):

```
Use only when the user goal matches a Zera specialist:
(1) FAQ about the Zera platform,
(2) factual inventory already stored (item, batch, battery, warranty, hazardous checklist),
(3) predicted time-to-failure for equipment,
(4) disposal report text/PDF.
Do not call for general chat, coding, or topics outside those four. The orchestrator will still refuse off-topic requests, but skipping the call is cheaper and clearer.
```

- [ ] **Step 1: Teste que falha — `ask_zera` chama o serviço com Bearer do header**

```python
# _internal/mcp/test_server.py
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from mcp.server.fastmcp import FastMCP

from multi_agent.entity import AgentResponse
from multi_agent.exception import UnitMismatchException
from _internal.mcp.server import build_mcp, _authorization_from_headers


def test_ask_zera_description_names_the_four_specialists():
    service = MagicMock()
    mcp = build_mcp(service)
    tool = mcp._tool_manager.get_tool("ask_zera")
    text = (tool.description or "").lower()
    assert "faq" in text
    assert "inventory" in text
    assert "time-to-failure" in text or "predict" in text
    assert "disposal" in text or "report" in text
    assert "do not call" in text or "only when" in text


@pytest.mark.asyncio
async def test_ask_zera_forwards_ids_and_bearer():
    service = MagicMock()
    service.process_message = AsyncMock(return_value=AgentResponse(content="ok", agent_trace=["faq"]))
    mcp = build_mcp(service)
    uid, tid, unit = uuid4(), uuid4(), uuid4()
    result = await mcp.call_tool(
        "ask_zera",
        {
            "content": "O que é o Zera?",
            "user_id": str(uid),
            "thread_id": str(tid),
            "unit_id": str(unit),
        },
        extra={"headers": {"authorization": "Bearer test-token"}},
    )
    # Se call_tool/extra não existir nesta versão do SDK, o teste deve invocar
    # a coroutine registrada da tool com um Context fake — ajustar ao API real
    # do pacote instalado na Task 1, sem mudar o contrato ask_zera.
    service.process_message.assert_awaited_once()
    args = service.process_message.await_args.args
    assert args[0] == "O que é o Zera?"
    assert str(args[1]) == str(uid)
    assert str(args[2]) == str(tid)
    assert str(args[3]) == str(unit)
    assert args[4] == "Bearer test-token"


@pytest.mark.asyncio
async def test_ask_zera_without_authorization_raises():
    with pytest.raises(ValueError, match="Authorization"):
        _authorization_from_headers({})


@pytest.mark.asyncio
async def test_ask_zera_unit_mismatch_is_not_swallowed():
    service = MagicMock()
    service.process_message = AsyncMock(side_effect=UnitMismatchException("nope"))
    from _internal.mcp.server import ask_zera_impl

    with pytest.raises(UnitMismatchException):
        await ask_zera_impl(
            service,
            content="x",
            user_id=str(uuid4()),
            thread_id=str(uuid4()),
            unit_id=str(uuid4()),
            authorization="Bearer t",
        )
```

A API `mcp.call_tool(..., extra=headers)` varia. **Contrato estável para o implementador:** extraia `ask_zera_impl` / `create_disposal_report_impl` testáveis sem o SDK; o `@mcp.tool` só adapta Context → headers.

- [ ] **Step 2: Rodar o teste e ver falha de import**

Run: `pytest _internal/mcp/test_server.py -v`

Expected: FAIL (`ModuleNotFoundError: _internal.mcp.server` ou `build_mcp` undefined)

- [ ] **Step 3: Implementação mínima**

```python
# _internal/mcp/server.py
from uuid import UUID

from mcp.server.fastmcp import FastMCP

from multi_agent.entity import AgentResponse
from multi_agent.multi_agent import IMultiAgentService

ASK_ZERA_DESCRIPTION = """Ask the Zera multi-agent assistant (guardrails + orchestrator + specialists).
Use only when the user goal matches a Zera specialist:
(1) FAQ about the Zera platform,
(2) factual inventory already stored (item, batch, battery, warranty, hazardous checklist),
(3) predicted time-to-failure for equipment,
(4) disposal report text/PDF.
Do not call for general chat, coding, or topics outside those four. The orchestrator will still refuse off-topic requests, but skipping the call is cheaper and clearer.
Requires Authorization Bearer (same JWT as POST /api/v1/multi-agent/process-message) on the HTTP request to this MCP server.
"""


def _authorization_from_headers(headers: dict[str, str]) -> str:
    raw = headers.get("authorization") or headers.get("Authorization")
    if not raw:
        raise ValueError("Authorization Bearer header is required")
    return raw


async def ask_zera_impl(
    service: IMultiAgentService,
    *,
    content: str,
    user_id: str,
    thread_id: str,
    unit_id: str,
    authorization: str,
) -> dict:
    response: AgentResponse = await service.process_message(
        content, UUID(user_id), UUID(thread_id), UUID(unit_id), authorization
    )
    return response.model_dump(mode="json")


async def create_disposal_report_impl(
    service: IMultiAgentService,
    *,
    user_id: str,
    disposal_id: str,
) -> dict:
    url = await service.create_disposal_report(UUID(user_id), disposal_id)
    return {"report_url": url}


def build_mcp(service: IMultiAgentService) -> FastMCP:
    mcp = FastMCP("zera")

    @mcp.tool(name="ask_zera", description=ASK_ZERA_DESCRIPTION)
    async def ask_zera(
        content: str,
        user_id: str,
        thread_id: str,
        unit_id: str,
    ) -> dict:
        # FastMCP Context: get_http_headers() if available; else request_context.
        from mcp.server.fastmcp import Context
        ctx: Context
        try:
            from mcp.server.fastmcp import get_context
            ctx = get_context()
            headers = dict(getattr(ctx, "request_context").request.headers)
        except Exception:
            headers = {}
        authorization = _authorization_from_headers(headers)
        return await ask_zera_impl(
            service,
            content=content,
            user_id=user_id,
            thread_id=thread_id,
            unit_id=unit_id,
            authorization=authorization,
        )

    @mcp.tool(
        name="create_disposal_report",
        description="Generate or return the stored PDF URL for one disposal_id. Use only when the user wants the disposal report PDF, not chat.",
    )
    async def create_disposal_report(user_id: str, disposal_id: str) -> dict:
        return await create_disposal_report_impl(
            service, user_id=user_id, disposal_id=disposal_id
        )

    return mcp
```

Ajustar o jeito de ler headers ao SDK instalado (método oficial `Context` da versão). Os testes de `ask_zera_impl` e `_authorization_from_headers` não dependem disso.

- [ ] **Step 4: Testes passam**

Run: `pytest _internal/mcp/test_server.py -v`

Expected: PASS (depois de alinhar o teste de `call_tool` ao impl extraído)

- [ ] **Step 5: Commit**

```bash
git add _internal/mcp/
git commit -m "$(cat <<'EOF'
feat: add Zera MCP tools over process_message

EOF
)"
```

---

### Task 3: Montar `/mcp` no FastAPI

**Files:**
- Modify: `_internal/api/router.py`
- Create: `_internal/api/test_mcp_mount.py`
- Modify: `app/api/main.py` only if `BuildAPI` precisar do lifespan no `FastAPI(...)` — preferir fazer tudo em `BuildAPI`.

**Interfaces:**
- Consumes: `build_mcp(service).streamable_http_app()`
- Produces: host em `http://{APP_HOST}:{APP_PORT}/mcp` (Streamable HTTP)

O lifespan do **app host** deve `async with mcp.session_manager.run()`. Chamar `streamable_http_app()` **antes** de usar `session_manager`. Starlette não corre lifespan de app montado.

- [ ] **Step 1: Teste de mount**

```python
# _internal/api/test_mcp_mount.py
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from _internal.api.router import RouterAPI
from config.environments import Environments
from logger.logger import Logger


def test_mcp_path_is_not_404():
    envs = Environments()
    router = RouterAPI(envs, Logger())
    router.BuildAPI(MagicMock())
    client = TestClient(router._app)
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response.status_code != 404
```

- [ ] **Step 2: pytest — FAIL 404**

Run: `pytest _internal/api/test_mcp_mount.py -v`

Expected: FAIL `assert 404 != 404` ou AttributeError `_app`

- [ ] **Step 3: Mount + lifespan**

Em `BuildAPI`, depois de criar `self._app`:

```python
import contextlib
from _internal.mcp.server import build_mcp

mcp = build_mcp(multi_agent_service)
mcp_app = mcp.streamable_http_app()

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield

self._app = FastAPI(lifespan=lifespan)
self._app.mount("/mcp", mcp_app)
```

`FastAPI()` hoje é criado sem lifespan — unificar num único construtor. Health e `/api/v1` continuam iguais. Trailing slash: montar de forma que o cliente use `https://host/mcp` (sem duplicar `/mcp/mcp` — testar o path real do SDK; se o app interno já é `/mcp`, montar em `/` só o sub-app ou montar `""` conforme doc `run/asgi.md`).

Regra: o URL público documentado é `{origin}/mcp`. Ajustar `Mount` para isso.

- [ ] **Step 4: Testes**

Run: `pytest _internal/api/test_mcp_mount.py _internal/api/test_multi_agent_handlers.py _internal/mcp/test_server.py -v`

Expected: PASS; REST dos handlers inalterado.

- [ ] **Step 5: Commit**

```bash
git add _internal/api/router.py _internal/api/test_mcp_mount.py app/api/main.py
git commit -m "$(cat <<'EOF'
feat: mount Streamable HTTP MCP at /mcp

EOF
)"
```

---

### Task 4: Plugin ChatGPT (pacote + skill)

**Files:**
- Create: `plugin/plugin.json`
- Create: `plugin/mcp.json`
- Create: `plugin/skills/zera/SKILL.md`

O plugin **não** reimplementa o grafo. Aponta para o MCP remoto. `url` em `mcp.json` usa o host de produção quando existir; para o repo, placeholder `https://REPLACE_WITH_PUBLIC_HTTPS/mcp`.

- [ ] **Step 1: Manifests**

`plugin/plugin.json`:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "zera",
  "version": "0.1.0",
  "description": "Zera specialist assistant: platform FAQ, inventory facts, time-to-failure, disposal reports. Not a general chatbot.",
  "keywords": ["zera", "inventory", "faq", "predictive-maintenance", "disposal"]
}
```

`plugin/mcp.json`:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "zera": {
      "type": "streamable-http",
      "url": "https://REPLACE_WITH_PUBLIC_HTTPS/mcp"
    }
  }
}
```

`plugin/skills/zera/SKILL.md`:

```markdown
---
name: zera
description: Call Zera tools only when the user goal matches FAQ, inventory, time-to-failure, or disposal reports.
---

You are helping a Zera worker. Prefer the bundled Zera MCP tools over guessing inventory, failure time, or platform policy.

Call `ask_zera` only if the goal is clearly one of:
1. FAQ about how the Zera platform works
2. Facts already in inventory (item, lot, battery, warranty, hazardous materials checklist)
3. Predicted remaining useful life / time-to-failure of equipment
4. Disposal report (text via chat, PDF via `create_disposal_report`)

If the user is coding, chatting generally, or asking something outside those four, do not call Zera. Answer with the host model or say Zera does not cover that.

Call `login` once with the worker's Zera email and password (admin-core credentials). Do not echo the password afterwards. Then call `ask_zera` with `content` and a stable `thread_id`. This plugin does not expose PDF generation (`POST /reports`).
```

- [ ] **Step 2: Conferir arquivos**

Run: `python -c "import json,pathlib; json.load(open('plugin/plugin.json')); json.load(open('plugin/mcp.json')); print(pathlib.Path('plugin/skills/zera/SKILL.md').read_text())"`

Expected: JSON válido; skill contém "only if" / four specialists.

- [ ] **Step 3: Commit**

```bash
git add plugin/
git commit -m "$(cat <<'EOF'
feat: add ChatGPT plugin package pointing at Zera MCP

EOF
)"
```

---

### Task 5: Docs de contrato e overview

**Files:**
- Modify: `docs/this-project-overview.md` (nova decisão técnica 6)
- Modify: `docs/contrato-api-ms-artificial-intelligence-core.md` (seção MCP)

- [ ] **Step 1: Escrever**

Decisão 6 (overview): fachada MCP em `/mcp` para hosts (ChatGPT, Claude, Cursor); plugin em `plugin/` é manifest+skill, não segundo grafo; tools não são nós LangGraph; auth = mesmo Bearer + ids do REST.

Contrato: `POST /mcp` Streamable HTTP; tools `ask_zera`, `create_disposal_report`; header `Authorization`; argumentos UUID iguais ao REST. Fora de escopo das 4 intenções: o host **não deve** chamar; se chamar, o grafo bloqueia/sugere como hoje.

- [ ] **Step 2: Commit**

```bash
git add docs/this-project-overview.md docs/contrato-api-ms-artificial-intelligence-core.md
git commit -m "$(cat <<'EOF'
docs: document MCP facade and ChatGPT plugin

EOF
)"
```

---

### Task 6: Verificação local

- [ ] **Step 1:** `make test` (unitários, exclui integration). Expected: PASS.
- [ ] **Step 2 (manual, não CI):** com a API no ar, MCP Inspector `npx @modelcontextprotocol/inspector@latest` em `http://127.0.0.1:$APP_PORT/mcp`. Sem Bearer, tool falha. Com Bearer de login admin-core + UUIDs reais, FAQ curta responde.
- [ ] **Step 3 (manual ChatGPT):** Developer mode → Security and login; [chatgpt.com/plugins](https://chatgpt.com/plugins) → **+** → URL público HTTPS `/mcp` (GCP). Ligar o plugin; perguntar algo fora de escopo e confirmar que o modelo **não** chama (skill); perguntar FAQ Zera e ver `ask_zera`.

Fora desta entrega: OAuth CIMD, A2A, publicar no diretório público, MCP do inventory direto.

---

## Spec coverage

| Requisito | Task |
| --- | --- |
| MCP Streamable HTTP no serviço GCP/FastAPI | 1, 3 |
| Só `ask_zera` + `login`; sem PDF MCP | 2 |
| Login proxy admin-core; JWT só no servidor | 2 |
| Copy “só especialista” | 2, 4 |
| Plugin ChatGPT (manifest + mcp.json + skill) | 4 |
| Docs | 5 |
| Sem A2A / sem inventory MCP público | constraints |

## Self-review

- Sem TBD: path `/mcp` e nomes de tool fechados; se o SDK mudar `Context`, a Task 2 manda extrair `*_impl`.
- `ask_zera_impl` signature is the stable contract across tests and tools.
- Plugin URL placeholder is intentional until the public hostname exists.
