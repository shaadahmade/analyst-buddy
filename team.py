import contextvars
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import pii
from agent import Stopped, ask, build_agent, goal_change_problem, make_llm, preload

MAX_ANALYSTS = 3
ANALYST_STEPS = 6
VERIFIER_STEPS = 6
log = logging.getLogger("team")


@dataclass
class TeamContext:
    tenant: object
    data: dict
    files: list
    chart_dir: Path
    llm: object = None


class GoalChange(BaseModel):
    action: Literal["add", "update", "remove"]
    goal: str = Field(description="the new goal, or the existing goal's exact text for update/remove")
    new_goal: str = Field(default="", description="the new wording, only for update")


class Plan(BaseModel):
    mode: Literal["direct", "team"] = Field(description="direct for a simple lookup or a single figure; team for why, "
                                                        "compare, drivers, trends or several parts")
    reason: str = Field(description="one short sentence")
    subquestions: list[str] = Field(default_factory=list, description="2 or 3 independent analysis questions when mode is team")
    goal_changes: list[GoalChange] = Field(default_factory=list, description="only when the user states a business target or "
                                                                             "asks to add, change or remove a goal")


class Check(BaseModel):
    claim: str = Field(description="the number as an analyst stated it, with what it measures")
    recomputed: str = Field(description="the value the verifier got with its own code, or 'not checked'")
    ok: bool = Field(description="true if the recomputed value matches within rounding")


class Verdict(BaseModel):
    checks: list[Check] = Field(default_factory=list)


SUPERVISOR = """You are the supervisor of a team of data analyst agents. Decide how to answer the user's question.
Pick "direct" for simple lookups, single figures, definitions, small talk or follow-ups that need one quick check.
Pick "team" when the question asks why something changed, compares groups, looks for drivers, or has several parts.
For "team", write 2 or {max} sub-questions that analysts can work on independently and in parallel, each specific
(name the metric, the breakdown and the period), together covering everything the user asked.

Data available:
{overview}

Notes from the data agent about the tables:
{notes}

Current company goals (the user confirms any goal change with a button, so suggest freely but never duplicate):
{goals}

Recent conversation:
{history}"""

DATA_AGENT = """You are the data agent of an analyst team. You know the company's tables. For the question and its
sub-questions, say in at most 8 short lines: which files and columns each sub-question should use, how to join them,
which column means revenue, date and so on, and any gap (missing table, period not covered). Do not compute anything.

Data available:
{overview}

Notes about the tables:
{notes}"""

ANALYST_NOTE = """

You are Analyst {n} in a team. Answer only your sub-question, thoroughly but briefly. The data agent's guidance:
{guidance}
End with a short findings list where every number is stated with what it measures and its period."""

VERIFIER_NOTE = """

You are the team's verifier. Analysts reported the findings below. Independently recompute the most important
numbers (at most 6) with your own code. Do not reuse their code or trust their numbers. Then list each claim, the
value you got, and whether it matches within rounding.

Findings to check:
{findings}"""

WRITER = """You are the writer of an analyst team. Write the final answer to the user from the analysts' findings and
the verifier's checks. Use only numbers that appear in them; never add new ones. Where the verifier's value differs,
use the verifier's value. Mark numbers the verifier confirmed with a check mark like this: 3,381 ✓.
Format: a short summary first, then the key numbers, then 1 to 3 recommended actions. Keep it tight.

Relevant memories (corrections and preferences from this company):
{memories}"""


def history_text(messages: list, limit: int = 6) -> str:
    lines = [f"{'User' if isinstance(m, HumanMessage) else 'Analyst'}: {m.text[:600]}"
             for m in messages if isinstance(m, (HumanMessage, AIMessage)) and m.text and not getattr(m, "tool_calls", None)]
    return "\n".join(lines[-limit:]) or "(none)"


def notes_text(tenant) -> str:
    notes = tenant.knowledge().get("data_notes", [])
    return "\n".join(n["note"][:800] for n in notes[-6:]) or "(none)"


