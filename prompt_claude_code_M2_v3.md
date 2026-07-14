# Prompt — DeployOps Agentic · Mês 2 do MVP (tarefas M2-T01 a M2-T06)

> Cole tudo abaixo desta linha no Claude Code, executando dentro de `itau-rs7-dep-iu-lotus-sdk`.

---

## 0. Como ler este briefing

Este documento é **direcionamento, não especificação**. Ele existe porque você não tem o contexto do projeto, do escopo e das decisões de arquitetura já tomadas — e eu quero que você o tenha antes de começar.

Mas: **o repositório e a documentação oficial são a fonte de verdade, não este texto.** Onde eu citar nomes de campos, funções, parâmetros ou estruturas da IU Lotus, trate como **hipótese a confirmar** — eu escrevi de memória e posso estar desatualizado ou incompleto. Vá olhar. Se o que você encontrar contradisser o que está aqui, **o repositório ganha** e você me avisa da divergência.

Da mesma forma, a lista de arquivos, a estrutura de pastas e a modelagem que sugiro adiante são pontos de partida. Você tem o contexto real do código; use seu julgamento. Se tiver um desenho melhor, proponha.

Antes de escrever qualquer código: **leia os repositórios, entenda a plataforma, e me devolva um plano de execução** (o que entendeu, o que vai criar, o que vai mockar, premissas, dúvidas e divergências encontradas). Só depois da minha confirmação você implementa.

---

## 1. Onde está o contexto

Três repositórios irmãos, no mesmo nível do sistema de arquivos. Você é executado dentro do primeiro, mas **pode e deve sair dele** para consultar os outros dois:

| Repositório | O que é |
|---|---|
| `itau-rs7-dep-iu-lotus-sdk` | **Onde você está.** O SDK da IU Lotus. É a implementação real da plataforma — a autoridade sobre assinaturas, parâmetros, schemas, fluxos de deploy e o que de fato existe. |
| `../itau-rs7-doc-iulotus` | Documentação **pública** da IU Lotus. Conteúdo em `docs/` na raiz. Jornada oficial, conceitos, experiência do usuário. |
| `../itau-mr7-doc-documentacao-interna` | Documentação **interna** da IU Lotus. Conteúdo em `docs/` na raiz. Decisões técnicas, operação, infraestrutura, troubleshooting, governança, produção. **Tem prioridade sobre a pública para decisões técnicas.** |

**Estude os três antes de propor o plano.** É lendo o SDK e essas duas documentações que você vai entender como um deploy realmente acontece na IU Lotus: quais artefatos existem, quais campos eles têm, quais são obrigatórios, o que a esteira faz, o que o usuário faz, o que a governança exige. Não confie em mim para isso — confie no que está lá.

---

## 2. O projeto

**DeployOps Agentic** é um sistema multiagente (copiloto) que ajuda Data Scientists e ML Engineers a **preparar artefatos de deploy** e **acionar com segurança o deploy de modelos** na IU Lotus. É **pesquisa aplicada / prova de conceito**, feita por uma pessoa só, com 8 meses para um MVP. Não é produção.

**Enquadramento correto — isso governa o design inteiro.** O agente **não faz deploy**. O agente:

1. entende a intenção do usuário;
2. checa pré-requisitos de governança;
3. **gera/preenche os artefatos de configuração** que a plataforma exige (descubra quais são e qual a forma exata deles lendo o SDK e a doc);
4. valida esses artefatos de forma determinística;
5. apresenta um **plano revisável** para **aprovação humana** (com um fast-path opcional e restrito — seção 5);
6. e só então **aciona o fluxo oficial de deploy** da esteira IU Lotus, que é quem de fato executa.

Quem executa é a esteira determinística existente. O agente prepara, valida, explica e aciona. Autonomia irrestrita está fora de escopo — é um ambiente bancário regulado.

**Escopo do MVP:**
- Ambiente alvo: **`analytics` apenas**. A plataforma tem uma cascata de ambientes; os demais estão **fora do MVP** e devem ser bloqueados por allowlist no código. (Confirme no repo os nomes exatos dos ambientes.)
- Prioridade no flavor de inferência **batch**, mas o estado deve comportar os demais que a plataforma suportar.
- Fora de escopo: Feature Store (outro agente cuida), deploy em ambientes fora de `analytics`, rollback automático, orquestradores externos pesados.
- Contexto de governança do banco (não implemente integração real com nada disso — no MVP é checklist + gate humano): MRM/FAARM, GMUD, SR 11-7.

