import json
import base64
import tempfile
from pathlib import Path
from types import SimpleNamespace

from agent import MAX_OUTPUT, format_execution


class FakeResult:
    def __init__(self, png=None, text=""):
        self.png, self.text = png, text

    def _repr_png_(self):
        return self.png

    def __str__(self):
        return self.text


def fake_exec(stdout=(), results=(), error=None):
    return SimpleNamespace(logs=SimpleNamespace(stdout=list(stdout), stderr=[]), results=list(results), error=error)


with tempfile.TemporaryDirectory() as tmp:
    charts = Path(tmp) / "charts"
    png = base64.b64encode(b"\x89PNG fake").decode()
    out = format_execution(fake_exec(["hi\n"], [FakeResult(png=png), FakeResult(text="42")]), charts)
    saved = list(charts.glob("chart_*.png"))
    assert "STDOUT:\nhi" in out and "RESULT:\n42" in out and saved[0].name in out, out
    assert len(saved) == 1 and saved[0].read_bytes() == b"\x89PNG fake"

    err = SimpleNamespace(name="KeyError", value="'revenue'", traceback="tb...")
    assert "ERROR KeyError" in format_execution(fake_exec(error=err), charts)

    assert format_execution(fake_exec(), charts) == "(no output)"
    long = format_execution(fake_exec(["x" * (MAX_OUTPUT * 2)]), charts)
    assert long.endswith("[output truncated]") and len(long) < MAX_OUTPUT + 50

from tenants import Memory, Tenant

for bad in ["../acme", "acme/../globex", "ACME", "a", "", "acme;drop"]:
    try:
        Tenant(bad)
        raise AssertionError(f"accepted bad tenant id {bad!r}")
    except ValueError:
        pass
try:
    Tenant("no-such-company")
    raise AssertionError("accepted unknown tenant")
except ValueError:
    pass


class FakeIndex:
    def __init__(self):
        self.store = {}

    def upsert_records(self, *, records, namespace):
        self.store.setdefault(namespace, []).extend(records)

    def search(self, *, namespace, top_k, inputs, fields, filter):
        hits = [SimpleNamespace(fields=r) for r in self.store.get(namespace, []) if matches(r, filter)][:top_k]
        return SimpleNamespace(result=SimpleNamespace(hits=hits))


def matches(record, flt):
    if "$or" in flt:
        return any(matches(record, f) for f in flt["$or"])
    (key, cond), = flt.items()
    if "$exists" in cond:
        return (key in record) == cond["$exists"]
    if key not in record:
        return False
    return record[key] == cond["$eq"] if "$eq" in cond else record[key] in cond["$in"]


index = FakeIndex()
acme, globex = Memory(Tenant("acme"), index), Memory(Tenant("globex"), index)
acme.remember("Acme secret: South region is churning", "insight")
assert set(index.store) == {"acme"}
assert globex.recall("South region") == [], "globex saw acme's memory"
assert "Acme secret" in acme.recall("South region")[0]

index.store["acme"].append({"_id": "old", "text": "legacy company memory", "kind": "fact", "created": "2026-01-01"})
viewer = Memory(Tenant("acme"), index, "vic@acme.in", "viewer")
viewer.remember("vic prefers weekly numbers", "liked")
assert index.store["acme"][-1]["owner"] == "vic@acme.in", "a viewer's memory must stay personal"
assert len(viewer.recall("x")) == 3, "a viewer reads company memories and their own"
analyst = Memory(Tenant("acme"), index, "ana@acme.in", "analyst")
assert not any("vic prefers" in m for m in analyst.recall("x")), "saw another user's personal memory"
north = Memory(Tenant("acme"), index, "rep@acme.in", "analyst", {"orders.csv": {"rows": {"region": ["North"]}, "hide": []}})
north.remember("rep note", "fact")
assert [m.split("] ")[1] for m in north.recall("South region")] == ["rep note"], "a scoped user read company-wide memories"
assert index.store["acme"][-1]["owner"] == "rep@acme.in"

import pandas as pd

from agent import apply_scope, upload_data

df = pd.DataFrame({"region": ["North", "South", "North"], "revenue": [1, 2, 3], "customer_id": [7, 8, 9]})
only_north = apply_scope(df, {"rows": {"region": ["North"]}, "hide": ["customer_id"]})
assert list(only_north.columns) == ["region", "revenue"] and only_north["revenue"].tolist() == [1, 3]
assert apply_scope(df, {"rows": {"no_such_column": ["x"]}, "hide": []}).empty, "an unknown filter column must hide all rows"

