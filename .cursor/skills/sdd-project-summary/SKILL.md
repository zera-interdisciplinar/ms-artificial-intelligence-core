---
name: sdd-project-summary
description: Gera um resumo do projeto no padrão Spec-Driven Development (SDD) — compara o que a spec/contexto do projeto define contra o que já está implementado no código, e lista próximos passos e observações. Use sempre que o usuário pedir um "resumo do projeto", "status do projeto", "onde estamos", "o que falta fazer", "raio-x do projeto", ou perguntar de forma geral como anda o andamento do trabalho, mesmo sem citar "SDD" explicitamente. É um relatório somente leitura: nunca faz alterações no projeto por conta própria — qualquer mudança sugerida só pode ser executada mediante aprovação explícita e imediata do usuário, pedida no momento, nunca antecipada ou assumida de instruções passadas.
---

# Resumo de projeto no padrão SDD

Esta skill produz um retrato do projeto no estilo Spec-Driven Development:
o que a especificação (intenção, decisões, requisitos) diz que o projeto
deveria ter, o que já existe de fato no código, o que falta, e qualquer
inconsistência entre os dois. A ideia é dar ao usuário uma visão rápida de
"onde estamos vs. onde deveríamos estar" sem precisar reler o histórico
inteiro de decisões.

## Regra inegociável: isto é um relatório, não uma tarefa de execução

Esta skill **só observa e relata**. Ela nunca cria, edita, apaga ou corrige
arquivos, nunca roda `git commit`/`git push`, e nunca "aproveita" para
resolver algo que encontrou pendente ou inconsistente — mesmo que a correção
pareça trivial ou óbvia.

**Por quê**: o usuário pediu explicitamente que qualquer alteração no
projeto dependa da aprovação dele, dada no momento em que a mudança é
proposta — não de uma autorização genérica dada antes. Um resumo que já vem
com mudanças aplicadas deixa de ser um resumo confiável do estado real.

**Como aplicar**: ao final do resumo, se houver ações sugeridas (uma
implementação pendente, uma inconsistência para corrigir, um arquivo
desatualizado), liste-as na seção "Observações" como **propostas**, e
pergunte ao usuário se quer que alguma delas seja executada agora. Nunca
execute nenhuma antes dessa pergunta ser feita e respondida — inclusive
salvar o próprio resumo em arquivo (veja "Entrega do resultado" abaixo)
conta como alteração e depende da mesma aprovação.

## Passo 1: reunir as fontes

Antes de escrever o resumo, colete informação real — não invente nem
assuma a partir de memória de conversas anteriores, o estado do projeto
pode ter mudado.

1. **Spec/contexto do projeto** — procure um arquivo tipo `CONTEXT.md`,
   `SPEC.md`, `DESIGN.md`, `PLAN.md` ou similar na raiz do projeto. É a
   fonte principal do que o projeto *deveria* ter: objetivo, decisões
   metodológicas, arquitetura pretendida, features/requisitos definidos.
   Se não existir nenhum, use `README.md` e o histórico de commits como
   substituto, e diga isso explicitamente nas observações (a ausência de
   uma spec formal já é uma observação relevante).
2. **Estado real do código** — liste a estrutura de diretórios relevante
   (`src/`, `scripts/`, `tests/`, etc.) e confira quais arquivos previstos
   na spec já existem, quais estão vazios/stub, e quais têm implementação
   completa. Não confie só no nome do arquivo — abra os que forem centrais
   para confirmar se o conteúdo bate com o que a spec descreve.
3. **Git** — rode `git log --oneline -20` e `git status` para saber o que
   foi commitado recentemente e o que está em progresso/não commitado.
   Isso ajuda a diferenciar "implementado e estável" de "em andamento".
4. **Testes e dependências** — confira se existe suíte de testes
   (`tests/`) e se cobre as partes já implementadas; confira
   `requirements.txt`/`package.json`/etc. para ver se as dependências
   batem com o que a spec exige.

## Passo 2: montar o resumo

Use exatamente esta estrutura de 4 seções (nesta ordem). Escreva no mesmo
idioma que o usuário usou para pedir o resumo.

```markdown
# Resumo do projeto — <nome do projeto>

## O que precisa ter (spec)
<Lista do que a spec/contexto do projeto define como necessário — objetivo,
decisões fechadas, componentes/arquivos previstos, requisitos não-funcionais
relevantes (ex: sem vazamento de dados, formato de saída, etc.). Cite a
fonte (ex: "CONTEXT.md, seção X") quando possível.>

## O que já tem (implementado)
<Para cada item da spec acima, diga se está: implementado e testado /
implementado mas sem teste / parcialmente implementado (stub) / ausente.
Baseie-se no que você realmente leu no código nesta rodada, não em memória.>

## Próximos passos
<O que falta para fechar a spec, na ordem que faz mais sentido implementar
primeiro. Se a spec já lista isso (ex: seção "Pendente"), confirme se ainda
é válido ou se o código avançou além do que está documentado.>

## Observações
<Inconsistências entre spec e código, débitos técnicos, riscos (ex: vazamento
de dados, falta de testes em parte crítica), documentação desatualizada, ou
qualquer decisão implícita no código que não está registrada na spec. Se
houver ações sugeridas, liste-as aqui como propostas explícitas, não como
algo já feito.>
```

Mantenha o resumo objetivo e ancorado em evidência (arquivo, linha, commit)
sempre que possível — evite afirmações genéricas tipo "o projeto está
avançando bem" sem apontar o que sustenta isso.

## Entrega do resultado

Sempre mostre o resumo completo na conversa primeiro. Só grave em arquivo
(ex: `STATUS.md`) se o usuário pedir isso explicitamente ou responder "sim"
quando você perguntar se quer salvar — nunca crie o arquivo por conta
própria só porque parece útil. Isso vale mesmo que uma rodada anterior já
tenha pedido para salvar: pergunte de novo a cada execução, porque a
aprovação é para aquele momento, não permanente.
