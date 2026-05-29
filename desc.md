# Discovery: DeployOps Agentic para a jornada de deploy de modelos no IU Lotus

> **Status:** em validação com squad  
> **Tipo:** Discovery de arquitetura  
> **Autor(es):** [a preencher]  
> **Data:** [a preencher]  
> **Decisão futura associada:** ADR a ser produzido após validação

---

## 1. Objetivo

Investigar a viabilidade técnica de um copiloto agentic para conduzir a jornada de deploy de modelos no IU Lotus (etapa 09 da documentação pública), reduzindo o esforço manual de preparação de artefatos pré-deploy sem comprometer a governança da plataforma (MRM, FAARM, GMUD, allowlist de ambientes, aprovação humana).

## 2. Contexto e motivação

A jornada oficial de deploy é bem documentada, mas concentra esforço repetitivo do usuário em pontos onde um LLM bem ancorado pode acelerar:

- Preenchimento de `model.yml` (esqueleto vazio com flavor, instância, schedule, lifecycle, tags)
- Construção do payload de `config_deploy()` com `inference_query`, `target_query`, placeholders, primary keys e contas AWS
- Configuração de `expressions.yml` (CASE-WHEN para cálculo pós-inferência — usado por praticamente todos os modelos do Itaú)
- Validação de pré-requisitos (MRM, FAARM, baselines) hoje feita manualmente
- Diagnóstico de falhas pós-deploy nos cinco padrões catalogados pela documentação

Esses pontos são candidatos naturais a copiloto LLM, desde que opere dentro de limites de governança claros.

## 3. O que queremos descobrir

1. Um agente LLM consegue conduzir essa jornada de modo seguro, sem violar governança?
2. Qual o nível adequado de autonomia (chatbot, copiloto, executor)?
3. Qual a arquitetura mínima viável para uma pessoa em 8 meses?
4. Quais validações e bloqueios determinísticos são obrigatórios?
5. O acionamento real do deploy via SDK é possível sob controle humano?

## 4. Decisão que este Discovery apoia

Antes de gerar ADR/RFC e iniciar a construção do MVP, validar com a squad:

- A arquitetura proposta atende aos critérios eliminatórios (aderência ao IU Lotus, governança, segurança, viabilidade)
- O escopo é factível para uma pessoa em 8 meses
- As premissas de acesso (SDK, repositório, ambiente `analytics`) são realistas no horizonte do projeto

## 5. Conhecimento prévio (fatos documentados)

- Deploy é orquestrado pelo SDK via `lotus.deploy_project(env=...)`, em cascata `analytics → dev → hom → prod`
- `analytics` é sandbox consumer com dados reais, sem impacto produtivo
- Produção exige `story_id` e gera GMUD com aprovação manual como gate final
- `{{IULOTUS_DATREF}}` é placeholder oficial para datas em queries operacionais; datas hardcoded devem ser evitadas
- A documentação oficial recomenda inferência local pré-deploy (validação no Studio em ~30s vs. 10–15min por iteração no GitHub Actions)
- A documentação cataloga cinco padrões nomeados de falha pós-deploy: `LoadFeatures` (table not found / query vazia), `LoadModel` (experiment not found), `Predict` (KeyError), `WriteResults` (permissão)
- O SDK encapsula PR, GitHub Actions e GMUD por baixo — não é necessário (nem desejável) abrir PR direto no MVP

## 6. Lacunas identificadas

| Lacuna | Impacto |
|---|---|
| Assinatura e contrato exato de `deploy_project()` e `config_deploy()` na versão em uso | SDK Wrapper depende disso |
| Schema oficial versionado de `model.yml` e `expressions.yml` | Validators determinísticos dependem disso |
| Existência e escopo do agente SDK/StackSpot eventualmente existente | Afeta decisão de construir paralelo vs. evoluir o existente |
| Disponibilidade de dry-run nativo no SDK | Afeta estratégia de testes sem deploy real |
| APIs de MRM, FAARM, baselines, TAAC | Define se checklist será via API ou mock/manual |
| Política para envio de queries reais a prompts LLM | Afeta arquitetura de segurança e sanitização |
| Repositório e modelo disponíveis para PoC | Afeta cronograma do MVP |

## 7. Abordagens avaliadas