def answer(agent, sandbox, memory, messages: list, question: str, on_step=None, should_stop=None, images=None,
           team: TeamContext | None = None) -> tuple[list, str | None, int]:
    if team is None or images or not team.files:
        return ask(agent, sandbox, memory, messages, question, on_step=on_step, should_stop=should_stop, images=images)
    emit = on_step or (lambda e: None)
    stopped = should_stop or (lambda: False)

    def stage(who, text):
        emit({"type": "stage", "id": uuid.uuid4().hex, "agent": who, "text": text})

    def halt():
        if stopped():
            raise Stopped()

    llm = pii.guard(team.llm or make_llm())
    overview = team.data.get("overview") or "(no data files yet)"
    notes = notes_text(team.tenant)
    stage("Supervisor", "Reading the question and planning")
    plan = llm.with_structured_output(Plan, method="function_calling").invoke([
        SystemMessage(SUPERVISOR.format(max=MAX_ANALYSTS, overview=overview, notes=notes, history=history_text(messages),
                                        goals="; ".join(team.tenant.knowledge().get("goals", [])) or "(none yet)")),
        HumanMessage(question)])
    subs = [q.strip() for q in plan.subquestions if q.strip()][:MAX_ANALYSTS]
    goals = team.tenant.knowledge().get("goals", [])
    for change in plan.goal_changes[:3]:
        if goal_change_problem(goals, change.action, change.goal, change.new_goal) is None:
            call_id = uuid.uuid4().hex
            emit({"type": "call", "id": call_id, "agent": "Supervisor", "tool": "suggest_goal", "args": change.model_dump()})
            emit({"type": "output", "id": call_id, "agent": "Supervisor", "output": "suggested; a confirm button appears below your answer, so refer to it as below"})
    if plan.mode != "team" or len(subs) < 2:
        stage("Supervisor", "A quick question: one analyst handles it")
        new, final, calls = ask(agent, sandbox, memory, messages, question, on_step=on_step, should_stop=should_stop)
        return new, final, calls + 1
    stage("Supervisor", f"Splitting the work into {len(subs)} parts: " + " | ".join(subs))
    halt()

    stage("Data Agent", "Choosing the tables and columns for each part")
    guidance = llm.invoke([SystemMessage(DATA_AGENT.format(overview=overview, notes=notes)),
                           HumanMessage(f"Question: {question}\nSub-questions:\n" + "\n".join(f"- {q}" for q in subs))]).text
    stage("Data Agent", guidance.strip().splitlines()[0][:200] if guidance.strip() else "No special guidance")
    halt()

    try:
        memories = memory.recall(question)
    except Exception:
        log.warning("memory recall failed", exc_info=True)
        memories = []
    recall = SimpleNamespace(recall=lambda q: memories)
    contexts = []

    def kernel():
        ctx = sandbox.create_code_context()
        contexts.append(ctx)
        preload(sandbox, team.files, context=ctx)
        return ctx

    def labelled(name):
        return lambda e: emit({**e, "agent": name})

    def analyst(n, sub):
        worker = build_agent(sandbox, team.tenant, recall, team.data, llm, team.chart_dir, context=kernel(),
                             role_note=ANALYST_NOTE.format(n=n, guidance=guidance), max_steps=ANALYST_STEPS,
                             remember_tool=False)
        _, found, calls = ask(worker, sandbox, recall, [], sub, on_step=labelled(f"Analyst {n}"), should_stop=should_stop)
        return found or f"(Analyst {n} ran out of steps before finishing.)", calls

    try:
        for n, sub in enumerate(subs, 1):
            stage(f"Analyst {n}", sub)
        with ThreadPoolExecutor(max_workers=len(subs)) as pool:
            traced = [contextvars.copy_context() for _ in subs]
            results = list(pool.map(lambda c, pair: c.run(analyst, *pair), traced, enumerate(subs, 1)))
        halt()
        findings = "\n\n".join(f"Analyst {n} on '{sub}':\n{text}" for n, (sub, (text, _)) in enumerate(zip(subs, results), 1))

        stage("Verifier", "Recomputing the key numbers with its own code")
        checker = build_agent(sandbox, team.tenant, recall, team.data, llm, team.chart_dir, context=kernel(),
                              role_note=VERIFIER_NOTE.format(findings=findings), max_steps=VERIFIER_STEPS,
                              remember_tool=False)
        _, report, verify_calls = ask(checker, sandbox, recall, [], f"Verify the findings for: {question}",
                                      on_step=labelled("Verifier"), should_stop=should_stop)
        halt()
        verdict = llm.with_structured_output(Verdict, method="function_calling").invoke([
            SystemMessage("Turn the verifier's report into a list of checks."), HumanMessage(report or "(no report)")])
        for c in verdict.checks:
            stage("Verifier", f"{'✓' if c.ok else '✗'} {c.claim} → {c.recomputed}")
        if not verdict.checks:
            stage("Verifier", "Could not confirm the numbers; the answer says so")
    finally:
        for ctx in contexts:
            try:
                sandbox.remove_code_context(ctx)
            except Exception:
                pass

    stage("Writer", "Writing the answer from the checked findings")
    checks = json.dumps([c.model_dump() for c in verdict.checks], ensure_ascii=False) if verdict.checks else "(no checks)"
    final = llm.invoke([SystemMessage(WRITER.format(memories="\n".join(memories) or "(none)")),
                        HumanMessage(f"Question: {question}\n\nFindings:\n{findings}\n\nVerifier checks:\n{checks}")]).text
    calls = 4 + sum(c for _, c in results) + verify_calls
    return messages + [HumanMessage(question), AIMessage(final)], final, calls
