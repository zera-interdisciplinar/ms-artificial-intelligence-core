# Fachada MCP

Alinhado a [8.6 Integrações MCP](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/64684055) e [8.4 Identidade, Redis e persistência](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/64684034).

Com `SELF_MCP_URL` definido, o mesmo processo da API monta o servidor MCP (HTTP streamable) depois das rotas `/health` e `/api/v1`. Vazio: a fachada não sobe. Ingress: `k8s/ingress-mcp.yaml` e `k8s/ingress-mcp-qa.yaml`. O OAuth do connector usa o mesmo host, atrás do Kong.

## Tool

Uma tool, `ask_zera`. O modelo não vê senha, `user_id` nem `unit_id`. O adaptador lê o Bearer, tira o `sub` e chama `process_message` com `unit_id` vazio: a unidade é a que o admin-core tem para esse usuário. PDF de descarte não é tool desta fachada.

Sem sessão, a fachada responde 401 e o connector segue para o login da plataforma.

## OAuth no Redis

Chave `mcp:oauth:{tipo}:{chave}`.

| Tipo | TTL |
|---|---|
| `client` | sem TTL |
| `pending` | 10 min, uso único |
| `code` | 60 s, uso único |
| `access` | `expiresIn` do admin-core |
| `refresh` | 30 dias |

O mesmo Redis guarda o checkpoint da conversa e o cache de unidade (`admin_core:unit:{user_id}`, 6 min, sem renovar no acerto). Um único cliente Redis, criado em `app/api/main.py`.
