# Integração MCP — sdk-ml-failure-predictor (Time-to-Failure Predictor)

> Protocolo alinhado entre 3 sessões: ms-artificial-intelligence-core (este repo), infra-gtw-kong e sdk-ml-failure-predictor. Registrado aqui para não se perder entre sessões de IA.
>
> **Status neste repo:** implementado em `multi_agent/service.py` (`MultiAgentService._fetch_predict_model_tools`/`_fetch_predict_model_context` + wiring do `predict_model_agent` em `setup()`), usando `MultiServerMCPClient` (`langchain-mcp-adapters`). Falta apenas o valor real de `PREDICT_MODEL_MCP_URL` (host do gateway Kong), que ainda não foi publicado/confirmado — ver Pendências.

## O que é

Servidor MCP externo (repositório `sdk-ml-failure-predictor`) que expõe um modelo PyTorch de regressão, prevendo em quantos meses um equipamento de TI vai quebrar.

## Transporte

- HTTP (`streamable-http`), `json_response=True` (sem SSE/streaming — request/response comum).
- `stateless_http=True` (sem sessão fixa entre chamadas).
- Path fixo do protocolo MCP: `/mcp`.

## Roteamento (Kong)

- Ingress externo em `/predictor` (prod) e `/qa/predictor` (qa).
- Plugin `mcp-path-rewrite` (request-transformer) reescreve o URI final sempre pra `/mcp`.
- Aponta pro Service Kubernetes `ml-failure-predictor:8000`, namespaces `qa`/`production`.

## Autenticação

**NENHUMA por enquanto** (decisão do usuário do lado do sdk-ml-failure-predictor). Sem api-key, sem mTLS, sem JWT. Isso é temporário — TODO reintroduzir key-auth quando houver processo de rotação de chave definido. Não codificar nenhum header de auth no client até isso mudar.

## Tool exposta: `predict_time_to_failure`

Input (todos obrigatórios, batem com o schema pydantic `DeviceRecord` do lado deles):

| campo | tipo | exemplo |
|---|---|---|
| `category` | str | "notebook", "celular", "projetor", "monitor", "tablet", "desktop", "impressora", "roteador" |
| `manufacturer` | str | "Dell", "Apple", "Samsung" |
| `model` | str | "Latitude 5420" (nome comercial do modelo) |
| `climateZone` | str | "TROPICAL", "ARID", "TEMPERATE", "COLD" |
| `usageIntensity` | int | escala 1-10 |
| `manufacturingDate` | int | ano de fabricação, ex: 2022 |
| `acquiredAt` | str | data ISO de aquisição, ex: "2023-01-15" |

Output: `float` único — `time_to_failure_months` (meses estimados até a falha).

