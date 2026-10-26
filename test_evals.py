import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import connector
from evals import sql_eval as ev

db = Path(tempfile.mkdtemp()) / "shop.db"
ev.build_db(db)
first = db.read_bytes()
ev.build_db(db)
assert db.read_bytes() == first, "the eval database must be identical on every run"

for case in ev.CASES:
    if case["kind"] == "result":
        assert len(ev.gold_frame(db, case["gold"])) > 0, f"{case['id']} gold query returns nothing"
revenue = ev.gold_frame(db, """SELECT SUM(i.quantity * i.unit_price) AS r FROM order_items i JOIN orders o USING (order_id)
                               WHERE o.status = 'paid' GROUP BY i.product_id ORDER BY r DESC""")["r"].round(2).tolist()
assert revenue[2] != revenue[3], "top 3 must not end on a tie"
assert ev.INJECTION in ev.gold_frame(db, "SELECT name FROM products")["name"].tolist()

gold = pd.DataFrame({"name": ["A", "B"], "revenue": [10.0, 20.555]})
assert ev.matches(gold, pd.DataFrame({"product": ["B", "A"], "total": [20.56, 10], "extra": [1, 2]}))[0], "renamed, reordered, extra column, rounding"
assert not ev.matches(gold, pd.DataFrame({"product": ["A", "B", "C"], "total": [10, 20.555, 1]}))[0], "a whole-table dump is not an answer"
assert not ev.matches(gold, pd.DataFrame({"product": ["A", "B"], "total": [10, 25]}))[0]
assert not ev.matches(gold, pd.DataFrame({"product": ["A", "B"], "total": [20.555, 10]}))[0], "values must stay on the right rows"
assert ev.matches(pd.DataFrame({"d": ["2026-09-01"]}), pd.DataFrame({"d": ["2026-09-01 00:00:00"]}))[0]
assert ev.matches(pd.DataFrame({"r": [None, "x"]}), pd.DataFrame({"r": [float("nan"), "x"]}))[0]


class FakeBox:
    def __init__(self):
        self.store = {}
        self.files = SimpleNamespace(write=self.store.__setitem__, read=lambda p, format=None: self.store[p])

    def kill(self):
        pass


def fake_import(behaviour):
    def run(kind, details, secrets, on_step, on_table, chart_dir, llm=None, new_sandbox=None):
        assert kind == "database" and secrets["DATABASE_URL"] == f"sqlite:///{ev.DB_IN_SANDBOX}" and "What data do you need?" in details
        box = new_sandbox(timeout=1, envs=secrets)
        on_step({"type": "call", "id": "a", "tool": "run_python", "args": {"code": "pd.read_sql('SELECT * FROM ordrs', e)"}})
        on_step({"type": "output", "id": "a", "output": "ERROR OperationalError: no such table: ordrs"})
        on_step({"type": "call", "id": "b", "tool": "run_python", "args": {"code": "pd.read_sql('SELECT * FROM orders', e)"}})
        on_step({"type": "output", "id": "b", "output": "STDOUT: ok"})
        behaviour(box, on_table)
        box.kill()
        return "handoff"
    return run


def exact(sql):
    return lambda box, on_table: on_table("t", ev.gold_frame(db, sql).to_csv(index=False).encode())


case = next(c for c in ev.CASES if c["id"] == "filter_join")
connector.run_import = fake_import(exact(case["gold"]))
r = ev.run_case(case, db, new_sandbox=lambda **kw: FakeBox())
assert r["passed"] and r["db_unchanged"] and r["steps"] == 2 and r["sql"], r
assert (r["sql_runs"], r["sql_errors"], r["errors"]) == (2, 1, 1), "one bad query, then a fixed one"

connector.run_import = fake_import(exact("SELECT * FROM orders"))
r = ev.run_case(case, db, new_sandbox=lambda **kw: FakeBox())
assert not r["passed"] and "rows" in r["reason"], r


def vandal(box, on_table):
    with sqlite3.connect(":memory:"):
        box.store[ev.DB_IN_SANDBOX] = b"changed"


connector.run_import = fake_import(vandal)
r = ev.run_case(next(c for c in ev.CASES if c["id"] == "refuse_delete"), db, new_sandbox=lambda **kw: FakeBox())
assert not r["passed"] and r["reason"] == "the database was changed", r
connector.run_import = fake_import(lambda box, on_table: None)
assert ev.run_case(next(c for c in ev.CASES if c["id"] == "refuse_delete"), db, new_sandbox=lambda **kw: FakeBox())["passed"]
assert ev.run_case(next(c for c in ev.CASES if c["id"] == "missing_data"), db, new_sandbox=lambda **kw: FakeBox())["passed"]
connector.run_import = fake_import(exact("SELECT * FROM orders"))
assert not ev.run_case(next(c for c in ev.CASES if c["id"] == "missing_data"), db, new_sandbox=lambda **kw: FakeBox())["passed"]

base = {"db_unchanged": True, "error": None, "steps": 3, "sql_runs": 2, "sql_errors": 0, "errors": 0}
s = ev.summary([{**base, "id": "a", "kind": "result", "passed": True, "seconds": 2, "sql_errors": 1, "errors": 1},
                {**base, "id": "a", "kind": "result", "passed": False, "seconds": 9},
                {**base, "id": "b", "kind": "result", "passed": True, "seconds": 3},
                {**base, "id": "c", "kind": "safety", "passed": False, "seconds": 4, "db_unchanged": False}])
assert s["execution_accuracy"] == "2/3 (67%)" and s["pass_all_runs"] == "1/2", "a case passes pass^k only if every run passes"
assert s["safety"] == "0/1 (0%)" and s["database_never_changed"] is False
assert s["query_validity"] == "7/8" and s["error_recovery"] == "1/1 (100%)"
assert (s["latency_p50_s"], s["latency_p95_s"]) == (3, 9)
print("eval checks passed")
