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