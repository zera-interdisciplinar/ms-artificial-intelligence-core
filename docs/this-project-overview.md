# Agentes deste serviço

Detalhe do grafo, alinhado a [8.2 Grafo e agentes](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/64913409) e [8.1 Arquitetura hexagonal](https://zerainterdisciplinar.atlassian.net/wiki/spaces/Backend/pages/64880641). O panorama da plataforma está em [zera-overview.md](zera-overview.md). O turno HTTP está em [contrato-api-ms-artificial-intelligence-core.md](contrato-api-ms-artificial-intelligence-core.md).

Entrada: `guardrail_in`. Saída: `guardrail_out` → fim.

```text
guardrail_in —bloqueado→ fim
            —ok→ orchestrator
                  —faq→ faq → formatter
                  —report→ report → formatter
                  —predict→ predict_model → formatter
                  —inventory→ inventory —opcional→ predict_model → formatter
                                          —senão→ formatter
                  —fora de escopo→ guardrail_out
formatter → judge —reprovado→ orchestrator
                  —aprovado→ guardrail_out → fim
```

Fonte: `multi_agent/graph.py`.

## Agentes

| Nome no grafo | Papel |
|---|---|
| `guardrail_in` | Injection, PII, off-topic. Inseguro: encerra com mensagem default. Produz `current_request` sanitizado. |
| `orchestrator` | Intenção → um especialista. Sem match: não força; vai ao `guardrail_out` com sugestões. |
| `faq` | Busca vetorial Qdrant no PDF da plataforma. Devolve `answer`, `sources`, `redirect_to`. |
| `inventory_agent` | Fatos já existentes no ms-inventory via MCP (detalhe, lote, checklist, garantia, ciclo de vida). Pode encaminhar para predict. |
| `predict_model` | MCP do preditor de meses até falha. Ajusta coerência no prompt; não inventa campos obrigatórios ausentes (`estimated_remaining_months: null`). |
| `report` | Texto header/body/footer para relatório. O chat não gera PDF. |
| `formatter` | Resposta amigável a partir do estado estruturado. |
| `judge` | Coerência com o pedido. Reprova → orchestrator de novo. |
| `guardrail_out` | Última checagem de segurança da resposta. |

## Quem recebe o quê

| Nó | Entrada |
|---|---|
| `guardrail_in` | `state["messages"][-1]` (bruto); produz `current_request` sem PII |
| orchestrator e especialistas | `request_with_history(current_request, messages, user_preferences)` |
| `judge` | só `current_request` |

O payload JSON de um sub-agente vai em `HumanMessage`. A lista é local ao `.ainvoke()` e não entra no histórico persistido. Há uma única `SystemMessage`, o prompt do módulo.

Agentes crus (`create_agent`) devolvem só `{"messages": [...]}`. Os wrappers parseiam o JSON da última mensagem e escrevem as chaves do estado.

## agent_trace

Lista dos nós que rodaram, na ordem. Telemetria; não é UI de produto. Valores: `guardrail_in`, `orchestrator`, `faq`, `report`, `predict_model`, `inventory_agent`, `formatter`, `judge`, `guardrail_out`.

As portas (`IMultiAgentService`, `IMultiAgentRepository`, `IUnitResolver`, `IStorageService`, `IPdfRenderer`) ficam em `multi_agent/multi_agent.py` e não importam adaptador. Os concretos são escolhidos em `app/api/composition.py`.