---

## 3. Arquitetura alvo do MVP mínimo

```
Usuário técnico (DS / MLOps)
        │  canal simples: CLI / notebook / chat
        ▼
┌──────────────────── Camada Agentic (NOVO) ────────────────────┐
│  Orquestrador DeployOps  → estados, roteamento, bloqueios     │
│      ├── Módulo de Governança  → pré-requisitos e bloqueios   │
│      └── Agente de Configuração → artefatos de deploy         │
│      (ambos consultam a documentação IU Lotus como            │
│       Knowledge Source)                                       │
└───────────────────────────────────────────────────────────────┘
        │
        ▼  Validações determinísticas (NOVO)
   ┌───────────────┬────────────────────┬────────────────────┐
   │ Checklist     │ Validators         │ Diff revisável     │
   │ pré-deploy    │ (schema, sintaxe,  │ antes/depois,      │
   │ (governança)  │  placeholders...)  │ campos pendentes   │
   └───────────────┴────────────────────┴────────────────────┘
        │
        ▼
   ◆ GATE DE APROVAÇÃO — review do plano ◆
     · padrão: aprovação humana (interrupt)
     · fast-path opcional: auto-aprovação sob política estrita (seção 5)
        │            │              │
   aprovado     rejeitado       bloqueado
        │       (volta p/ CFG)   (handoff)
        ▼
   Condução de inferência local → instrui o usuário e AGUARDA confirmação
        │ ok
        ▼
┌────────── Esteira IU Lotus (EXISTENTE) ──────────┐
│  Wrapper seguro do SDK (NOVO):                   │
│  allowlist de ambiente, dry-run ou real          │
│        ▼                                         │
│  SDK IU Lotus  →  ambiente analytics             │
└──────────────────────────────────────────────────┘
        │
        ▼  Pós-deploy básico (NOVO)
   Parser do retorno do acionamento (status, referências, erros)
        ▼
   Diagnóstico básico (padrões de falha documentados)
        ▼
   Relatório pós-deploy (status, evidências, pendências) → Usuário

   Handoff estruturado (lacunas e próximos passos) → Usuário
   Audit log JSONL (run_id, decisões, aprovações, tool calls) ← todos os nodes
```

**Nesta rodada (M2), NADA disso tem lógica real.** Tudo que depende de LLM, de retrieval ou de integração externa é **mock**. O objetivo é ter o **esqueleto do grafo rodando end-to-end**, com os caminhos felizes e os loops de retorno funcionando, **antes** de qualquer lógica de negócio.

---

## 4. Restrições que valem de verdade

Poucas, e todas são decisões de projeto — não são preferências técnicas minhas:

1. **Orquestração em LangGraph 1.x.** É decisão de arquitetura já tomada no projeto — não proponha outro framework de orquestração. Use a API 1.x (`StateGraph`, roteamento condicional, `interrupt()` / `Command(resume=...)`, checkpointer). Se a dependência ainda não estiver no repo, adicione seguindo as convenções dele.
2. **Ferramental do repo manda.** Não invente stack. Olhe o `pyproject.toml` (ou equivalente), o setup de lint/format/testes e as convenções que já existem, e siga. Se faltar algo, proponha antes de adicionar.
3. **Nenhuma chamada real nesta rodada:** sem LLM real, sem retrieval real, sem SDK real, sem rede nos testes. Tudo por trás de interfaces, com implementação fake.
4. **Allowlist de ambiente.** Qualquer caminho que simule acionamento de deploy rejeita hard qualquer ambiente que não seja `analytics`. É bloqueio de segurança, não `if` decorativo.
5. **O gate de aprovação é sempre atravessado.** Não pode existir caminho no grafo que chegue ao acionamento do deploy sem passar pelo node de review. O que pode variar é se ele interrompe ou auto-aprova (seção 5).
6. **O agente nunca inventa campos de identificação e de destino.** Existem campos que **não podem** ser inferidos por LLM — coisas como identificadores de história/demanda, identificadores de risco de modelo, contas AWS, identificadores de experimento, tabelas e queries de destino/inferência. Esses campos só podem ser preenchidos por **confirmação humana explícita** ou por **fonte estruturada confiável**; se não houver, ficam marcados como pendentes/bloqueantes e o agente diz isso em voz alta. **A lista exata desses campos você deriva do schema real dos artefatos** (SDK + doc interna) — os exemplos que dei são ilustrativos e podem estar incompletos ou com nome errado. Levante a lista, me mostre, e deixe-a num único lugar do código, configurável.
7. **Lacuna não se preenche com invenção.** Se a doc e o SDK não cobrirem algo, pare, registre em `docs/M2/lacunas.md` e me pergunte.

