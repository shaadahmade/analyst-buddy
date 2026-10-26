import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

import connector

SECRET = "postgresql://u:very_secret_123@db/x"


class FakeSandbox:
    def __init__(self, envs):
        self.envs, self.killed, self.ran = envs, False, []
        self.files = SimpleNamespace(read=self.read)

    def run_code(self, code, timeout=None):
        self.ran.append(code)
        out = [f"key is {self.envs.get('DATABASE_URL')}\n"] if "leak" in code else ["ok\n"]
        return SimpleNamespace(logs=SimpleNamespace(stdout=out, stderr=[]), results=[], error=None)

    def read(self, path, format):
        assert format == "bytes"
        if path.endswith("missing.csv"):
            raise FileNotFoundError(path)
        return b"date,amount\n2026-10-01,12.5\n"

    def kill(self):
        self.killed = True


class ScriptedModel:
    def __init__(self, script, seen):
        self.script, self.seen = script, seen

    def bind_tools(self, tools):
        assert [t.name for t in tools] == ["run_python", "save_table"]
        return self

    def invoke(self, messages):
        self.seen.append(messages)
        step = self.script.pop(0)
        if isinstance(step, str):
            return AIMessage(step)
        name, args = step
        return AIMessage("", tool_calls=[{"name": name, "args": args, "id": uuid.uuid4().hex}])


boxes, steps, tables, seen = [], [], [], []


def new_sandbox(timeout, envs):
    boxes.append(FakeSandbox(envs))
    return boxes[-1]


def on_table(name, data):
    tables.append((name, data))
    return f"saved as {name}.csv"


script = [
    ("run_python", {"code": "leak()"}),
    ("save_table", {"name": "charges", "path": "/home/user/out/missing.csv"}),
    ("save_table", {"name": "charges", "path": "/home/user/out/charges.csv"}),
    f"Saved charges: 1 row. (key was {SECRET})",
]
with tempfile.TemporaryDirectory() as tmp:
    note = connector.run_import("database", "", {"DATABASE_URL": SECRET}, steps.append, on_table, Path(tmp),
                                llm=ScriptedModel(script, seen), new_sandbox=new_sandbox)

box = boxes[0]
assert box.envs == {"DATABASE_URL": SECRET} and box.killed, "secrets go in as env vars and the sandbox is closed"
assert "os.makedirs" in box.ran[0]
outputs = [m.content for m in seen[-1] if isinstance(m, ToolMessage)]
assert SECRET not in str(seen) and "[secret]" in outputs[0], "a secret printed by code must never reach the model"
assert "not saved" in outputs[1] and outputs[2] == "saved as charges.csv", outputs
assert tables == [("charges", b"date,amount\n2026-10-01,12.5\n")]
assert SECRET not in note and "[secret]" in note
assert [e["type"] for e in steps].count("call") == 3 and SECRET not in str(steps)
assert "DATABASE_URL" in seen[0][0].content and SECRET not in seen[0][0].content

boxes.clear()
endless = [("run_python", {"code": "print(1)"})] * (connector.MAX_IMPORT_STEPS + 5)
with tempfile.TemporaryDirectory() as tmp:
    assert connector.run_import("url", "https://x.example/a.csv", {}, lambda e: None, on_table, Path(tmp),
                                llm=ScriptedModel(endless, []), new_sandbox=new_sandbox) is None
assert boxes[0].killed, "the sandbox must close even when the connector runs out of steps"

boxes.clear()
try:
    with tempfile.TemporaryDirectory() as tmp:
        connector.run_import("url", "https://x.example/a.csv", {}, lambda e: None, on_table, Path(tmp),
                             llm=ScriptedModel([("run_python", {"code": "print(1)"})] * 3, []), new_sandbox=new_sandbox,
                             should_stop=lambda: True)
    raise AssertionError("stop was ignored")
except connector.Stopped:
    assert boxes[0].killed

assert set(connector.SOURCES) == {"url", "database", "other"}
print("connector checks passed")
