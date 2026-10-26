import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import team
from agent import Stopped
from team import Check, GoalChange, Plan, TeamContext, Verdict


class Structured:
    def __init__(self, outer, schema):
        self.outer, self.schema = outer, schema

    def invoke(self, messages):
        self.outer.seen.append((self.schema.__name__, messages))
        return self.outer.plan if self.schema is Plan else self.outer.verdict


class Worker:
    def __init__(self, outer):
        self.outer = outer

    def invoke(self, messages):
        system = messages[0].content
        if not any(isinstance(m, ToolMessage) for m in messages):
            n = re.search(r"Analyst (\d)", system)
            return AIMessage("", tool_calls=[{"name": "run_python", "id": uuid.uuid4().hex,
                                              "args": {"code": f"print('work {n.group(1) if n else 'verify'}')"}}])
        if "verifier" in system:
            return AIMessage("South fell 31% -> I get 30.8%. North 3,381 -> I get 3,381.")
        n = re.search(r"Analyst (\d)", system).group(1)
        return AIMessage(f"Analyst {n} finding: North revenue 3,381; South down 31%.")


class FakeLLM:
    def __init__(self, plan, verdict=Verdict()):
        self.plan, self.verdict, self.seen = plan, verdict, []

    def with_structured_output(self, schema, **kw):
        return Structured(self, schema)

    def bind_tools(self, tools, tool_choice=None):
        assert [t.name for t in tools] == ["run_python"], "team workers must not write to memory"
        return Worker(self)

    def invoke(self, messages):
        self.seen.append(("invoke", messages))
        system = messages[0].content
        if "data agent" in system:
            return AIMessage("Use orders.csv: region, revenue, order_date. No gaps.")
        assert "writer" in system and "Findings:" in messages[1].content and "Verifier checks" in messages[1].content
        return AIMessage("Revenue fell because South dropped 30.8% ✓.")


class FakeSandbox:
    def __init__(self):
        self.lock, self.contexts, self.removed, self.ran, self.live, self.peak = threading.Lock(), [], [], [], 0, 0

    def set_timeout(self, t):
        pass

    def create_code_context(self):
        with self.lock:
            self.contexts.append(f"ctx{len(self.contexts) + 1}")
            return self.contexts[-1]

    def remove_code_context(self, ctx):
        self.removed.append(ctx)

    def run_code(self, code, context=None, timeout=None):
        with self.lock:
            self.live += 1
            self.peak = max(self.peak, self.live)
            self.ran.append((context, code))
        time.sleep(0.05)
        with self.lock:
            self.live -= 1
        return SimpleNamespace(logs=SimpleNamespace(stdout=["ok\n"], stderr=[]), results=[], error=None)


class DirectGraph:
    def stream(self, state, config, stream_mode):
        yield {"messages": state["messages"] + [AIMessage("direct answer")]}


tenant = SimpleNamespace(id="acme", knowledge=lambda: {"goals": ["Grow"], "data_notes": [{"note": "orders.csv: 1,000 rows"}]},
                         output_dir=Path(tempfile.gettempdir()))
memory = SimpleNamespace(recall=lambda q: ["[correction] revenue excludes refunds"])
events = []
plan = Plan(mode="team", reason="why question", subquestions=["revenue by region", "revenue by product", "revenue by channel", "extra"],
            goal_changes=[GoalChange(action="add", goal="Reach 1,000 orders a month"), GoalChange(action="add", goal="grow")])
verdict = Verdict(checks=[Check(claim="South -31%", recomputed="-30.8%", ok=True), Check(claim="North 3,381", recomputed="3,400", ok=False)])

box = FakeSandbox()
llm = FakeLLM(plan, verdict)
crew = TeamContext(tenant, {"overview": "- orders.csv: 1,000 rows"}, ["orders.csv"], Path(tempfile.gettempdir()), llm)
history = [HumanMessage("hi"), AIMessage("hello")]
new, final, calls = team.answer(DirectGraph(), box, memory, history, "Why did revenue drop?", events.append, lambda: False,
                                team=crew)
