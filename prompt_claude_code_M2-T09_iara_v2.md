# Prompt — DeployOps Agentic · Mês 2 do MVP (tarefa M2-T09 — avaliação de retrieval sobre o IARA)

> Cole tudo abaixo desta linha no Claude Code, executando dentro de `itau-rs7-dep-iu-lotus-sdk`.

---

## 0. Como ler este briefing

Este documento é **direcionamento, não especificação**. Ele existe porque você não tem o contexto do projeto nem das decisões já tomadas — e eu quero que você o tenha antes de começar.

Mas: **o código e a documentação oficial são a fonte de verdade, não este texto.** Onde eu citar nomes de campos, funções, parâmetros, formatos de retorno ou capacidades do IARA e da IU Lotus, trate como **hipótese a confirmar** — escrevi de memória. Vá olhar. Se o que você encontrar contradisser este briefing, **o código ganha** e você me avisa da divergência.

Antes de escrever qualquer código: **leia o que precisa ler, levante o que o IARA de fato entrega e de fato permite configurar, e me devolva um plano de execução.** Só depois da minha confirmação você implementa.

---

## 1. Onde está o contexto

| Repositório | O que é |
|---|---|
| `itau-rs7-dep-iu-lotus-sdk` | **Onde você está.** SDK da IU Lotus + o código do DeployOps Agentic que já construímos (grafo LangGraph esqueleto, nodes, estado tipado, audit log). |
| `../itau-rs7-doc-iulotus` | Documentação **pública** da IU Lotus. Conteúdo em `docs/`. Jornada, conceitos, experiência do usuário. |
| `../itau-mr7-doc-documentacao-interna` | Documentação **interna** da IU Lotus. Conteúdo em `docs/`. Decisões técnicas, operação, infraestrutura, troubleshooting, governança, produção. **Prioridade sobre a pública em decisões técnicas.** |
| `../itau-kk7-doc-iara-gen-ai` | Documentação do **IARA** (a ferramenta de RAG — ver abaixo). Conteúdo em `docs/02_documentacao`. **Autoridade sobre o que o IARA faz, o que expõe por SDK, e o que é configurável na ingestão e no retrieval.** Leia com atenção — é o insumo central do passo zero (seção 4). |

As duas documentações da IU Lotus (pública e interna) **são o corpus** que o RAG deste projeto consulta.

**E existe um quarto elemento, que é o centro desta tarefa:**

**IARA** — ferramenta interna do Itaú que provê o RAG. **Não somos nós que implementamos retrieval.** Há um script no repo atual, `scripts/query_iara_kb.py`, que consulta a base de conhecimento via **SDK do IARA** (não via SDK da IU Lotus — são coisas distintas, não confunda). Pelo que sei do comportamento dele:

- rodado normalmente, retorna: a **pergunta**, a **resposta gerada por um LLM** a partir dos chunks, e os **chunks recuperados**;
- rodado com o parâmetro **`--retrieve-only`**, retorna **apenas os chunks, sem passar pelo LLM** — este é o modo que interessa para avaliar retrieval isolado do gerador.

Pelo que sei, cada chunk vem com **score de similaridade inicial** e possivelmente **score após rerank** — mas confirme isso lendo o retorno real, porque não tenho certeza.

**A base de conhecimento deste projeto fui eu quem criou, via SDK, com um script `sync_to_iara.py` no repositório atual da IU Lotus.** Ou seja: a ingestão passou por código nosso. Isso é importante porque significa que algumas decisões de ingestão (splitter, chunking, metadados, pré-processamento) **podem ter sido feitas por nós e podem ser alaváncas nossas** — mas só o levantamento do passo zero vai dizer o que de fato é configurável por SDK.

**A KB é minha e exclusiva deste projeto — eu a criei, só eu a uso, não é compartilhada com outros times ou domínios.** Não há risco de recuperar conteúdo de outro domínio; não precisa investigar isolamento multi-tenant.

**Vá ler a documentação do IARA (`../itau-kk7-doc-iara-gen-ai/docs/02_documentacao`), o `scripts/query_iara_kb.py`, o `sync_to_iara.py` e o SDK do IARA. Eles são a autoridade sobre o contrato real — eu não sou.**

---

## 2. O projeto, em três parágrafos

**DeployOps Agentic** é um copiloto multiagente que ajuda Data Scientists e ML Engineers a **preparar artefatos de deploy** e **acionar com segurança o deploy de modelos** na IU Lotus. Pesquisa aplicada / prova de conceito, uma pessoa, 8 meses para um MVP. Não é produção.

