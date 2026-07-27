# PROMPT 09 — gerar 01_STATUS_VS_PLANO.md (rode por último)

Cole no Claude Code, no repositório `itau-rs7-dep-iu-lotus-sdk`, DEPOIS de já ter criado a pasta `docs/planejamento_inicial/`.

---

Contexto: a pasta `docs/planejamento_inicial/` deste repo contém o PLANEJAMENTO ORIGINAL do DeployOps Agentic (fase de discovery/desenho, anterior à implementação): arquitetura do MVP (`arquitetura_mvp_minimo.md`), diagrama do fluxo (`mvp_minimo.md`), decomposição/cronograma (`decomposicao_mvp_deployops.md`), rodadas de pesquisa comparando Claude e GPT (`claude-new-round1.md`, `gpt-new-round1.md`, `claude-new-round2.md`, `gpt-new-round2.md`) e o relatório final consolidado (`relatorio-final.md`). Há um índice em `docs/planejamento_inicial/00_LEIA-ME.md`.

Status desses arquivos: são histórico e direção, NÃO especificação vigente. A fonte de verdade é o estado ATUAL deste repositório — código, testes, ADRs e docs de milestone (`docs/M*`). Em qualquer conflito entre o planejamento e o que está implementado, o REPOSITÓRIO vence.

Tarefa: leia (1) `docs/planejamento_inicial/00_LEIA-ME.md` e os arquivos de plano relevantes citados nele, e (2) o estado atual do repo — grafo LangGraph, nodes, estado tipado, audit log, `policy/approval_policy.py`, adapters de retrieval, ADRs, `docs/M*`. Depois CRIE um arquivo novo: `docs/planejamento_inicial/01_STATUS_VS_PLANO.md`.

Esse arquivo deve mapear, ponto a ponto, onde a implementação SEGUIU o plano inicial e onde DIVERGIU dele, cobrindo pelo menos:
- framework / orquestração;
- nodes do grafo;
- HITL / aprovação humana (incluindo fast-path);
- validators determinísticos;
- SDK Wrapper e allowlist de ambiente;
- RAG / retrieval (IARA);
- audit log;
- escopo (o que entrou / saiu vs. a decomposição).

Para cada item, marque `[FATO repo]` quando puder apontar arquivo/símbolo específico, e `[INFERÊNCIA]` quando estiver deduzindo. Onde o plano cita coisas já descartadas (OPA/Conftest, Step Functions, Temporal, KServe, StackSpot, Feature Store, MLflow stages), confirme contra o repo e registre o status real.

Restrições:
- NÃO altere os 8 arquivos de plano nem o `00_LEIA-ME.md`. Só CRIE o `01_STATUS_VS_PLANO.md`.
- A documentação oficial da IU Lotus está nos repos irmãos `../itau-rs7-doc-iulotus/docs/` (pública) e `../itau-mr7-doc-documentacao-interna/docs/` (interna); a doc do IARA em `../itau-kk7-doc-iara-gen-ai/docs/`. Prefira essas fontes; nenhuma cópia OCR foi trazida para esta pasta.
- Comece confirmando que a pasta `docs/planejamento_inicial/` tem os 9 arquivos esperados (índice + 8); se faltar algo, reporte antes de prosseguir.
- Prosa e comentários em PT-BR.
