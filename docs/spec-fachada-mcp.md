# Spec técnica — fachada MCP

O host (Claude e equivalentes com connector MCP) fala com um servidor MCP remoto. O adaptador autentica, traduz a tool e chama um método. Esse método chama o grafo que já existe.

A spec de produto (`spec-provedores-ia-externos.md`) descreve o problema, o escopo de uso e o que não pode vazar. Este documento fixa o desenho: uma tool, login pelo OAuth do connector, e a ACL como o método que o adaptador chama.

## Forma

Três faixas, de cima para baixo.

**Entrada.** O Claude cadastra a URL do servidor MCP. Sem sessão, o servidor responde 401 e o Claude abre a tela de login da plataforma. O Bearer fica no Claude. O modelo não vê senha nem token.

**Processamento.** O adaptador chama o método da ACL. O método chama `process_message`. O grafo segue como hoje: valida unidade, hidrata o fio, guardrail de entrada, orquestrador, um especialista, formatter, judge, guardrail de saída.

**Saída.** O método devolve `AgentResponse`. O adaptador entrega isso como resultado da tool.

## ACL

Um método, chamado pelo adaptador MCP. Ele não conhece tool nem `session_handle`.

Entrada já resolvida pelo adaptador:

| Campo | Origem |
| --- | --- |
| `content` | Texto da tool |
| `thread_id` | Fio pedido pelo cliente, ou um fio novo se o cliente não mandou |
| `user_id` | Bearer, nunca argumento livre do modelo |
| `unit_id` | Unidade que o admin-core atribui a esse usuário |
| `authorization` | Credencial de backend (`Bearer`) que o `process_message` já usa para falar com o admin-core |

O método chama `IMultiAgentService.process_message(content, user_id, thread_id, unit_id, authorization)` e devolve o `AgentResponse` (`content`, `blocked`, `blocked_reason`, `agent_trace`, `report_url`).

O app Zera continua chamando `process_message` pela API atual. A ACL é a porta do MCP. Não é um segundo grafo.

## Adaptador MCP

Traduz o protocolo, resolve a identidade, chama a ACL, traduz a resposta. Não escolhe especialista e não chama inventário, predição, FAQ nem relatório.

- Servidor MCP remoto (Streamable HTTP), uma tool: perguntar ao assistente. A descrição deixa explícito quando chamar: FAQ da plataforma, fato de inventário, tempo até falha, texto de relatório de descarte. Fora isso, o host não chama.
- Autenticação é OAuth do connector. Na primeira uso o servidor responde 401, o Claude abre a tela de login da plataforma e guarda o Bearer.
- A tool não recebe `session_handle`, e-mail, senha, `user_id` nem `unit_id`. Recebe o texto e o identificador do fio.
- O adaptador lê o Bearer da requisição, resolve usuário e unidade, chama a ACL.

O `login` e o `session_handle` do servidor MCP atual saem. A sessão deixa de ser um handle que volta para o modelo.

## Identidade

- O IdP continua sendo o da plataforma (`ms-administrative-core`). A fachada não guarda senha.
- `process_message` segue chamando `_validate_unit`: a unidade do token tem de ser a que o admin-core confirma. Divergência é recusa, não alargamento.
- Integrações internas (inventário, predição, admin) continuam com a chave de serviço do grafo, atrás do orquestrador. O Bearer do host não é encaminhado para esses MCPs.

Se o admin-core ainda só expõe login com e-mail e senha, o authorization server do OAuth fica no adaptador e troca esse login pelo token que o cliente guarda. O grafo não participa dessa troca.

## Grafo (inalterado)

`process_message` valida a unidade, hidrata o fio (cache em memória ou MongoDB: mensagens e preferências) e invoca o grafo compilado.

Ordem: guardrail de entrada (bloqueio encerra), orquestrador (fora de escopo vai para o guardrail de saída), um de FAQ (FAISS), inventário, predição ou relatório em texto. Inventário pode seguir para predição. Especialista vai para o formatter, depois o judge. Judge reprovado volta ao orquestrador. Aprovado vai para o guardrail de saída.

PDF de descarte não é operação desta fachada. Segue na API de relatório do app.

## Fora desta fachada

- Expor nó interno como tool.
- Apontar o host para o MCP de inventário ou de predição.
- Senha ou token no texto que o modelo vê.
- Protocolo agente-a-agente (A2A).
- Framework de ACL, interface genérica para protocolo futuro, ou mapeamento por especialista.