assert final == "Revenue fell because South dropped 30.8% ✓." and new == history + [HumanMessage("Why did revenue drop?"), AIMessage(final)]
agents = {e.get("agent") for e in events}
suggested = [e["args"] for e in events if e.get("tool") == "suggest_goal"]
assert suggested == [{"action": "add", "goal": "Reach 1,000 orders a month", "new_goal": ""}], "valid goals pass, duplicates are dropped"
assert "Current company goals" in llm.seen[0][1][0].content and "Grow" in llm.seen[0][1][0].content
assert {"Supervisor", "Data Agent", "Analyst 1", "Analyst 2", "Analyst 3", "Verifier", "Writer"} <= agents, agents
assert "Analyst 4" not in agents, "at most 3 analysts"
assert all(e.get("agent") for e in events if e["type"] in ("call", "output")), "every code step names its agent"
assert box.peak > 1, "analysts must run in parallel"
assert sorted(box.removed) == sorted(box.contexts) and len(box.contexts) == 4, (box.contexts, box.removed)
assert all(ctx for ctx, code in box.ran), "team code never runs in the shared main kernel"
assert sum("dfs" in code for _, code in box.ran) == 4, "every kernel gets the data preloaded"
stages = [e["text"] for e in events if e["type"] == "stage"]
assert any(s.startswith("✓ South -31%") for s in stages) and any(s.startswith("✗ North 3,381 → 3,400") for s in stages), stages
assert calls >= 4 + 3 * 2 + 2
supervisor_prompt = llm.seen[0][1][0].content
assert "orders.csv: 1,000 rows" in supervisor_prompt and "Analyst: hello" in supervisor_prompt

events.clear()
direct = FakeLLM(Plan(mode="direct", reason="one number"))
new, final, calls = team.answer(DirectGraph(), FakeSandbox(), memory, [], "Total revenue?", events.append, lambda: False,
                                team=TeamContext(tenant, {}, ["orders.csv"], Path(tempfile.gettempdir()), direct))
assert final == "direct answer" and any("one analyst" in e["text"] for e in events if e["type"] == "stage")
one_sub = FakeLLM(Plan(mode="team", reason="x", subquestions=["only one"]))
assert team.answer(DirectGraph(), FakeSandbox(), memory, [], "q", None, None,
                   team=TeamContext(tenant, {}, ["orders.csv"], Path(tempfile.gettempdir()), one_sub))[1] == "direct answer"
picky = FakeLLM(plan)
assert team.answer(DirectGraph(), FakeSandbox(), memory, [], "what is circled?", None, None, images=["data:image/png;base64,AA=="],
                   team=TeamContext(tenant, {}, [], Path(tempfile.gettempdir()), picky))[1] == "direct answer"
assert picky.seen == [], "circled pictures go straight to one analyst"
assert team.answer(DirectGraph(), FakeSandbox(), memory, [], "q", None, None, team=None)[1] == "direct answer"
empty = FakeLLM(plan)
assert team.answer(DirectGraph(), FakeSandbox(), memory, [], "why?", None, None,
                   team=TeamContext(tenant, {}, [], Path(tempfile.gettempdir()), empty))[1] == "direct answer"
assert empty.seen == [], "a workspace with no data must not start the team"

box = FakeSandbox()
flag = {"stop": False}


def watch(e):
    if e.get("agent") == "Analyst 2" and e["type"] == "call":
        flag["stop"] = True


try:
    team.answer(DirectGraph(), box, memory, [], "Why?", watch, lambda: flag["stop"],
                team=TeamContext(tenant, {"overview": "x"}, ["orders.csv"], Path(tempfile.gettempdir()), FakeLLM(plan, verdict)))
    raise AssertionError("stop was ignored")
except Stopped:
    assert box.contexts and sorted(box.removed) == sorted(box.contexts), "stopping must still close every kernel"

print("team checks passed")