**Enquadramento que governa tudo: o agente não faz deploy.** Ele entende a intenção, checa pré-requisitos de governança, gera/preenche os artefatos de configuração que a plataforma exige, valida de forma determinística, apresenta um plano revisável para **aprovação humana**, e só então aciona a esteira oficial — que é quem executa. Ambiente alvo do MVP: **`analytics` apenas**.

**Orquestração em LangGraph 1.x** (decisão já tomada). O grafo esqueleto já existe, com nodes `intake`, `governance_check`, `retrieve_context`, `config_agent`, `validators`, `build_diff`, `human_review`, `local_inference`, `sdk_dispatch`, `parse_sdk_result`, `diagnose`, `report`, `handoff`. Tudo que depende de LLM, retrieval ou integração externa está atrás de interface, com implementação fake. **O `retrieve_context` está mockado. O IARA é quem vai ficar atrás dessa interface.**

---

## 3. O que é esta tarefa, e por que ela importa

**M2-T09 — Testes de retrieval.** Entregável do plano: *"suite de queries esperadas vs. retornadas, métricas de retrieval mínimas"*.

Não é "testar o RAG por higiene". É **decidir, com número, se o retrieval via IARA está bom o suficiente para o Agente de Configuração depender dele no Mês 3.** Se o IARA devolve o chunk errado, o agente preenche um campo do artefato de deploy com informação de outro flavor, ou alucina uma regra de governança — e isso só apareceria três meses depois, no diff revisável, com todo o prompt engineering já construído em cima de base ruim.

**Mas há uma diferença crucial em relação a um RAG que fosse nosso: nós não controlamos o índice.** Chunking, embeddings, modelo de rerank — são do IARA. Então esta tarefa se divide em duas naturezas de saída, e você deve manter as duas separadas o tempo todo:

| Natureza | O que provavelmente é | O que fazemos com isso |
|---|---|---|
| **Quase certo que é nosso** | formulação das queries; `k`; usar chunks vs. usar a resposta gerada | Decidimos e implementamos |
| **Talvez nosso — o passo zero decide** | corte de score (onde e se aplicamos); splitter/chunking/metadados da ingestão; tipo de busca (semântica/híbrida); rerank | Depende do que o SDK expõe. É o objetivo do levantamento da seção 4. |
| **Encaminhável a terceiros** | limitações fixas do IARA; comportamento do modelo de embedding ou do rerank que não conseguimos configurar; qualidade da própria plataforma | Vira **evidência** para o time do IARA. Não é bug nosso, não tentamos consertar. |

**Importante:** eu não sei ao certo o que cai em cada linha — em especial, **não sei se conseguimos controlar o corte de score**, e não sei o que do menu de ingestão é mudável por SDK vs. só pelo portal. **Preencher esse quadro com fato é o entregável do passo zero (seção 4).** Não assuma; verifique. O relatório final deve dizer, para cada problema encontrado, em qual linha ele caiu.

---

## 4. Passo zero — levantamento do IARA (faça isto ANTES do plano)

Este passo é o mais importante do briefing. Ele existe porque **eu não sei ao certo o que controlamos e o que não controlamos** no IARA — e essa distinção define o escopo inteiro da tarefa. Não implemente nada até responder, lendo a doc do IARA (`../itau-kk7-doc-iara-gen-ai/docs/02_documentacao`), o `scripts/query_iara_kb.py`, o `sync_to_iara.py` e o SDK.

**O objetivo do passo zero é preencher, com fato, este quadro:**

| Natureza | Descrição | O que fazemos |
|---|---|---|
| **Acionável por nós via SDK/código** | parâmetros que conseguimos mudar programaticamente hoje | Vira alavanca da varredura (seção 6.3) |
| **Configurável só na ingestão** | decisões tomadas quando a KB é (re)criada — exigem re-ingestão para mudar | Documentar; mudança é decisão de projeto, não experimento barato |
| **Fora do nosso controle** | fixo no IARA, ou só via portal/UI, não via SDK | Vira observação/evidência, não alavanca |

Preencha respondendo:

