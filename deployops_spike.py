"""
Spike LangGraph 1.0 - DeployOps Agent (IU Lotus) - versao interativa
====================================================================

Objetivo do spike: provar o padrao minimo de human-in-the-loop que sustenta
a arquitetura DeployOps -> "o agente PREPARA o plano de deploy, um humano APROVA,
e so depois o deploy e despachado". Nada e executado de verdade aqui.

Mapeamento direto ao diagrama de arquitetura (camada agentic):
    node 1  prepare_deploy_plan  -> Agente de Configuracao + Validacoes deterministicas
    node 2  human_approval       -> "Aprovacao humana / review do plano" (o losango)
    node 3  dispatch_deploy      -> SDK Wrapper seguro (aqui em modo dry-run/mock)

NESTA VERSAO o gate humano e INTERATIVO: o grafo pausa de verdade e pergunta
no terminal se aprova ou nao. Use para demonstrar ao vivo na reuniao.

IMPORTANTE (escopo de pesquisa / copiloto, nao executor autonomo):
- Este spike NAO chama lotus.deploy_project nem nenhuma API real da IU Lotus.
- O "despacho" e simulado (dry-run). A ligacao com o SDK real fica para depois,
  sempre atras do SDK Wrapper com allowlist e somente em env="analytics" no MVP.
- Os nomes de campos sao ilustrativos e devem ser conferidos na fonte oficial.

Requisitos:
    pip install "langgraph>=1.0"

Como rodar (demo ao vivo):
    python deployops_spike.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, TypedDict

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
# Demonstracao INTERATIVA - gate humano ao vivo no terminal
# ---------------------------------------------------------------------------
SAMPLE_REQUEST = {
    "model_name": "classificacao_propensao",
    "env": "analytics",          # MVP: apenas sandbox analytics
    "repo_name": "itau-mr7-infra-meu-modelo",
    "story_id": "",              # vazio fora de prod, e o esperado
}


def _print_plan_for_review(payload: dict) -> None:
    """Mostra o plano de forma legivel para o revisor humano na sala."""
    plan = payload["deploy_plan"]
    print("\n" + "=" * 64)
    print("  O AGENTE PREPAROU UM PLANO DE DEPLOY - AGUARDANDO REVISAO HUMANA")
    print("=" * 64)
    print(f"  modelo       : {plan.get('model_name')}")
    print(f"  ambiente     : {plan.get('env')}")
    print(f"  repositorio  : {plan.get('repo_name')}")
    print(f"  story_id     : {plan.get('story_id') or '(vazio - esperado fora de prod)'}")
    print(f"  validacao OK : {payload['validation_passed']}")
    if payload["validation_errors"]:
        print(f"  erros        : {payload['validation_errors']}")
    print("-" * 64)


def run_interactive() -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": "demo-interativa"}}

    # 1a invocacao: roda ate o interrupt e PAUSA de verdade.
    first = graph.invoke({"deploy_request": SAMPLE_REQUEST}, config=config)

    if "__interrupt__" not in first:
        print("Fluxo terminou sem pausa - verifique as validacoes.")
        return

    payload = first["__interrupt__"][0].value
    _print_plan_for_review(payload)

    # >>> GATE HUMANO AO VIVO <<<
    # Aqui o grafo esta congelado no checkpointer, esperando a decisao.
    answer = input("  Aprovar este deploy? (s/n): ").strip().lower()
    approved = answer in ("s", "sim", "y", "yes")
    reviewer = input("  Seu nome (revisor): ").strip() or "desconhecido"
    notes = input("  Observacao (enter para pular): ").strip()

    decision = {
        "decision": "approved" if approved else "rejected",
        "reviewer": reviewer,
        "notes": notes,
    }

    # 2a invocacao: retoma o grafo do node de aprovacao com a decisao digitada agora.
    final = graph.invoke(Command(resume=decision), config=config)

    print("\n" + "=" * 64)
    print(f"  DECISAO: {final.get('approval_decision', '').upper()} por {final.get('approval_reviewer')}")
    if final.get("deploy_result"):
        r = final["deploy_result"]
        print(f"  DESPACHO ({r['mode']}): {r['status']} em env={r['env']}")
        print("  (dry-run - NENHUM deploy real foi executado)")
    else:
        print("  NENHUM DESPACHO - fluxo encerrado pela rejeicao do revisor.")
    print(f"  Registros de auditoria gravados: {len(final.get('audit_log', []))}")
    print("=" * 64)


if __name__ == "__main__":
    run_interactive()
