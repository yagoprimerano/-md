"""
Spike LangGraph 1.0 - DeployOps Agent (IU Lotus)
=================================================

Objetivo do spike: provar o padrao minimo de human-in-the-loop que sustenta
a arquitetura DeployOps -> "o agente PREPARA o plano de deploy, um humano APROVA,
e so depois o deploy e despachado". Nada e executado de verdade aqui.

Mapeamento direto ao diagrama de arquitetura (camada agentic):
    node 1  prepare_deploy_plan  -> Agente de Configuracao + Validacoes deterministicas
    node 2  human_approval       -> "Aprovacao humana / review do plano" (o losango)
    node 3  dispatch_deploy      -> SDK Wrapper seguro (aqui em modo dry-run/mock)

IMPORTANTE (escopo de pesquisa / copiloto, nao executor autonomo):
- Este spike NAO chama lotus.deploy_project nem nenhuma API real da IU Lotus.
- O "despacho" e simulado (dry-run). A ligacao com o SDK real fica para depois,
  sempre atras do SDK Wrapper com allowlist e somente em env="analytics" no MVP.
- Os nomes de campos (story_id, account_aws_number etc.) sao ilustrativos e devem
  ser conferidos na fonte oficial antes de qualquer uso operacional.

Requisitos:
    pip install "langgraph>=1.0"

Como rodar:
    python deployops_spike.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

# InMemorySaver e o nome canonico no LangGraph 1.x; mantemos fallback por seguranca.
try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # versoes mais antigas expunham como MemorySaver
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver


# ---------------------------------------------------------------------------
# Estado compartilhado do grafo
# ---------------------------------------------------------------------------
class DeployState(TypedDict, total=False):
    # Entrada vinda do usuario tecnico (Data Scientist / MLOps)
    deploy_request: dict

    # Produzido pelo node 1
    deploy_plan: dict
    validation_passed: bool
    validation_errors: list[str]

    # Produzido pelo node 2 (decisao humana via interrupt)
    approval_decision: str          # "approved" | "rejected"
    approval_reviewer: str
    approval_notes: str

    # Produzido pelo node 3
    deploy_result: dict

    # Trilha de auditoria acumulada ao longo do fluxo (vira o Audit log JSONL)
    audit_log: list[dict]


def _audit(state: DeployState, event: str, detail: dict) -> list[dict]:
    """Acrescenta um registro de auditoria preservando o historico ja existente."""
    log = list(state.get("audit_log", []))
    log.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "detail": detail,
        }
    )
    return log


# ---------------------------------------------------------------------------
# NODE 1 - prepare_deploy_plan
# Monta o plano de deploy e roda validacoes deterministicas (MOCK).
# ---------------------------------------------------------------------------
def prepare_deploy_plan(state: DeployState) -> DeployState:
    req = state.get("deploy_request", {})

    # Campos que, por governanca, NUNCA sao auto-preenchidos pelo agente.
    # No spike apenas verificamos presenca; nunca inventamos valor.
    required_fields = ["model_name", "env", "repo_name"]
    errors: list[str] = [f"campo obrigatorio ausente: {f}" for f in required_fields if not req.get(f)]

    # Regra de failsafe: no MVP so permitimos o sandbox analytics.
    env = req.get("env")
    if env and env != "analytics":
        errors.append(f"env '{env}' bloqueado no MVP - apenas 'analytics' permitido")

    # story_id e obrigatorio em prod; aqui reforcamos que prod esta fora de escopo.
    if env == "prod" and not req.get("story_id"):
        errors.append("env=prod exige story_id (e esta fora do escopo do MVP)")

    # Monta o "diff revisavel" que o humano vai ler no review.
    plan = {
        "model_name": req.get("model_name"),
        "env": env,
        "repo_name": req.get("repo_name"),
        "story_id": req.get("story_id"),  # vazio fora de prod, e esperado
        "deterministic_checks": {
            "fields_present": not any("ausente" in e for e in errors),
            "env_allowed": env == "analytics",
        },
    }

    return {
        "deploy_plan": plan,
        "validation_passed": len(errors) == 0,
        "validation_errors": errors,
        "audit_log": _audit(state, "plan_prepared", {"plan": plan, "errors": errors}),
    }


# ---------------------------------------------------------------------------
# NODE 2 - human_approval (UNICO interrupt do grafo)
# Pausa a execucao e devolve o plano para revisao humana.
# ---------------------------------------------------------------------------
def human_approval(state: DeployState) -> Command[Literal["dispatch_deploy", "__end__"]]:
    # O interrupt fica no inicio do node: ao resumir, o LangGraph re-executa o node
    # desde o comeco, entao mantemos tudo antes do interrupt idempotente.
    decision = interrupt(
        {
            "message": "Revise o plano de deploy antes de despachar.",
            "deploy_plan": state.get("deploy_plan"),
            "validation_passed": state.get("validation_passed"),
            "validation_errors": state.get("validation_errors", []),
            # O cliente humano deve responder com algo como:
            #   {"decision": "approved"|"rejected", "reviewer": "...", "notes": "..."}
        }
    )

    approved = isinstance(decision, dict) and decision.get("decision") == "approved"
    reviewer = (decision or {}).get("reviewer", "desconhecido")
    notes = (decision or {}).get("notes", "")

    update: DeployState = {
        "approval_decision": "approved" if approved else "rejected",
        "approval_reviewer": reviewer,
        "approval_notes": notes,
        "audit_log": _audit(
            state,
            "human_decision",
            {"decision": "approved" if approved else "rejected", "reviewer": reviewer},
        ),
    }

    # Roteamento condicionado a decisao humana:
    # aprovado -> despacha; rejeitado -> encerra (sem tocar em nada).
    goto = "dispatch_deploy" if approved else END
    return Command(goto=goto, update=update)


# ---------------------------------------------------------------------------
# NODE 3 - dispatch_deploy (MOCK / dry-run)
# So roda se houver aprovacao humana. Nao chama o SDK real.
# ---------------------------------------------------------------------------
def dispatch_deploy(state: DeployState) -> DeployState:
    plan = state.get("deploy_plan", {})

    # ---- AQUI seria o unico ponto de integracao real, no futuro ----
    # Atras do SDK Wrapper seguro, com allowlist e env="analytics":
    #   result = lotus.deploy_project(repo_name=plan["repo_name"], env=plan["env"])
    # No spike, apenas simulamos um retorno no formato esperado.
    result = {
        "mode": "DRY_RUN",  # nunca um deploy real neste spike
        "status": "simulated_success",
        "model_name": plan.get("model_name"),
        "env": plan.get("env"),
        "workflow_url": "https://example.invalid/dry-run",  # placeholder, NAO e URL real
    }

    return {
        "deploy_result": result,
        "audit_log": _audit(state, "deploy_dispatched", {"result": result}),
    }


# ---------------------------------------------------------------------------
# Montagem do grafo
# ---------------------------------------------------------------------------
def build_graph():
    builder = StateGraph(DeployState)

    builder.add_node("prepare_deploy_plan", prepare_deploy_plan)
    builder.add_node("human_approval", human_approval)
    builder.add_node("dispatch_deploy", dispatch_deploy)

    builder.add_edge(START, "prepare_deploy_plan")
    builder.add_edge("prepare_deploy_plan", "human_approval")
    # human_approval roteia dinamicamente (Command), entao nao adicionamos edge fixa de saida.
    builder.add_edge("dispatch_deploy", END)

    # O checkpointer e OBRIGATORIO para o interrupt funcionar (persiste o estado pausado).
    checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Demonstracao: fluxo aprovado e fluxo rejeitado
# ---------------------------------------------------------------------------
def _run_demo(request: dict, human_decision: dict, thread_id: str) -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n=== Thread '{thread_id}' | decisao simulada: {human_decision['decision']} ===")

    # 1a invocacao: roda ate o interrupt e pausa.
    first = graph.invoke({"deploy_request": request}, config=config)

    if "__interrupt__" in first:
        payload = first["__interrupt__"][0].value
        print("PAUSOU para aprovacao humana. Plano em revisao:")
        print(f"  validacao_ok = {payload['validation_passed']}")
        print(f"  erros        = {payload['validation_errors']}")
        print(f"  plano        = {payload['deploy_plan']}")

    # 2a invocacao: humano responde -> grafo resume do node de aprovacao.
    final = graph.invoke(Command(resume=human_decision), config=config)

    print(f"Decisao registrada: {final.get('approval_decision')} por {final.get('approval_reviewer')}")
    if final.get("deploy_result"):
        print(f"Resultado do despacho (dry-run): {final['deploy_result']}")
    else:
        print("Nenhum despacho (fluxo encerrado pela rejeicao).")
    print(f"Registros de auditoria: {len(final.get('audit_log', []))}")


if __name__ == "__main__":
    sample_request = {
        "model_name": "classificacao_propensao",
        "env": "analytics",          # MVP: apenas sandbox analytics
        "repo_name": "itau-mr7-infra-meu-modelo",
        "story_id": "",              # vazio fora de prod, e o esperado
    }

    # Cenario 1: humano aprova -> despacho (dry-run) acontece.
    _run_demo(
        request=sample_request,
        human_decision={"decision": "approved", "reviewer": "yago", "notes": "ok analytics"},
        thread_id="demo-aprovado",
    )

    # Cenario 2: humano rejeita -> grafo encerra sem despachar nada.
    _run_demo(
        request=sample_request,
        human_decision={"decision": "rejected", "reviewer": "yago", "notes": "rever query"},
        thread_id="demo-rejeitado",
    )