1. **Alavancas de RETRIEVAL — o que muda na consulta.** Pelo portal do IARA eu vejo estas opções, mas **não sei quais são acessíveis via SDK** (que é como nós vamos consultar). Confirme cada uma na doc e no código:
   - **`top_k`** — acho que estou trabalhando com 8. Confirme o parâmetro e o default.
   - **Tipo de busca** — semântica / por palavras-chave / híbrida. Acho que o default é semântica. **A híbrida existe via SDK?** (Relevante: nossas queries têm nome exato de campo e de etapa; busca lexical pode ajudar.)
   - **Estratégia de similaridade** — acho que cosseno é o default. É configurável?
   - **Reranking** — existe? é ligável/desligável via SDK? O retorno traz o score pós-rerank?
   - **`score_threshold` / corte de score** — **não sei se isso existe, nem se é controlável por nós.** Verifique com prioridade: existe um parâmetro de corte no SDK? Se sim, é nossa alavanca; se não, o corte tem que ser feito do nosso lado, sobre os scores que o IARA devolve. **Descubra qual dos dois casos é o nosso** — isso decide onde o threshold da seção 6.3 é aplicado.
   - **Filtro por metadados** na consulta — existe via SDK?

2. **Alavancas de INGESTÃO — o que muda na KB.** A ingestão foi feita por nós, via `sync_to_iara.py`. Pelo portal eu vejo estas opções na hora de ingerir um documento; **confirme quais foram usadas de fato no nosso script e quais são mudáveis por SDK:**
   - **Pré-processamento do conteúdo** — otimização baseada em LLM, ou desativado. O que usamos?
   - **Método de fragmentação (splitter)** — character text splitter (texto sem estrutura), recursive character text splitter (texto estruturado), recursive character text splitter para markdown (texto pré-processado), recursive json splitter (json). **Como nosso corpus é markdown/json estruturado, qual splitter faz sentido — e qual usamos?**
   - **`chunk_size`** — default que eu lembro é ~700. Qual usamos?
   - **`chunk_overlap`** — default que eu lembro é ~10. Qual usamos?
   - **`is_separator_regex`** (default desativado?) e **`separator`** (default `\n`?).
   - **Metadados na ingestão** — **acho que já incluí metadados quando ingeri via SDK.** Isto é decisivo para o item 4 abaixo. Verifique no `sync_to_iara.py` **exatamente quais metadados foram anexados a cada chunk** (nome de arquivo? caminho? seção? título?).

   Deixe claro no relatório: para mudar qualquer coisa de ingestão, presumo que seja preciso **re-ingerir a KB**. Confirme. Se for o caso, tratamos ingestão como decisão de projeto (poucas variações, deliberadas), não como varredura barata.

3. **Contrato de saída da consulta.** Rodando `scripts/query_iara_kb.py --retrieve-only`, o que exatamente volta por chunk? Texto, score(s), e — crucial — **metadado de origem** (arquivo, seção)? Veja o item 4.

4. **Rastreabilidade de origem — decisivo.** Para casar o que o IARA devolve com o ground truth `(arquivo, seção)`, cada chunk retornado precisa dizer de onde veio. Se os metadados que ingerimos (item 2) já carregam arquivo+seção e voltam na consulta, ótimo — o casamento é direto. Se **não** voltam, **me reporte imediatamente**: pode significar que precisamos re-ingerir com metadados melhores, ou usar um fallback (casar o texto do chunk contra os arquivos do repo de doc). Isto também importa para a arquitetura além desta tarefa: o agente precisa **citar a fonte** de cada campo que preenche; sem origem no chunk, essa rastreabilidade não existe.

5. **O modo `--retrieve-only` isola mesmo o retrieval?** Confirme que com essa flag nenhuma chamada ao LLM gerador acontece — é esse o modo que avaliaremos. O modo com resposta gerada só é usado na seção 6.4.

6. **O IARA se abstém?** Existe caso em que a consulta devolve "nada encontrado" / lista vazia? Ou ele **sempre** devolve os `k` chunks mais parecidos, por pior que seja o match? Teste na prática com uma pergunta absurda e sem relação com o corpus. A resposta muda o desenho da seção 6.1: se ele nunca devolve vazio, a única barreira contra alucinação é o corte de score do nosso lado.

7. **Custo, latência, limites.** Chamada ao IARA é rápida? Tem rate limit? Isso confirma a necessidade de cache (seção 6.2).

Me devolva esse levantamento — **o quadro de natureza preenchido** — **antes** do plano de execução. É a partir dele que a seção 6.3 ganha escopo real.

---

## 5. Restrições que valem de verdade

