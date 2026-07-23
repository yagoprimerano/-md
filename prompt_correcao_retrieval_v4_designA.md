# Correção M2 — retrieval como ferramenta sob demanda (Knowledge Source)

> Cole abaixo desta linha no Claude Code, no repositório `itau-rs7-dep-iu-lotus-sdk`, na branch do M2.
> **Esta versão substitui qualquer prompt de correção anterior sobre retrieval.**

---

## 0. Natureza desta tarefa

Você implementou o esqueleto do grafo LangGraph do **DeployOps Agentic** (M2-T01 a M2-T06). O resultado está majoritariamente certo, mas há **um erro de arquitetura no retrieval** que precisa ser corrigido antes do M3. Esta é uma **correção focada**, não um refazimento.

Não toque no que está certo: gate de aprovação humana, fast-path e seu isolamento, allowlist de ambiente, campos never-autofill, checkpointer SQLite, audit log JSONL, testes de roteamento/gate/fast-path/allowlist. A mudança é cirúrgica e circunscrita ao retrieval.

Antes de codar, **leia o código atual** e **me devolva um plano**. Só implemente após eu confirmar.

---

## 1. Onde está o contexto

| Repositório | O que é |
|---|---|
| `itau-rs7-dep-iu-lotus-sdk` | **Onde você está.** SDK da IU Lotus + o código do DeployOps Agentic que já construímos (grafo LangGraph esqueleto, nodes, estado tipado, audit log). |
| `../itau-rs7-doc-iulotus` | Documentação **pública** da IU Lotus. Conteúdo em `docs/`. Jornada, conceitos, experiência do usuário. |
| `../itau-mr7-doc-documentacao-interna` | Documentação **interna** da IU Lotus. Conteúdo em `docs/`. Decisões técnicas, operação, infraestrutura, troubleshooting, governança, produção. **Prioridade sobre a pública em decisões técnicas.** |
| `../itau-kk7-doc-iara-gen-ai` | Documentação do **IARA** (a ferramenta de RAG — ver abaixo). Conteúdo em `docs/01_documentacao`. **Autoridade sobre o que o IARA faz, o que expõe por SDK, e o que é configurável na ingestão e no retrieval.** Leia com atenção se precisar entender o contrato real do RAG que entra em M3. |

As duas documentações da IU Lotus (pública e interna) **são o corpus** que o RAG deste projeto consulta. O **IARA** é a ferramenta interna que provê o retrieval real (entra em M3); nesta rodada tudo continua mockado, mas se você precisar entender a assinatura real de consulta para desenhar a porta corretamente, a doc do IARA é a fonte.

**Dois modos de retorno do IARA — e a decisão de projeto sobre eles.** O IARA pode retornar de duas formas: (a) **apenas os chunks recuperados** (retrieve-only), ou (b) **os chunks + uma resposta sintetizada por um LLM do próprio IARA** a partir da pergunta e dos chunks. **Este projeto consome apenas os chunks (modo retrieve-only).** A resposta sintetizada do IARA **não entra no fluxo de decisão** — nem no `config_agent`, nem no `governance_check`. Motivos: para o `config_agent`, já verificamos que os chunks brutos funcionam melhor; para o `governance_check`, consumir uma resposta já "interpretada" por um LLM colocaria um LLM no meio de um gate que precisa ser determinístico e auditável (ver seção 3). A porta da Knowledge Source que você desenhar deve, portanto, **expor o modo retrieve-only como o caminho usado**. Não faça o fluxo depender da resposta sintetizada.

---

## 2. O erro

O grafo tem hoje um node fixo `retrieve_context` na cadeia:

```
governance_check → retrieve_context → config_agent → validators
```

Isso está errado por dois motivos:

1. **Retrieval não é uma etapa fixa do pipeline.** No desenho pretendido do projeto, a documentação (Knowledge Source) é um **recurso consultado sob demanda**, não um passo que roda uma vez antes do agente. Quem consulta são **dois componentes**, cada um quando precisa:
   - o **Agente de Configuração** (`config_agent`) consulta a Knowledge Source para conhecer convenções, exemplos e restrições ao preencher cada campo de cada artefato (`model.yml`, payload de `config_deploy`, `expressions.yml`);
   - o **Módulo de Governança** (`governance_check`) lê a Knowledge Source **via RAG** para **carregar quais são as regras de pré-requisito** — em vez de tê-las codificadas rigidamente (ver seção 3 para o que isso significa e o que NÃO significa).

   Um retrieval cego no início, sobre a fala crua do usuário e antes de o agente raciocinar sobre o que precisa, é o pior momento para buscar: o agente ainda não sabe o que não sabe. O agente é quem sabe formular a pergunta certa ao RAG, no momento em que bate a dúvida.

