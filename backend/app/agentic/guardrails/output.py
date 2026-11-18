"""Guardrail de saída (grounding determinístico): a resposta final só pode citar evidências que
alguma tool realmente devolveu nesta execução, e só pode referenciar propostas que foram criadas."""

from app.agentic.tools.base import ToolContext


def check_final(final: dict, ctx: ToolContext) -> list[str]:
    problems = []
    kind = final.get("kind")
    cited = final.get("evidence") or []
    seen = ctx.evidence_seen
    seen_sources = {ev.get("source_id") for ev in seen.values()}
    for ev in cited:
        key = f"{ev.get('source_id')}#{ev.get('section', '') or ''}"
        if key not in seen and not (not ev.get("section") and ev.get("source_id") in seen_sources):
            problems.append(f"evidence {ev.get('source_id')} §{ev.get('section')} was not returned by any tool in this run")
    if kind == "answer" and not cited:
        problems.append("kind=answer requires at least one evidence item from the tools; otherwise use kind=abstain")
    for pid in final.get("proposal_ids") or []:
        if pid not in ctx.proposals_created:
            problems.append(f"proposal {pid} was not created in this run")
    if kind == "action_proposed" and not (final.get("proposal_ids") or ctx.proposals_created):
        problems.append("kind=action_proposed requires a proposal created by a tool")
    if kind == "escalated" and not ctx.support_requests:
        problems.append("kind=escalated requires calling escalate_to_organizer first")
    return problems