1. **O IARA fica atrás da porta de retrieval que já existe no código.** O node `retrieve_context` já consome uma interface, com implementação fake. Você cria um **adapter do IARA** para essa mesma porta. **Não crie uma segunda interface**, não chame o SDK do IARA de dentro de node nenhum, e o harness de avaliação fala com a **porta**, nunca com o SDK direto. Se a porta atual não comportar o que o IARA devolve (dois scores, metadados), **proponha a extensão antes de mexer** — não a altere por conta própria.

2. **O corpus é documentação estruturada** (`.md`, `.json` e afins nos dois repositórios de doc). A hierarquia de seções é confiável e é o que usaremos como unidade de ground truth. Não presuma nada além disso sobre a forma dos arquivos — vá ver.

3. **Campos que o agente nunca pode auto-preencher.** Existem campos dos artefatos de deploy que **não podem** ser inferidos por LLM nem por retrieval — identificadores de história/demanda, identificadores de risco de modelo, contas AWS, identificadores de experimento, tabelas e queries de destino/inferência. Só vêm de **confirmação humana explícita** ou de **fonte estruturada confiável**. **A lista exata já deve existir num único lugar configurável no código** (foi criada na rodada anterior a partir do schema real dos artefatos). **Encontre-a e use-a** — ela é o insumo do conjunto negativo (seção 6.1).

4. **Perímetro de dados.** O IARA é interno, então presumo que consultar a base de doc interna por ele está dentro do perímetro — **mas confirme, não presuma.** Independente disso: **não envie conteúdo dos repositórios de documentação para nenhuma API externa** nesta tarefa (incluindo APIs de embedding ou de LLM de terceiros, se você pensar em usar alguma para automatizar avaliação). Se achar que precisa, pare e me pergunte.

5. **Você não define o limiar de aprovação do CI.** Você **mede** e **propõe, com justificativa**. O valor que trava o build é decisão minha e da squad.

6. **Não cace um número bonito.** Se o retrieval via IARA for ruim para as nossas queries, isso é um achado de primeira ordem — possivelmente o achado mais importante do mês. Reporte honestamente. Não ajuste o gold set para melhorar a métrica.

7. **Ferramental do repo manda.** `pyproject.toml`, lint, format, testes, convenções. Se faltar dependência, proponha antes de adicionar.

8. **Lacuna não se preenche com invenção.** Registre em `docs/M2/lacunas.md`.

Convenção de idioma: identificadores e nomes de arquivo em inglês; docstrings, comentários e documentação em **pt-BR**.

**Não faça commits.** Mudanças no working tree; eu reviso e commito.

---

## 6. Tarefas desta rodada

Ordem importa. O gold set é escrito **antes** de inspecionar os resultados do IARA, para não ser enviesado por eles.

### 6.1 — Gold set de retrieval

**Entregável:** `eval/retrieval/gold_set_retrieval.yaml` (ou o caminho que as convenções do repo indicarem), versionado.

**De onde vêm as queries — este é o coração da tarefa.** Não invente perguntas genéricas de usuário. As queries devem ser **as consultas que os nodes do nosso grafo vão de fato emitir contra o IARA**. Vá aos call sites: o que o `config_agent` precisa buscar para preencher cada campo de cada artefato? O que o módulo de governança precisa buscar para checar cada item do checklist? O que o `diagnose` precisa buscar para reconhecer um padrão de falha? **As queries derivam do schema dos artefatos e do checklist de governança, não da sua imaginação.**

**30 a 50 queries, com esta composição:**

| Tipo | Qtde aprox. | O que é | Comportamento esperado |
|---|---|---|---|
| **P0 (positivas)** | ~20 | Campos e regras que o agente vai preencher/validar. Falha aqui é bloqueante. | Recuperar o(s) chunk(s) que documentam aquilo, com score alto |
| **P1 (positivas)** | ~10 | Conceituais, jornada, doc pública. Suportam explicação ao usuário. | Recuperar, com tolerância maior |
| **Negativas** | ~10-15 | Perguntas cuja resposta **não existe na documentação**: valores concretos de conta AWS, ID de história, ID de risco de modelo, ID de experimento, tabela de destino de um projeto específico. Derive da lista da restrição 3. | **Nenhum chunk acima do nosso threshold.** A abstenção é o acerto. |
| **Ambíguas** | ~5 | Pergunta que faz sentido em múltiplos contextos (ex.: "configuração de deploy" quando há vários flavors de inferência). | Recuperar chunks de **todos** os contextos plausíveis |