2. **O elo está morto.** Hoje o `config_agent` **não lê** o resultado do `retrieve_context`, **não recebe** porta de retrieval e **não consulta** o RAG. E o `governance_check` também **não tem** acesso ao RAG. Ou seja: o `retrieve_context` produz um output que ninguém consome, e os dois componentes que *deveriam* consultar a Knowledge Source não conseguem.

Estamos em M2 (esqueleto, tudo mockado), então não há sintoma visível ainda — mas o esqueleto está moldando o M3 errado.

---

## 3. O desenho correto

**Remover o node `retrieve_context`.** A capacidade de retrieval passa a ser uma **porta única** (a "Knowledge Source"), **injetada como dependência** em **dois** nodes: `config_agent` e `governance_check`. Cada um a chama **sob demanda**.

Novo roteamento (a única mudança de topologia):

```
governance_check → (aprovado) config_agent   ← direto, sem retrieve_context no meio
governance_check → (reprovado) handoff
```

Tudo o mais no grafo permanece idêntico.

### 3.1 — Papéis do RAG em cada consumidor (leia com atenção — isto evita um erro grave)

Os dois nodes consultam a **mesma** Knowledge Source, mas para fins diferentes, e **nenhum dos dois usa LLM para decidir**:

- **`config_agent` (agêntico em M3):** usa os chunks como contexto para preencher/revisar campos dos artefatos. Aqui o LLM (em M3) raciocina sobre o conteúdo. Este é o único componente genuinamente agêntico.

- **`governance_check` (determinístico — NÃO é agente):** usa o RAG para **carregar a lista de regras de pré-requisito** a partir da documentação oficial (quais campos são obrigatórios, quais itens são bloqueantes), em vez de ter essa lista hardcoded no código. **A decisão de aprovar ou bloquear permanece uma checagem determinística de presença** — para cada regra da lista, código puro verifica se o input do usuário a satisfaz (`if campo_obrigatório not in inputs: bloqueante`). **Nenhum LLM interpreta se um pré-requisito foi satisfeito. Nenhum LLM decide o gate.** O RAG serve só para manter a *lista de regras* viva e atualizável pela documentação — não para julgar o caso.

A distinção em uma frase: a governança **busca o regulamento na estante** (RAG, dinâmico), mas **aplica a checagem mecanicamente** (determinística). Um LLM que lê o caso e decide com discernimento seria o modo agêntico — e é exatamente o que a arquitetura **proíbe** para um gate de deploy em ambiente bancário regulado. Se, ao implementar, você se pegar colocando um LLM para interpretar a resposta do RAG e decidir a aprovação, **pare — o desenho está errado.**

Isto também explica por que consumimos apenas os chunks (seção 1): a resposta sintetizada do IARA é uma interpretação por LLM, e a governança não pode decidir com base nela.

### 3.2 — Interface única

**Trava inegociável:** existe **uma única porta/interface de retrieval** no projeto (a Knowledge Source). `config_agent` e `governance_check` usam **a mesma**. **Não crie uma segunda interface.** Se a porta atual (a que o `retrieve_context` usava) não expõe o método de consulta adequado (retrieve-only), **estenda a existente** — não duplique. O `MockRetriever` / adapter fake continua sendo a única implementação nesta rodada.

> Observação: remover um node e reconectar uma aresta **é** uma mudança de grafo — e está tudo bem, ainda estamos em M2 (esqueleto) e o projeto aceita ajustes de grafo quando necessários. O que evitamos é deixar o esqueleto errado e ter que refazê-lo em M3.

---

## 4. Mudanças concretas (tudo mockado, sem rede)

1. **Remover o node `retrieve_context`** do builder do grafo e reconectar `governance_check --aprovado--> config_agent`. Remover o arquivo do node e seus testes específicos, se houver.

2. **Definir/consolidar a porta da Knowledge Source** — a interface única de consulta ao RAG, **modo retrieve-only** (retorna chunks, não resposta sintetizada), com o `MockRetriever` atrás dela (a mesma que já existia). Se precisar de um método de query com assinatura adequada para uso sob demanda, adicione-o **nesta** porta.

3. **Injetar a porta em `config_agent`.** No fluxo mockado, o `config_agent` deve **chamar a Knowledge Source sob demanda** ao menos uma vez (simulando a busca da documentação de um campo específico que está preenchendo). **O resultado da consulta tem que influenciar o artefato mockado de forma observável** — por exemplo, um campo do artefato que muda de valor ou de status conforme o chunk retornado. Não repita o bug anterior: a consulta não pode ser decorativa e ter o resultado descartado.

4. **Injetar a mesma porta em `governance_check`.** No fluxo mockado, o `governance_check` deve **consultar a Knowledge Source para "carregar" a lista de regras de pré-requisito** (em vez de tê-las hardcoded) e, em seguida, **aplicar a checagem de presença de forma determinística** sobre essa lista. O resultado do RAG influencia **quais regras são checadas**; a decisão de bloquear/aprovar é código puro. Registre no mock essa separação de forma clara (ex.: uma função que carrega regras via porta, e outra, sem LLM, que aplica a checagem).

