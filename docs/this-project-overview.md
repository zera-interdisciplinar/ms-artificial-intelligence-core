# overview desse repositório

## objetivo

O objetivo desse repositório é iniciar uma api que centrealize todos os fluxos do sistema multi-agentes. Ele contem a estrutura de pastas e arquivos que serão utilizados para o desenvolvimento do sistema multi-agentes, incluindo a implementação de agentes, repositórios, serviços e controladores. Utiliza banco de dados MongoDB para armazenamento de dados e FastAPI para criação de endpoints. O repositório também inclui testes unitários e integração contínua para garantir a qualidade do código.

## agentes do sistema

### Guardrail_in
Agente do guardrail de entrada, responsável por iniciar o fluxo de execução do sistema multi-agentes. Ele recebe o Estado inicial com a pergunta do usuário e identifica prompt injections, informações sensíveis e outras ameaças de segurança, garantindo que apenas informações SEGURAS e RELEVANTES sejam processadas pelos agentes subsequentes. O GuardrailIn também pode realizar pré-processamento de dados, como normalização e validação, antes de encaminhar a solicitação para os próximos agentes. Caso a entrada do usuário seja considerada insegura, o GuardrailIn pode interromper o fluxo e retornar uma mensagem de erro apropriada (default).

### orchestrator
Agente responsável por coordenar a execução dos agentes do sistema multi-agentes. Ele recebe o Estado inicial com a pergunta do usuário (já com PII removidos) e extraí a intenção do usuário, identificando o agente mais adequado para processar a solicitação. O Orchestrator também pode gerenciar a comunicação entre os agentes, garantindo que as informações sejam transmitidas de forma eficiente e segura.

### faq_agent
Agente responsável por responder perguntas frequentes relacionados ao sistema zera como um todo. Ele recebe o Estado inicial com a pergunta do usuário (já com PII removidos) e faz uma busca vetorial em um pdf interno que contem informações sobre o sistema zera, retornando as respostas mais relevantes para o usuário utilizando FAISS.

### report_agent 
Agente responsável por gerar relatórios sobre a empresa utilizadora. Ele recebe o Estado inicial com a pergunta do usuário (já com PII removidos), incluindo os itens selecionados para descarte, e gera textos para geração de relatórios, de acordo com as técnicas apresentadas no prompt. O modelo retorna um documento com texto gerado para o header, body e footer do relatório, que será posteriormente formatado em PDF pelo serviço de geração de relatórios.

### predict_model
Agente responsável por realizar uma integração com um outro repositório interno que tem um modelo de predição de tempo de vida útil de equipamentos eletrônicos. Ele recebe o Estado inicial com a pergunta do usuário (já com PII removidos), incluindo os itens selecionados para descarte, e faz uma chamada para o modelo de predição, retornando as informações de tempo de vida útil estimado para cada item. O modelo de predição utiliza regressão linear para estimar o tempo de vida útil dos equipamentos, com base em dados históricos e características dos itens. Por ser um modelo simples, o predict_model será usado para ajustar a resposta, verificando se é coerente com o que o modelo de predição retornou, e caso não seja, ele ajusta a resposta. Haverá intruções desse ajuste no prompt do predict_model, para que ele saiba como ajustar a resposta de acordo com o que o modelo de predição retornou.

### formatter_agent
Agente responsável por formatar a resposta final do sistema de uma forma amigavel para o usuário. Ele recebe o Estado já modificado durante o fluxo, e constroi a resposta final de forma organizada e padronizada.

### judge_agent
Agente responsável por julgar a resposta final do sistema, verificando se ela está coerente com o que foi solicitado pelo usuário. Ele recebe o Estado já modificado durante o fluxo, e verifica se a resposta final está de acordo com as instruções do prompt, e se ela é coerente com as informações fornecidas pelo usuário. Caso a resposta final não esteja coerente, o Judge_agent pode solicitar ajustes na resposta final, ou retornar uma mensagem de erro apropriada.

### guardrail_out
Agente do guardrail de saída, responsável por verificar a resposta final do sistema antes de enviá-la para o usuário. Ele recebe o Estado já modificado durante o fluxo, e verifica se a resposta final está de acordo com as instruções do prompt, e se a resposta vai contra alguma diretriz de segurança. Caso a resposta final não esteja de acordo com as instruções do prompt, ou se ela vai contra alguma diretriz de segurança, o GuardrailOut pode solicitar ajustes na resposta final, ou retornar uma mensagem de erro apropriada.


# Decisões tecnicas

1- judge_agent, formatter_agent, faq_agent e report_agent eram adicionados ao grafo como nós crus (create_agent(...) direto), assim como orchestrator e predict_model. Esses nós só devolvem {"messages": [...]}, nunca escrevem nas chaves próprias do estado (formatted_response, approved, discrepancy, answer, sources, report_header/body/footer). Criamos wrappers (make_judge_func, make_formatter_func, make_faq_func, make_report_func) que fazem o parse do JSON da última mensagem do agente e projetam isso de volta no estado, seguindo o mesmo padrão já usado em Guardrail.guardrail_in_func/guardrail_out_func.

2- no payload enviado para judge_agent (e nos demais agentes que recebem um JSON serializado como turno de entrada, ex: guardrail_out_func), usamos HumanMessage em vez de SystemMessage. Essa lista de mensagens é local à chamada .invoke() do sub-agente (não é state["messages"]), então não suja o histórico persistido da conversa. Preferimos HumanMessage porque create_agent já injeta o system_prompt do módulo como a única mensagem de sistema do sub-agente; a maioria dos provedores (incluindo Gemini) espera exatamente uma instrução de sistema mais turnos human/AI, então empilhar uma segunda SystemMessage com o payload é frágil (pode ser rejeitado ou descartado dependendo do provedor). (AI)

3- integrações com sistemas externos ao repositório (ms-inventory e ms-adm-core, para obter contexto de empresas, itens, etc.) serão feitas via MCP, e não via tool local com chamada de API/SDK direta. Critério usado: MCP compensa quando (a) o LLM precisa decidir em runtime se/quando chamar a capacidade E (b) ela pertence a outro repositório com ciclo de deploy próprio, cuja interface pode evoluir sem coordenação com este repo — nesse caso o cliente MCP descobre as tools em runtime (tools/list), então mudanças do outro lado não exigem alteração de código nem redeploy aqui. Tools locais (ex: retrieve_context do faq_agent) continuam sendo a escolha certa quando a capacidade é interna a este repositório e só um agente a usa, sem fronteira de sistema a desacoplar.

A decisão do predict_model segue o mesmo critério: mesmo tendo um único consumidor (este repo), o modelo preditivo vive em outro repositório e deve ganhar novas features/atualizações ao longo do tempo — o ponto decisivo não é reuso por múltiplos consumidores, e sim a volatilidade da interface do outro lado. Como o client MCP (MultiServerMCPClient, via langchain-mcp-adapters) já existirá no repo para ms-inventory/ms-adm-core, adicionar o predict_model como mais um servidor tem custo marginal baixo, evitando inconsistência de ter duas integrações cross-repo em padrões diferentes. (AI)