**Por que o conjunto negativo é obrigatório, e por que ele é ainda mais importante com o IARA:** se o IARA **sempre** sintetiza uma resposta e sempre devolve os chunks mais parecidos (verifique isso no passo zero, item 6), então **ele nunca se abstém** — e a única barreira entre "documentação não cobre" e "o agente inventou um identificador de conta AWS" é um **corte de score do nosso lado**. Calibrar esse corte é possivelmente a entrega mais valiosa desta tarefa inteira. Sem conjunto negativo, não há como calibrá-lo.

**Ground truth: rotule por `(arquivo, seção)`, nunca por hash/id de chunk do IARA.** O índice deles pode ser reconstruído a qualquer momento. O harness resolve `(arquivo, seção)` → chunk retornado em tempo de execução, usando o metadado de origem (ou o fallback que você definiu no passo zero, item 2).

Formato sugerido (adapte às convenções do repo):

```yaml
- id: RQ-P0-001
  query: "campos obrigatórios do artefato de configuração de modelo para inferência batch"
  tier: P0
  tipo: positivo
  consumidor: config_agent          # qual node emitiria esta query
  expected:
    - doc: "<caminho relativo no repo de doc>"
      secao: "<cabeçalho da seção>"

- id: RQ-NEG-003
  query: "qual o identificador de conta AWS de destino do projeto"
  tier: P0
  tipo: negativo
  consumidor: config_agent
  expected: []                       # abstenção é o acerto
  notas: "campo da lista never-auto-fill — o retriever não pode 'ajudar'"
```

**Hold-out:** marque ~20% com `holdout: true`. Não podem ser usadas na calibração/varredura — só na medição final. Anti-overfit, não negociável.

**Viés — leia isto:** quem escreve a query e rotula o ground truth é o mesmo agente que vai avaliar o retrieval. Mitigações que você **deve** aplicar: (a) derive as queries dos call sites e do schema dos artefatos, **antes** de rodar qualquer consulta ao IARA; (b) rotule o ground truth lendo os repositórios de documentação, **não** os resultados do IARA. **Não precisa me apresentar o gold set antes de seguir — pode construir e usar. Eu valido depois.** Mas marque no próprio YAML (campo `notas`) todo rótulo em que você ficou inseguro e por quê, para eu revisar com foco.

---

### 6.2 — Harness de avaliação

**Entregável:** `eval/retrieval/evaluate.py` (ou equivalente), com CLI, chamável também dos testes.

Ele fala com a **porta de retrieval** (adapter do IARA), consome o gold set, e produz métricas.

**Cache é requisito, não otimização.** Cada consulta ao IARA deve ter sua resposta bruta persistida em disco (`eval/retrieval/cache/`, fora do versionamento se pesada), chaveada por query + parâmetros. Motivos: (a) a calibração de threshold e a análise de falhas re-pontuam os **mesmos** resultados dezenas de vezes — não faz sentido reconsultar; (b) o CI precisa rodar **sem rede**; (c) queremos poder reproduzir um resultado meses depois. **Separe claramente "consultar o IARA" de "pontuar o que o IARA devolveu".** São dois passos, e o segundo é offline e determinístico.

**Métricas mínimas, todas reportadas por tier e por tipo — agregado único esconde exatamente o que interessa:**

| Métrica | O que responde | Escopo |
|---|---|---|
| `recall@k` (hit rate) | o chunk certo está entre os top-k? | positivas |
| `MRR` | está no topo da lista ou no fim? | positivas |
| `abstention_rate` | nenhum chunk acima do threshold, quando não deveria haver? | negativas |
| `precision@k` | quanto lixo vem junto (custo de contexto e ruído para o LLM) | positivas |
| `multi_context_recall` | nas ambíguas, recuperou **todos** os contextos esperados? | ambíguas |
| **`recall@k` e `MRR` pré-rerank vs. pós-rerank** | **o rerank do IARA ajuda ou atrapalha nas nossas queries?** | positivas |
| distribuição de score (inicial e pós-rerank) | como os scores se separam entre positivas e negativas? | todas |
| latência p50/p95 | viabilidade dentro de um node do grafo | todas |