with tempfile.TemporaryDirectory() as tmp:
    data_dir = Path(tmp)
    df.to_csv(data_dir / "orders.csv", index=False)
    (data_dir / "salaries.csv").write_text("name,salary\nA,100\n")
    (data_dir / "broken.xlsx").write_bytes(b"not excel")
    written = {}
    box = SimpleNamespace(files=SimpleNamespace(write=lambda p, d: written.__setitem__(p.rsplit("/", 1)[1], d)))
    fake_tenant = SimpleNamespace(data_dir=data_dir)
    names = upload_data(box, fake_tenant, {"orders.csv": {"rows": {"region": ["North"]}, "hide": ["customer_id"]},
                                           "broken.xlsx": {"rows": {"region": ["North"]}, "hide": []}})
    assert names == ["orders.csv"], names
    assert b"South" not in written["orders.csv"] and b"customer_id" not in written["orders.csv"], written
    assert "salaries.csv" not in written, "a file outside the scope reached the sandbox"
    written.clear()
    assert sorted(upload_data(box, fake_tenant)) == ["broken.xlsx", "orders.csv", "salaries.csv"]

from langchain_core.messages import AIMessage

import agent as agent_mod

seen = {}


class FakeGraph:
    def stream(self, state, config, stream_mode):
        seen["memories"] = state["memories"]
        seen["sent"] = state["messages"][-1]
        yield {"messages": state["messages"] + [AIMessage("ok")]}


class DownMemory:
    def recall(self, q):
        raise ConnectionError("pinecone down")


_, answer, calls = agent_mod.ask(FakeGraph(), SimpleNamespace(set_timeout=lambda t: None), DownMemory(), [], "hi")
assert answer == "ok" and calls == 1 and "unavailable" in seen["memories"], (answer, seen)

from agent import goal_change_problem

goals = ["Grow repeat orders 10%"]
assert goal_change_problem(goals, "add", "Cut refunds below 2%") is None
assert "already exists" in goal_change_problem(goals, "add", "grow repeat orders 10%")
assert "no goal has that exact text" in goal_change_problem(goals, "remove", "Something else")
assert goal_change_problem(goals, "update", "Grow repeat orders 10%", "Grow repeat orders 15%") is None
assert goal_change_problem(goals, "update", "Grow repeat orders 10%", "") is not None
assert goal_change_problem(goals, "delete", "x") is not None

shot = "data:image/png;base64,iVBORw0KGgo="
shot2 = "data:image/jpeg;base64,/9j/4AAQ"
kept, answer, _ = agent_mod.ask(FakeGraph(), SimpleNamespace(set_timeout=lambda t: None), DownMemory(), [], "what is this?",
                                images=[shot, shot2])
parts = seen["sent"].content
assert parts[0] == {"type": "text", "text": "what is this?"} and [p["image_url"]["url"] for p in parts[1:]] == [shot, shot2], parts
assert answer == "ok" and isinstance(kept[0].content, str) and shot not in str(kept), "images must not stay in the history"
assert "2 image(s) of circled areas" in kept[0].content

class EndlessModel:

    def __init__(self, tool_choice=None):
        self.tool_choice = tool_choice

    def bind_tools(self, tools, tool_choice=None):
        return EndlessModel(tool_choice)

    def invoke(self, messages):
        if self.tool_choice == "none":
            assert "last step" in messages[0].content, "final step must tell the model to answer now"
            return AIMessage("best answer from what I found")
        return AIMessage("", tool_calls=[{"name": "run_python", "args": {"code": "print(1)"}, "id": uuid.uuid4().hex}])


import uuid

ran = []
fake_sandbox = SimpleNamespace(
    set_timeout=lambda t: None,
    run_code=lambda code, timeout, context=None: ran.append(code) or fake_exec(["1\n"]),
)
graph = agent_mod.build_agent(fake_sandbox, Tenant("acme"), SimpleNamespace(recall=lambda q: []), {"overview": "x"}, llm=EndlessModel())
_, answer, calls = agent_mod.ask(graph, fake_sandbox, SimpleNamespace(recall=lambda q: []), [], "profile my data")
assert answer == "best answer from what I found", answer
assert calls == agent_mod.MAX_LLM_CALLS and len(ran) == agent_mod.MAX_LLM_CALLS - 1, (calls, len(ran))