Convenção de idioma: identificadores e nomes de arquivo em inglês; docstrings, comentários e docs em **pt-BR**.

**Não faça commits.** Deixe as mudanças no working tree; eu reviso e commito.

---

## 5. Fast-path de aprovação — funcionalidade OPCIONAL e REMOVÍVEL

O PM pediu um "toggle": o usuário que priorizar agilidade pode seguir o fluxo **sem parar para aprovação humana do plano**.

**Restrição de projeto sobre esta feature: ela é provisória.** Há chance real de ser removida a pedido da squad de governança. Portanto, implemente de forma **isolada e cirurgicamente removível** — apagar a feature não pode exigir mudança no grafo, no roteamento, nos demais nodes nem nos testes principais.

### 5.1 Desenho

- Toda a lógica da feature mora **num único módulo de política** (ex.: `policy/approval_policy.py`). Nenhum outro node sabe que ela existe.
- Ponto de entrada único: algo como `decide(state, config) -> ApprovalDecision`, retornando `REQUIRE_HUMAN` ou `AUTO_APPROVE(reason)`.
- O node de review faz **um único `if`** no começo: se a política auto-aprova, segue sem `interrupt()`; caso contrário, comportamento padrão. Nada mais muda no node. **A aresta de saída é a mesma** (`aprovado`), então o roteamento é idêntico nos dois modos.
- Config com **defaults seguros**: aprovação humana exigida por padrão; fast-path só liga por **flag explícita** (ex.: `--fast-path` no CLI), nunca herdada de arquivo de config.

Formato exato da config e da decisão: à sua escolha, seguindo as convenções do repo. O que importa é o isolamento.

### 5.2 Bloqueios duros — a política DEVE recusar o fast-path mesmo com o toggle ligado

O fast-path só pode disparar quando **não há nada para um humano decidir**. Se o agente tem dúvida, o humano volta ao circuito. Recuse (retorne `REQUIRE_HUMAN`) se:

- houver qualquer campo com status bloqueante;
- houver qualquer campo pendente;
- houver qualquer campo da lista "nunca auto-preencher" (restrição 6) sem confirmação de fonte humana/estruturada;
- os validators tiverem retornado erro;
- o checklist de governança não tiver passado;
- o ambiente não for `analytics`;
- for execução real (não dry-run) e a config não permitir fast-path em execução real — **default: não permitir**.

Isso não é negociável: é o que torna a feature defensável numa revisão de risco.

### 5.3 Auditoria

O audit log **sempre** registra o modo de aprovação (`manual` | `auto`). Quando `auto`, registra também o motivo liberado pela política, a config vigente e um evento explícito de bypass. Uma run auto-aprovada precisa ser **reconstituível pelo log**: quem ligou a flag, com que config, e quais pré-condições estavam satisfeitas.

### 5.4 Contrato de remoção — entregável obrigatório

Escreva `docs/M2/fast_path_removal.md` com o procedimento exato de remoção. Ele tem que caber, em essência, nisto:

1. apagar o módulo de política;
2. remover o `if` do node de review (deixando só o `interrupt()`);
3. remover a flag do CLI;
4. apagar os testes da feature;
5. (opcional) remover os campos aditivos do estado — inertes se ficarem.

**Se, ao implementar, você perceber que a remoção exigiria mais do que isso, o desenho está errado — pare e me avise.** Nenhuma mudança no grafo, no roteamento ou nos demais nodes pode ser necessária para remover a feature.

---

## 6. Tarefas desta rodada

Execute nesta ordem.

### M2-T01 — Estado tipado com todos os campos do MVP
**Entregável:** o schema completo do estado do grafo (TypedDict + reducers onde fizer sentido, ex.: trilhas append-only).

Ele precisa comportar, no mínimo: identidade da run (`run_id`, `thread_id`, timestamps); a intenção e o contexto do usuário; **slots para cada artefato de deploy que a plataforma exige** (descubra quais são e a forma deles no SDK/doc); **status por campo** (algo como `ok_fonte` / `inferido` / `pendente` / `bloqueante`); resultado do checklist de governança; resultado dos validators; o diff antes/depois com campos pendentes; a decisão do gate (aprovado/rejeitado/bloqueado, feedback, quem e quando); os campos do fast-path (seção 5); contadores e limite de iteração do loop de correção; status da condução de inferência local; parâmetros e retorno do acionamento do SDK (bruto e parseado); diagnóstico e relatório pós-deploy; motivo e conteúdo do handoff; trilha de auditoria; trilha de erros.