Sobre **pré vs. pós-rerank**: você tem os dois scores no retorno. Reordene os chunks pelo score inicial e calcule as métricas; reordene pelo score pós-rerank e calcule de novo. Se o rerank degradar alguma classe de query (hipótese a testar: queries com jargão do domínio e nome exato de campo/etapa), isso é acionável — ou reportamos ao time do IARA, ou passamos a usar `k` maior e filtrar do nosso lado.

Testes unitários das próprias métricas, com casos sintéticos. Precisamos confiar no medidor antes de confiar na medição.

Saída: tabela legível no stdout **e** JSON estruturado, para o CI comparar entre execuções.

---

### 6.3 — Calibração do corte de score e varredura das alavancas que existem

**Esta é a entrega central. Leia com atenção.** O escopo exato desta seção depende do quadro que você preencheu no passo zero. Faça o que se aplica ao que você descobriu; para o que não se aplica, diga por que e siga.

**(a) Curva de corte de score — obrigatório, independente de o corte ser "nosso" ou não.** O IARA devolve scores por chunk (inicial e, se existir, pós-rerank). Independentemente de o corte ser aplicado por um parâmetro do SDK ou por nós, sobre os scores retornados, a curva é a mesma. Varra o valor de corte ao longo de toda a faixa observada e, para cada valor, calcule:

- `recall@k` nas positivas P0 (quanto perdemos ao cortar);
- `abstention_rate` nas negativas (quanto ganhamos em segurança).

O resultado é uma **curva de trade-off**, e ela é o artefato principal do relatório. No relatório, deixe claro **onde** esse corte seria aplicado na prática (parâmetro do IARA vs. filtro nosso pós-consulta), conforme o passo zero. Recomende um valor, **explicitando qual erro estamos escolhendo tolerar**: cortar alto significa o agente dizer "não sei" mais vezes (fricção, mais handoff); cortar baixo significa o agente usar contexto irrelevante para preencher campo de deploy (alucinação, e é isso que a arquitetura inteira existe para impedir). **Neste projeto, o erro caro é o segundo.** Sua recomendação deve refletir isso, e deve dizer isso em voz alta.

**(b) Formulação da query — nossa alavanca mais barata e mais provável.** Compare, para as mesmas P0, formulações diferentes da mesma pergunta: linguagem natural vs. termos-chave; com vs. sem o nome exato do artefato/campo; com vs. sem o jargão do domínio. **A conclusão vira diretriz de prompt para o `config_agent` no Mês 3** — é um dos motivos de esta tarefa vir antes dele. Esta parte quase certamente é possível; priorize-a.

**(c) `top_k`** — pelo menos 3 valores (você trabalha com 8 hoje; teste abaixo e acima). Barato, faça.

**(d) Tipo de busca — semântica vs. híbrida vs. lexical**, **se o SDK permitir** (passo zero, item 1). Dado que nossas queries carregam nome exato de campo e de etapa, minha hipótese é que a híbrida ajude. Se só a semântica estiver disponível via SDK, **registre isso como limitação e como pedido potencial ao time do IARA** — e siga com o que dá.

**(e) Rerank ligado vs. desligado**, **se configurável via SDK**. Além disso, mesmo que não seja desligável, você tem os dois scores no retorno: compare `recall@k`/MRR reordenando por score inicial vs. por score pós-rerank (isto já está pedido na seção 6.2). Se o rerank degradar as queries de jargão, é achado acionável.

**(f) Alavancas de INGESTÃO — splitter, `chunk_size`, `chunk_overlap`, metadados — SÓ SE valer o custo.** Mudar qualquer uma provavelmente exige **re-ingerir a KB** (confirme no passo zero). Portanto:
   - **Não faça uma varredura ampla de ingestão nesta rodada.** É caro e arriscado (re-ingestão altera a base que o resto do trabalho usa).
   - **Faça no máximo UM experimento de ingestão deliberado, e só se a análise de falhas apontar a ingestão como gargalo dominante** — por exemplo, se muitas falhas P0 forem "chunk partido", teste um `chunk_size`/`overlap` maior ou o splitter de markdown, numa **KB separada de teste**, nunca sobre a KB principal.
   - Se você mexer na ingestão, **isole**: KB de teste com nome distinto, e a KB principal do projeto permanece intocada. Deixe registrado como reverter.
   - Se a ingestão atual já for razoável, **recomende** ajustes no relatório em vez de executá-los. A decisão de re-ingerir a base do projeto é minha.

Se alguma alavanca que eu supus não existir via SDK, **diga que não existe e siga** — não simule.