| Modo | Descrição | Avaliação | Decisão |
|---|---|---|---|
| M0 | Chatbot/RAG sem execução | Seguro, mas não aciona deploy | Rejeitado |
| M1 | Tool abre PR direto no repositório | Bom controle, mas duplica o que o SDK já encapsula | Futuro, se justificado |
| M2 | SDK Wrapper com aprovação humana e allowlist `analytics` | Equilibra execução e governança | **Escolhido para MVP** |
| M3 | Workflow pré-aprovado com gates automáticos | Mais maduro, exige governança formal estabelecida | Futuro |
| M4 | Runbooks restritos para rollback/rerun | Útil, mas envolve operações sensíveis | Futuro |
| M5 | Autonomia ampla, sem aprovação humana | Viola governança e segurança | Rejeitado |

## 8. Recomendação

Construir um **DeployOps Agentic enxuto** sobre **LangGraph 1.0 stable** (lançamento outubro/2025), com três camadas:

**Camada agentic (LangGraph)**
- Orquestrador DeployOps (state machine com edges condicionais e loops de retorno)
- Agente de Configuração para `model.yml`, payload de `config_deploy()` e `expressions.yml`
- Módulo de Governança aplicando regras lidas da documentação

**Camada determinística**
- Validators de YAML (pydantic + jsonschema), SQL (SQLGlot), placeholders, campos críticos
- Diff revisável antes da aprovação
- Audit log JSONL apoiado no checkpointer do LangGraph, com sanitização de dados sensíveis
- Handoff estruturado para lacunas insolúveis

**Camada IU Lotus existente**
- SDK Wrapper seguro que aciona `lotus.deploy_project(env="analytics")` sob aprovação humana
- SDK IU Lotus inalterado

**Decisões arquiteturais centrais:**

- MVP restrito a `analytics` batch; `dev`, `hom`, `prod`, GMUD ficam para fases intermediária e futura
- Aprovação humana obrigatória antes de qualquer chamada ao SDK (via `interrupt()` do LangGraph)
- Allowlist de ambiente codificada no SDK Wrapper (somente `analytics` no MVP)
- Loop de retorno após rejeição na aprovação (até 3 iterações antes de virar handoff)
- Condução de inferência local pré-deploy via gate humano com snippet pronto (agente instrui, usuário executa, agente aguarda confirmação)
- `expressions.yml` está no escopo central do Agente de Configuração; `config.yml` fica fora (é setup uma vez por repositório, não está no hot path)
- Parser estruturado do retorno do SDK + diagnóstico básico reconhecendo os cinco padrões documentados de falha

## 9. Riscos e trade-offs

| Risco | Mitigação |
|---|---|
| Acesso ao SDK não liberado para o mês 6 | SDK Wrapper em modo mock/dry-run fiel; piloto simulado se necessário |
| LangGraph travar no spike inicial (M1) | Fallback para Python puro com state machine simples; até 1 semana absorvida pelo buffer |
| Schemas oficiais indisponíveis | Schemas mínimos derivados da documentação + revisão pela squad antes de validators ficarem rígidos |
| Escopo crescer durante a construção | Backlog futuro explícito; ADR de escopo referenciado em todas as conversas |
| Lacuna sobre agente SDK/StackSpot existente | Tratado como pergunta crítica à squad; decisão de separação só após confirmação |

**Trade-off principal:** aderência ao SDK (e à esteira IU Lotus oficial) versus controle fino sobre PRs e workflow. No MVP, optamos por aderência — duplicar o que o SDK já encapsula é redundante e arriscado.

## 10. Próximos passos

1. Apresentar este Discovery em reunião curta com a squad
2. Coletar respostas para as ~15–20 perguntas críticas (acessos, schemas, escopo, política de dados em prompts)
3. Ajustar este Discovery conforme retorno e arquivar a versão validada
4. Gerar ADR-001 (stack tecnológico, incluindo LangGraph) e ADR-002 (escopo do MVP)
5. Executar spike de LangGraph (~1 semana) para validar o framework antes de comprometer o cronograma inteiro
6. Iniciar M1 do MVP conforme cronograma de 8 meses já aprovado

## 11. Participantes

- [a preencher]

## 12. Referências

- Etapa 09 — Deploy (documentação pública consolidada do IU Lotus)
- Documentação interna IU Lotus (categorias DeployOps, Componentes, Discovery Geral)
- Relatórios consolidados das rodadas 1 e 2 da pesquisa arquitetural do projeto
- LangGraph 1.0 stable (lançado em outubro/2025)
- Mermaid `mvp_minimo.svg` — planejamento macro aprovado
- Documento `decomposicao_mvp_deployops.docx` — decomposição de tarefas em 8 meses