**Critério de aceite:** schema importável, defaults coerentes (fast-path desligado), factory de criação gerando `run_id`, testes cobrindo criação, defaults e comportamento append-only das trilhas.

---

### M2-T02 — Nodes esqueleto (10 a 12 nodes), com log e decisões hardcoded
**Entregável:** um node por responsabilidade, cada um retornando estado simulado. Zero lógica de negócio.

Ponto de partida (ajuste se o contexto do repo indicar melhor — mas me avise da mudança):

| Node | Responsabilidade (mock nesta rodada) |
|---|---|
| `intake` | Normaliza o pedido do usuário em campos do estado. |
| `governance_check` | Checklist de pré-requisitos de governança. Mock; aprovado/reprovado controlável por input de teste. |
| `retrieve_context` | Consulta à base de conhecimento (documentação IU Lotus). **Mock** — retorna trechos falsos com metadado de origem. O retriever real vem numa rodada seguinte; deixe atrás de uma interface para poder trocar sem tocar nos nodes. |
| `config_agent` | Gera/atualiza os artefatos de deploy. **Mock** — artefatos sintéticos, com alguns campos pendentes. |
| `validators` | Validações determinísticas. Mock: sucesso/erro conforme input de teste. |
| `build_diff` | Diff antes/depois + lista de campos pendentes. |
| `human_review` | **Gate de aprovação.** Consulta a política (seção 5): `interrupt()` (padrão) ou auto-aprovação. Retoma via `Command(resume=...)`. |
| `local_inference` | Instrui o usuário a rodar inferência local e **aguarda confirmação**. O fast-path **não** afeta este node nesta rodada. |
| `sdk_dispatch` | Wrapper seguro: valida allowlist de ambiente, respeita dry-run, chama o **adapter fake** do SDK. |
| `parse_sdk_result` | Extrai status, referências e erros do retorno (mock estruturado). |
| `diagnose` | Reconhece padrões de falha documentados (mock). |
| `report` | Relatório pós-deploy. Nó terminal. |
| `handoff` | Handoff estruturado: lacunas e próximos passos. Nó terminal. |

**Auditoria não é node** — é um helper chamado pelos nodes, que anexa evento à trilha do estado e escreve linha no audit log JSONL local.

**Critério de aceite:** cada node é função pura `state -> patch de estado`, com log estruturado, testável isoladamente, sem I/O de rede. Testes unitários por node.

---

### M2-T03 — Edges e roteamento condicional
**Entregável:** grafo compilável, com o roteamento correto.

- `intake` → `governance_check`
- `governance_check`: **reprovado** → `handoff`; **aprovado** → `retrieve_context`
- `retrieve_context` → `config_agent` → `validators`
- `validators`: **falhou** → volta para `config_agent` (conta iteração); **passou** → `build_diff`
- `build_diff` → `human_review`
- `human_review`: **aprovado** → `local_inference`; **rejeitado** → volta para `config_agent` (conta iteração, carregando o feedback); **bloqueado** → `handoff`
- **Guard de iteração:** ao atingir o limite de reworks (3), qualquer retorno para `config_agent` vira `handoff`, com motivo explícito.
- `local_inference`: **confirmada** → `sdk_dispatch`; **falhou** → `handoff`
- `sdk_dispatch` → `parse_sdk_result` → `diagnose` → `report` → END
- `handoff` → END

**Critério de aceite:** grafo compila; testes cobrem as **3 saídas do gate** e a reprovação da governança; teste que prova que **nenhum caminho alcança `sdk_dispatch` sem atravessar `human_review`** — e que continua valendo no modo fast-path.

---

### M2-T04 — Checkpointer SQLite e gestão de thread_id
**Entregável:** persistência funcionando.

- Checkpointer SQLite, arquivo em caminho configurável (não versionar o `.db`).
- `thread_id` explícito; uma run = um `thread_id` estável.
- Retomada: dado um `thread_id` interrompido no gate, retomar com `Command(resume=<decisão>)` preservando o estado.

**Critério de aceite:** teste que executa até o `interrupt()`, **descarta o objeto do grafo / simula restart do processo**, recria o grafo a partir do checkpointer e retoma com sucesso. Se o restart não for simulável no teste, diga no relatório o que foi verificado de fato e o que não foi.