**Use apenas queries não-holdout** na calibração e na varredura. A configuração recomendada é medida no hold-out ao final, e é esse número que vai para o relatório como resultado.

---

### 6.4 — Chunks vs. resposta gerada: uma recomendação com dado

O script tem dois modos: com `--retrieve-only` volta só os chunks; sem a flag, volta **também uma resposta sintetizada por um LLM** a partir dos chunks. Existe uma decisão de arquitetura em aberto: o nosso agente deve consumir os **chunks** (modo `--retrieve-only`, raciocinando por conta própria sob o nosso controle de não-invenção) ou a **resposta gerada** do IARA?

**Minha inclinação é chunks** — a resposta gerada é um segundo LLM, fora do nosso controle e da nossa auditoria, no meio de um caminho que termina em artefato de deploy num ambiente bancário. Mas isso deve ser decidido com evidência, não com inclinação.

**O que você faz:** para as queries **negativas**, rode o script **sem** `--retrieve-only` e registre **o que a resposta gerada diz**. Se ela responder com confiança a uma pergunta cuja resposta não existe na documentação — se ela "inventar" um identificador, um valor, um procedimento — isso é evidência direta e citável de que consumir a resposta gerada é perigoso para este projeto, e fecha a questão. Se ela se abstiver corretamente ("não encontrei essa informação"), também é informação valiosa e muda o desenho.

Toda a avaliação de retrieval das seções anteriores usa `--retrieve-only`. Esta seção é o único ponto em que o modo com resposta gerada é exercitado, e só nas negativas.

Não avalie a qualidade da resposta gerada nas positivas (fora de escopo desta rodada). O ponto aqui é só o comportamento sob ausência de informação.

**Entregável:** seção do relatório com o veredito e as evidências.

---

### 6.5 — Análise de falhas, com a coluna de responsabilidade

**Entregável:** cada query P0 que falhou, classificada por causa raiz **e por quem age**. Isto vale mais que qualquer métrica agregada.

| Categoria | Sintoma | Quem age |
|---|---|---|
| **Lacuna documental real** | A informação não está na documentação da IU Lotus | **Nós** — vira pergunta para a squad, item em `lacunas.md`. Não é bug. |
| **Formulação de query** | O chunk certo aparece com outra formulação da mesma pergunta | **Nós** — vira diretriz de prompt para o M3 (seção 6.3b) |
| **Corte de score mal calibrado** | O chunk certo veio, mas abaixo do corte (ou lixo veio acima dele) | **Nós** — entra na curva da 6.3a |
| **Chunk partido / má fragmentação** | A informação existe mas ficou dividida entre chunks, ou o chunk mistura assuntos | **Provavelmente nós** — a ingestão é nossa; vira recomendação de ajuste de splitter/`chunk_size` (seção 6.3f). Só é do IARA se o splitter que precisamos não existir. |
| **Metadado de origem ausente/errado** | O chunk não identifica de onde veio | **Nós** — a ingestão é nossa; corrigir no `sync_to_iara.py` |
| **Rerank degradou** | O chunk certo estava bem posicionado no score inicial e caiu após rerank, e o rerank não é desligável por nós | **Time do IARA** — reportar com evidência. Se for desligável por nós, é nossa alavanca. |
| **Limitação fixa do IARA** | Falta um recurso que precisaríamos (ex.: busca híbrida indisponível por SDK) | **Time do IARA** — reportar como pedido |

Se aparecer uma categoria nova, crie-a e explique. **O ponto desta tabela é que, com a ingestão sendo nossa, a maioria das falhas provavelmente é acionável por nós — não terceirize por reflexo.**

---

### 6.6 — CI

- Teste que roda o gold set **contra o cache** (sem rede) e falha se `recall@k` (P0) ou `abstention_rate` caírem abaixo do limiar de config.
- **Limiar em config, default seguro:** modo *warning* enquanto eu não aprovar o valor. Não trave o build com um número que você escolheu sozinho.
- Um alvo separado, atrás de marker, que consulta o IARA de verdade e **atualiza o cache** — para rodar sob demanda, não no CI.
- Determinístico. Sem rede no caminho padrão.

---

## 7. Definição de pronto