class StubbornModel(EndlessModel):

    def bind_tools(self, tools, tool_choice=None):
        return EndlessModel()

    def invoke(self, messages):
        assert "RESULT:" in messages[-1].content, "the tool-less retry must see the work done so far"
        return AIMessage("answer written from the results")


ran.clear()
graph = agent_mod.build_agent(fake_sandbox, Tenant("acme"), SimpleNamespace(recall=lambda q: []), {"overview": "x"}, llm=StubbornModel())
_, answer, calls = agent_mod.ask(graph, fake_sandbox, SimpleNamespace(recall=lambda q: []), [], "profile my data")
assert answer == "answer written from the results", answer
assert len(ran) == agent_mod.MAX_LLM_CALLS - 1, len(ran)

events = []
agent_mod.ask(graph, fake_sandbox, SimpleNamespace(recall=lambda q: []), [], "again", on_step=events.append)
assert [e["type"] for e in events[:2]] == ["call", "output"] and events[0]["id"] == events[1]["id"], events[:2]
assert events[0]["args"] == {"code": "print(1)"} and "1" in events[1]["output"], events[:2]

print("all checks passed")

ran.clear()
graph = agent_mod.build_agent(fake_sandbox, Tenant("acme"), SimpleNamespace(recall=lambda q: []), {"overview": "x"}, llm=EndlessModel())
history = ["earlier"]
try:
    agent_mod.ask(graph, fake_sandbox, SimpleNamespace(recall=lambda q: []), history, "profile my data",
                  should_stop=lambda: len(ran) >= 2)
    raise AssertionError("should have stopped")
except agent_mod.Stopped:
    pass
assert len(ran) == 2, f"stopped after its current step, ran {len(ran)} cells"
assert history == ["earlier"], "a stopped question must not touch the history"
print("stop checks passed")

class CaptureLLM:
    def bind_tools(self, tools, **kw):
        self.tools = {getattr(x, "name", "") : x for x in tools}
        return self


saved = {}
live_box = SimpleNamespace(files=SimpleNamespace(write=lambda p, d: saved.__setitem__(p, d)))
real_has, real_live = agent_mod.connections.has_shopify, agent_mod.connections.live_shopify
agent_mod.connections.has_shopify = lambda tenant: True
queries = []
agent_mod.connections.live_shopify = lambda tenant, q, v=None: (queries.append((q, v)) or ("musclerag.myshopify.com", {"orders": {"nodes": [{"name": "#1"}]}}))
try:
    def tools_for(data, remember_tool=True):
        llm = CaptureLLM()
        agent_mod.build_agent(live_box, Tenant("acme"), SimpleNamespace(recall=lambda q: []), data, llm=llm, remember_tool=remember_tool)
        return llm.tools

    assert "shopify_live" in tools_for({"overview": "x", "live": True})
    assert "shopify_live" in tools_for({"overview": "x", "live": True}, remember_tool=False), "team analysts get it too"
    assert "shopify_live" not in tools_for({"overview": "x", "live": False}), "members with a data scope never query live"
    assert "shopify_live" not in tools_for({"overview": "x"}), "live is off unless the session turns it on"
    live_tool = tools_for({"overview": "x", "live": True})["shopify_live"]
    out = live_tool.invoke({"query": "{ orders(first: 5) { nodes { name } } }", "variables": '{"q": "created_at:>=2026-10-25"}'})
    assert "Live from musclerag" in out and "/live/shopify_1.json" in out and queries[-1][1] == {"q": "created_at:>=2026-10-25"}, out
    assert json.loads(next(iter(saved.values()))) == {"orders": {"nodes": [{"name": "#1"}]}}
    assert live_tool.invoke({"query": "{ a }", "variables": "[1]"}).startswith("ERROR"), "variables must be an object"
    assert live_tool.invoke({"query": "{ a }", "variables": "{bad"}).startswith("ERROR")
    agent_mod.connections.has_shopify = lambda tenant: False
    assert "shopify_live" not in tools_for({"overview": "x", "live": True}), "no store connected, no tool"
finally:
    agent_mod.connections.has_shopify, agent_mod.connections.live_shopify = real_has, real_live
print("live shopify checks passed")