---

### M2-T05 — Teste end-to-end do happy path (todos mocks)
**Entregável:** run completo `intake` → `report` com dados sintéticos.

Governança aprova, validators passam, humano aprova no **modo manual** (fast-path desligado), inferência local confirmada, dispatch em dry-run. Ao final: estado coerente, relatório gerado, **audit log JSONL com os eventos na ordem esperada e modo de aprovação `manual`**, e nenhuma tentativa de acionar ambiente fora da allowlist.

**Critério de aceite:** teste verde, determinístico, sem rede.

---

### M2-T06 — Teste end-to-end com loop de retorno, handoff e fast-path
**Entregável:** cobertura dos caminhos não-felizes e da feature opcional.

Loop e handoff:
1. **Loop de rejeição:** humano rejeita → volta para `config_agent` → itera. Na 3ª rejeição o guard dispara e cai em `handoff` com motivo de limite de iterações. Verificar o contador e que o feedback humano chega ao `config_agent`.
2. **Bloqueio no gate:** `bloqueado` → `handoff` direto, com lacunas preenchidas.
3. **Governança reprova:** → `handoff`, sem nunca chegar ao `config_agent`.
4. **Falha na inferência local:** → `handoff`.

Fast-path (seção 5):

5. **Ligado, estado limpo** (sem pendências, validators ok, governança aprovada, dry-run) → **não há `interrupt()`**, o fluxo segue direto até `report`; audit log registra modo `auto`, evento de bypass, motivo e config.
6. **Ligado + campo pendente** → política **recusa**, `interrupt()` acontece, modo `manual`, motivo da recusa registrado.
7. **Ligado + erro de validator** → recusa.
8. **Ligado + execução real com a config que não permite** → recusa.
9. **Desligado (default)** → comportamento idêntico ao M2-T05: prova de que a feature é inerte quando não solicitada.

**Critério de aceite:** todos os cenários cobertos, cada um verificando estado final, motivo do handoff/recusa e a trilha de auditoria.

---

## 7. Definição de pronto

- [ ] Suíte de testes verde, determinística, sem rede.
- [ ] Lint/format do repo passando.
- [ ] Grafo compila e roda end-to-end pelo CLI, com retomada por `thread_id`.
- [ ] Nenhum caminho chega ao dispatch sem atravessar o node de review (provado por teste, nos dois modos).
- [ ] Fast-path desligado por default; ligado só por flag explícita; política recusa em todos os bloqueios duros da seção 5.2 (provado por teste).
- [ ] Allowlist de ambiente bloqueia tudo que não for `analytics` (provado por teste).
- [ ] Os campos "nunca auto-preencher" (levantados por você a partir do schema real) permanecem pendentes/bloqueantes no mock (provado por teste), e a lista vive num único lugar configurável.
- [ ] Audit log JSONL gerado, sempre com o modo de aprovação; runs auto-aprovadas reconstituíveis pelo log.
- [ ] `docs/M2/fast_path_removal.md` escrito **e verificado**: confirme explicitamente que a remoção não toca no grafo, no roteamento nem nos demais nodes.
- [ ] `docs/M2/relatorio_m2.md`: o que foi feito por tarefa, o que ficou mockado e por quê, armadilhas do LangGraph encontradas, **o que você descobriu lendo o SDK e a documentação que contradiz ou complementa este briefing**, e o que não foi possível validar.
- [ ] `docs/M2/lacunas.md`: tudo que precisa de confirmação da squad ou da fonte oficial.
- [ ] **Sem commits.** Mudanças no working tree.

---

## 8. O que NÃO fazer nesta rodada

- Não implementar retrieval real, LLM real, ou chamada real ao SDK.
- Não implementar a lógica real de geração dos artefatos de deploy (é a rodada seguinte).
- Não estender o fast-path para outros gates (ex.: pular a confirmação de inferência local). Só o gate de aprovação do plano.
- Não criar caminho de deploy para ambientes fora de `analytics`.
- Não trocar de framework de orquestração.
- Não inventar nomes, assinaturas ou campos da IU Lotus para "deixar mais realista". Se não confirmou no SDK ou na doc, marque como lacuna.

---

**Comece lendo os três repositórios. Depois me devolva o plano de execução, as premissas, as dúvidas e as divergências que encontrou entre este briefing e a realidade do código. Não escreva código ainda.**