- **1 device por chamada** — sem batch/lote implementado do lado deles ainda. Se precisarmos prever vários itens, chamar a tool várias vezes (é stateless).
- Sem side effects, sem estado entre chamadas.
- `time_to_failure_months` mapeia direto para o campo interno `estimated_remaining_months` do nosso `predict_model` agent (ver `multi_agent/prompt/predict_model.py`). Os campos `adjusted`/`adjustment_reason` continuam sendo pós-processamento nosso, não vêm da tool.
- **Correção (2026-08-16, confirmado direto no código pela sessão sdk-ml-failure-predictor-9d):** `climateZone` tem **4** valores válidos, não 3 — o protocolo anterior tinha esquecido `TEMPERATE`.
- **`category`/`manufacturer`/`model`/`climateZone` não são enums validados no schema pydantic — só o tipo é validado.** A tool aceita qualquer string nesses campos e qualquer int em `usageIntensity`, sem checar domínio. Um valor fora do vocabulário de treino (8 categorias, 4 zonas climáticas, 40 fabricantes, 298 modelos) ou fora de 1-10 em `usageIntensity` **não gera erro** — vira `<UNK>` (categoria/fabricante/modelo/clima) ou é usado numericamente sem clamp (usageIntensity), e a tool devolve um número com aparência válida mas sem sentido (testado com `usageIntensity: 999` + `climateZone` inventado → 487 meses). Só campo **ausente** ou de **tipo errado** gera erro real (`ToolError` do MCP, ex.: erro de validação pydantic do `DeviceRecord`).
- Por isso o client deste repo (prompt do `predict_model` agent) valida/faz clamp de `category`, `climateZone` e `usageIntensity` **antes** de chamar a tool, em vez de confiar na tool para rejeitar valores ruins.
- **Regras de ajuste do `predict_model` agent** (seção dedicada em `multi_agent/prompt/predict_model.py`, `_schema_definition`/`ADJUSTMENT_RULES_DEFINITION`): (1) `usageIntensity` fora de 1-10 é clampado pro limite mais próximo antes da chamada; (2) campo obrigatório ausente/indeterminável (`category`, `climateZone`, `manufacturingDate`, `acquiredAt`) impede a chamada e vira `estimated_remaining_months: null`; (3) `time_to_failure_months` negativo retornado pela tool é clampado pra 0. Fora dessas três situações, `adjusted` deve ser `false`.
- **Novas tools no MCP server (2026-08-23, implementadas pela sessão ml-failure-predictor a pedido desta sessão):** `list_valid_categories()` e `list_valid_climate_zones()`, expostas ao lado de `predict_time_to_failure` no mesmo servidor. Ambas leem direto do vocabulário treinado (`checkpoints/feature_encoder.json`, via `TTFPredictor.encoder`), sem lista hardcoded do lado deles, e excluem o token interno `<UNK>` do retorno. Existem justamente para o client não precisar manter uma cópia manual do domínio de `category`/`climateZone` (que já ficou desatualizada uma vez — ver correção do `TEMPERATE` acima).
  - Este repo consome as duas no boot (`MultiAgentService._fetch_predict_model_context()`, `multi_agent/service.py`) pra montar o prompt do `predict_model` agent dinamicamente (`build_predict_model_system_prompt(categories, climate_zones)` em `multi_agent/prompt/predict_model.py`), em vez de hardcode. Essas duas tools são consumidas só no boot — não são passadas pro `predict_model_agent` (que só recebe `predict_time_to_failure`).
  - `manufacturer`/`model` continuam texto livre no prompt (não têm tool de listagem — são 40/298 valores, esperados a crescer). **Confirmado com a sessão ml-failure-predictor (2026-08-23):** o `<UNK>` desses dois campos NÃO é uma "média genérica aprendida" como o texto anterior deste doc sugeria — o embedding do índice UNK nunca é atualizado por gradiente (`FeatureEncoder.fit()` constrói o vocab a partir dos próprios valores de treino, então nenhum registro real usa o índice 0; não existe técnica de UNK augmentation). Na prática, um `manufacturer`/`model` desconhecido passa um vetor essencialmente aleatório pra rede — o resultado tende a ficar numa faixa plausível (os outros ~5 termos concatenados, incluindo `category`/`climateZone`/numéricos, seguem informativos), mas não é o fallback previsível que "cai pra média" sugere. Mesmo assim, a recomendação de manter texto livre (sem tool de listagem) permanece — 298 modelos numa lista não compensa —, mas o risco real é "confiança indevida" nesses dois campos, não "silêncio gracioso". Se algum dia quiserem mitigar, a correção é do lado deles (treinar com UNK augmentation), não do lado deste client.
  - **Sem validação cruzada categoria+fabricante+modelo** (confirmado, `src/data/features.py`, `FeatureEncoder.encode_categorical`): cada coluna categórica (`category`, `manufacturer`, `model`, `climateZone`) é resolvida de forma independente contra seu próprio vocabulário. Uma combinação nunca vista no treino (ex.: `manufacturer="Dell"` + `category="impressora"`, que não existe em `MANUFACTURER_MODELS` do `synthetic_generator.py`) é aceita normalmente — cada valor resolve pro seu índice real isoladamente, sem nenhum guard-rail de combinação. Não é diferente (estruturalmente) de qualquer combinação rara pouco representada no treino.
  - `category`/`climateZone` são domínios estáveis no momento (sem plano de expansão confirmado pela sessão sdk-ml-failure-predictor), mas a fonte de verdade passou a ser essas tools, não mais um valor copiado à mão neste doc/prompt.

## Client (implementado neste repo)

`MultiServerMCPClient` (`langchain-mcp-adapters`, adicionado a `requirements.txt`), transporte `streamable_http`, sem `headers` de auth por ora (ver seção Autenticação). Em `multi_agent/service.py`:

- `MultiAgentService._fetch_predict_model_tools()` (método async) monta o client com um único server `predict_model` apontando para `self.envs.PREDICT_MODEL_MCP_URL` e chama `client.get_tools()` — retorna as 3 tools do servidor (`predict_time_to_failure`, `list_valid_categories`, `list_valid_climate_zones`).
- `MultiAgentService._fetch_predict_model_context()` (método async) usa o fetch acima, invoca `list_valid_categories`/`list_valid_climate_zones` uma vez (`.ainvoke({})`) pra obter os domínios válidos, e devolve só `predict_time_to_failure` como tool do agente — as outras duas são consumidas apenas no boot, não em runtime pelo `predict_model_agent`.
- `setup()` (síncrono, chamado uma vez no boot em `app/api/main.py`) roda esse fetch via `asyncio.run(...)` e usa `categories`/`climate_zones` pra montar o system prompt via `build_predict_model_system_prompt(...)`, passando também a tool `predict_time_to_failure` pro `create_agent(...)` do `predict_model_agent` — mesmo padrão usado pelo `faq_agent` com sua tool local `retrieve_context`.
- Nova env var `PREDICT_MODEL_MCP_URL` em `config/environments.py` (sem default, igual `GEMINI_API_KEY`).
- Testes: `multi_agent/test_service.py` (`TestSetup`, `TestFetchPredictModelTools`, `TestFetchPredictModelContext`) mockam `MultiServerMCPClient` — nenhuma chamada de rede real acontece em teste.
- `multi_agent/prompt/predict_model.py`: `PREDICT_MODEL_SYSTEM_PROMPT_FINAL` (string estática) foi substituído por `build_predict_model_system_prompt(categories, climate_zones)` (função), que monta o schema `DeviceRecord` com os valores de `category`/`climateZone` recebidos em runtime (não mais hardcoded) — o range 1-10 de `usageIntensity` continua fixo no texto. O prompt instrui o agente a validar/fazer clamp desses campos antes de chamar a tool (já que ela não valida domínio — ver seção Tool exposta acima) e a NUNCA inventar `category`/`climateZone`/`manufacturingDate`/`acquiredAt` ausentes — nesses casos o item entra em `predictions` com `estimated_remaining_months: null` e `adjustment_reason` explicando o campo faltante, em vez de chamar a tool com dado fabricado.
- Downstream do `predict_model` também foi alinhado ao novo formato de `predictions` (incluindo o caso `estimated_remaining_months: null`):
  - `multi_agent/prompt/formatter_agent.py` — instrução explícita pra não omitir nem inventar número quando `estimated_remaining_months` for `null`; deve explicar o motivo (`adjustment_reason`) em linguagem natural. Shots trocados de categorias inválidas ("Bateria", que não existe nas 8 categorias do modelo) para categorias reais, e novo shot cobrindo o caso `null`.
  - `multi_agent/prompt/judge_agent.py` — regra explícita de que uma estimativa `null` com motivo declarado NÃO é uma omissão (não deve ser reprovada por isso); só reprovar se o item foi omitido por completo ou se um número foi apresentado sem bater com o estado. Mesma troca de exemplo de categoria inválida + novo shot aprovando o caso `null`.

## Pendências em aberto (não bloqueiam o código acima, mas faltam pra rodar ponta a ponta)

1. Porta 8000 no cluster já verificada — sem conflito.
2. Imagem Docker do sdk-ml-failure-predictor ainda não publicada em registry real (workflow de deploy existe, com placeholders de projeto GCP a preencher).
3. `PREDICT_MODEL_MCP_URL` ainda não tem um valor real — host do gateway Kong (ingress `/predictor` prod / `/qa/predictor` qa) não foi confirmado nem adicionado a `.env`/`k8s/deployment*.yaml` neste round (deixado em branco em `.env` local; k8s manifests não tocados, pra não fabricar um hostname).
4. Nenhum dos 3 repos commitou nada relacionado a essa integração ainda — cada repo decide isso com seu próprio usuário, não por instrução cross-sessão. Este repo também não foi commitado (instrução explícita do usuário: nunca commitar/dar push).

Qualquer mudança nesse contrato (novos campos, batch, auth) precisa ser re-alinhada nos 3 antes de qualquer lado implementar.