- [ ] Levantamento do IARA (seção 4) entregue e reportado **antes** de qualquer implementação, incluindo: alavancas configuráveis reais, metadados de origem no retorno, o que está indexado, e se o IARA se abstém.
- [ ] Adapter do IARA implementado atrás da **porta de retrieval existente**; nenhuma interface nova; nenhum node chamando o SDK do IARA direto.
- [ ] `gold_set_retrieval.yaml` com ≥ 30 queries (P0, P1, **negativas**, ambíguas), ground truth por `(arquivo, seção)`, ~20% `holdout`.
- [ ] Queries derivadas dos **call sites e do schema dos artefatos** — e você me explica como derivou.
- [ ] Conjunto negativo construído a partir da lista real de campos "nunca auto-preencher" do código.
- [ ] Harness com cache em disco; passo de consulta separado do passo de pontuação; pontuação offline e determinística.
- [ ] Métricas da 6.2 por tier e por tipo, incluindo **pré-rerank vs. pós-rerank** e distribuição de scores.
- [ ] Testes unitários das métricas.
- [ ] **Curva de trade-off threshold × (recall, abstenção)** com valor recomendado e justificativa explícita de qual erro escolhemos tolerar.
- [ ] Varredura das alavancas que existem (incluindo **formulação de query**), medida no hold-out.
- [ ] Veredito **chunks vs. resposta gerada** (6.4), com evidência do comportamento do IARA nas negativas.
- [ ] Falhas P0 classificadas por causa raiz **e por responsável** (6.5).
- [ ] Gate de CI com limiar em config e default que **não trava o build** sem minha aprovação.
- [ ] Nenhum conteúdo de documentação enviado a API externa (afirme explicitamente no relatório).
- [ ] Lint/format passando; suíte verde e determinística, sem rede.
- [ ] `docs/M2/M2-T09_resultado_testes_retrieval.md`: metodologia, contrato real do IARA, métricas no hold-out, curva de threshold, config recomendada, veredito chunks vs. resposta, análise de falhas com responsável, limiar proposto para o CI, e **o que não foi possível validar**.
- [ ] `docs/M2/lacunas.md` atualizado: lacunas documentais descobertas + questões abertas sobre o IARA (o que é configurável por SDK vs. só por portal, indexação, atualização, filtros).
- [ ] **`docs/M2/M2-T09_pontos_de_validacao.md`** — um único documento consolidando **tudo que precisa da minha validação**: rótulos incertos do gold set, decisões que você tomou sozinho e que eu deveria confirmar, o valor de threshold proposto, o veredito chunks vs. resposta, e qualquer suposição sobre o IARA que você não conseguiu confirmar 100% no código. Eu não vou acompanhar passo a passo — este documento é como eu reviso no fim. Seja específico: "confirmar rótulo da RQ-P0-007" é útil; "revisar o gold set" não é.
- [ ] **Sem commits.** Working tree.

---

## 8. O que NÃO fazer nesta rodada

- Não implementar retrieval próprio, índice próprio, embeddings próprios **fora do IARA**. **O RAG é o IARA.** Ajustar a ingestão da nossa KB dentro do IARA (splitter, chunk_size, metadados via `sync_to_iara.py`) é legítimo e é nosso — mas construir um vector store paralelo, um BM25 caseiro, ou um pipeline de embeddings fora do IARA está fora de escopo. Se o IARA for insuficiente num ponto que não conseguimos configurar, isso é achado a reportar, não convite para reimplementar.
- Não chamar o SDK do IARA de dentro de nenhum node. Sempre pela porta.
- Não confundir SDK do IARA com SDK da IU Lotus. São coisas diferentes, com propósitos diferentes.
- Não enviar documentação (pública ou interna) para APIs externas.
- Não escolher o limiar do CI de forma que o resultado atual passe.
- Não ajustar o gold set depois de ver os resultados para melhorar a métrica. Se um rótulo estiver errado, corrija e **diga que corrigiu, e por quê**.
- Não usar queries de hold-out na calibração ou na varredura.
- Não implementar query expansion, HyDE, reranker próprio ou qualquer sofisticação. Se a análise sugerir que ajudaria, **recomende no relatório** — não implemente.
- Não tocar nos nodes do grafo nem no roteamento. Esta tarefa observa o retrieval; não muda o fluxo.
- Não inventar nomes de campo, artefato, seção ou parâmetro do IARA/IU Lotus. Se não confirmou no código ou na doc, é lacuna.

---

**Comece pelo levantamento da seção 4. Depois me devolva: o contrato real do IARA, o que encontrou de divergente deste briefing, o plano de execução, as premissas e as dúvidas. Não escreva código ainda.**