5. **Auditar cada consulta ao RAG.** Toda chamada à Knowledge Source — venha do `config_agent` ou do `governance_check` — gera um evento no audit log JSONL, registrando **quem** consultou (qual node), **o que** consultou (a query) e um resumo do que voltou (chunks). É isso que, no M3, vai permitir rastrear de onde cada decisão do agente tirou fundamento.

---

## 5. Verificar contra a intenção e me reportar (não altere sem confirmar)

Enquanto estiver no código, cheque estes pontos e **me reporte** — só corrija se eu confirmar, para não misturar escopo:

1. **Idempotência do SDK Wrapper (`sdk_dispatch`).** O planejamento é enfático: o wrapper deve registrar "já chamei o SDK neste `run_id`" **antes** da chamada e checar isso **a cada entrada no node** — justamente porque o LangGraph pode **reexecutar nodes ao retomar de `interrupt()`**. Sem esse guard, uma retomada depois do gate humano pode **disparar o deploy duas vezes**. Verifique se `sdk_dispatch` tem essa checagem de idempotência por `run_id`. Se **não** tiver, é o item mais importante desta verificação — reporte com destaque e diga onde entraria. (Em M2 é mock, então não explode agora, mas o esqueleto precisa do guard para o M3 não herdar o buraco.)

2. **Terceira opção da inferência local.** O node `local_inference` hoje tem só `confirmada`/`falhou`. O planejamento previa uma **terceira** saída: `pular` (retreino — a documentação permite pular a inferência local nesse caso, e o agente registra a escolha no audit log). Confirme se está ausente e diga onde entraria.

3. **Limite de iteração de rework.** Verifique se o comportamento é "**até 3 reworks**, handoff na **4ª** rejeição" ou se está fazendo handoff mais cedo (off-by-one). Reporte o número real e onde é decidido.

---

## 6. Testes a adicionar/ajustar

- `config_agent` **recebe** a porta de retrieval (dependência injetada) e, no mock, **faz ao menos uma consulta** que **aparece no audit log** e **altera o artefato** de forma observável.
- `governance_check` **recebe** a mesma porta, **consulta** no mock para carregar a lista de regras, e **aplica a checagem determinística** — com um teste que prova que a decisão de bloqueio é função da presença/ausência dos campos (não de nenhuma interpretação por LLM), e com evento no audit log.
- **Não existe** node `retrieve_context` no grafo compilado, e **não existe** uma segunda interface de retrieval — as duas vias usam a mesma porta, em modo retrieve-only.
- O roteamento `governance_check --aprovado--> config_agent` está correto e o grafo compila.
- Todos os testes de gate, fast-path, allowlist e checkpointer continuam **verdes e inalterados**. Se algum quebrar, a correção vazou — investigue antes de "consertar" o teste.

---

## 7. Documentação a atualizar

- `docs/M2/relatorio_m2.md`: registrar a correção — o que estava errado (`retrieve_context` como node fixo com output descartado; `config_agent` e `governance_check` sem acesso ao RAG), o que passou a ser (Knowledge Source como porta única retrieve-only, consultada sob demanda; `config_agent` usa os chunks como contexto, `governance_check` usa o RAG para carregar regras mas decide determinísticamente), e a remoção do node.
- Atualizar o diagrama do grafo na `apresentacao.md` para remover `retrieve_context` e refletir que `config_agent` e `governance_check` consultam a Knowledge Source como recurso (não como etapa).
- `docs/M2/lacunas.md`: se houver dúvida sobre a assinatura real da consulta ao IARA (o RAG real que entra em M3), registrar como lacuna — não inventar a assinatura.

---

## 8. Restrições que continuam valendo

- Tudo mockado; sem LLM/retrieval/SDK real; sem rede nos testes.
- Uma única porta de retrieval, modo retrieve-only; não duplicar interface; não usar a resposta sintetizada do IARA no fluxo de decisão.
- A governança é **determinística**: RAG carrega regras, código decide. Nenhum LLM no julgamento do gate.
- Nenhum caminho chega ao `sdk_dispatch` sem atravessar `human_review`.
- Allowlist bloqueia tudo que não for `analytics`.
- Campos never-autofill continuam `pendente`/`bloqueante`; retrieval sob demanda **não** é desculpa para o mock preencher um desses.
- Não inventar nomes/assinaturas da IU Lotus ou do IARA; repo e doc são fonte de verdade; divergência → repo ganha e você me avisa.
- **Sem commits.** Mudanças no working tree.

---

**Comece devolvendo: (a) como `config_agent`, `governance_check` e `retrieve_context` estão hoje; (b) qual é a porta de retrieval existente e sua assinatura, e se ela expõe modo retrieve-only; (c) o plano de mudança, incluindo a remoção do node e a reconexão da aresta; (d) o que encontrou nos três pontos da seção 5. Não escreva código ainda.**
