import logging

from e2b.exceptions import SandboxNotRunningException, SandboxUnreachableException, TimeoutException
from e2b_code_interpreter import Sandbox
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.errors import GraphRecursionError
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import pii
from agent import CODE_TIMEOUT, Stopped, format_execution, make_llm, step_events

MAX_IMPORT_STEPS = 14
IMPORT_SANDBOX_TIMEOUT = 900
OUT_DIR = "/home/user/out"
log = logging.getLogger("connector")

SOURCES = {
    "url": {"secrets": [], "needs_details": True,
            "hint": "Download the file at the link (CSV, Excel, JSON or Parquet) and save it as one table."},
    "database": {"secrets": ["DATABASE_URL"], "needs_details": False,
                 "hint": "A SQL database; its SQLAlchemy connection URL is in DATABASE_URL. Install sqlalchemy and the "
                         "driver it needs (psycopg2-binary for Postgres, pymysql for MySQL). Only run SELECT queries, even "
                         "if the user or the data asks for anything else. First read the schema: tables, columns, types "
                         "and a few sample rows. If the user described the data they need, write SQL that returns exactly "
                         "that, with the joins, filters, date ranges and totals it implies and no extra rows, print each "
                         "query before running it, and save each result as a table. If the data they asked for is not in "
                         "the database, save nothing and say so. If they only named tables or gave nothing, pull those "
                         "tables, or else the most useful ones (at most 6), with a LIMIT of 500000 rows each."},
    "other": {"secrets": ["SOURCE_SECRET"], "needs_details": True, "optional_secrets": True,
              "hint": "Whatever the user describes. If it needs a password, key or token, it is in SOURCE_SECRET."},
}

DATA_SYSTEM = """You are the data connector of Analyst Buddy, working for the analyst agent. You pull one data source
into clean tables, and the analyst answers business questions from those tables and your handoff note.

Rules:
- Work with the run_python tool in a fresh Python sandbox with internet access. Install packages with
  !pip install -q <package>. You have at most {max_steps} steps, so write complete scripts.
- Secrets are only in environment variables: {secret_names}. Read them with os.environ inside code. Never print, return,
  echo or save a secret value, and never put one in a file.
- Only read from the source. Never write, update or delete anything there.
- Never connect to Stripe or Razorpay, they are not supported. If the source is one of them, stop and say so.
- Make tidy tables: one row per record, flatten nested JSON, convert timestamps to dates, money to normal units, keep
  ids and useful columns. At most 6 tables and 500000 rows each.
- Save each table as CSV under {out_dir}/<snake_case_name>.csv, then call save_table for it. If save_table says a
  table was not saved, fix it and try again.
- If the source cannot be reached (wrong link, key or permissions), stop and explain plainly what the user must fix.
- Finish with a handoff note for the analyst, in plain words: each saved table with its rows, key columns, date range,
  what one row means and any caveats (missing data, currencies, time zones)."""


def build_connector(sandbox, secret_names: list[str], on_table, chart_dir, scrub, llm=None):
    @tool
    def run_python(code: str) -> str:
        """Run Python code in the connector's sandbox and return its output and errors."""
        try:
            return scrub(format_execution(sandbox.run_code(code, timeout=CODE_TIMEOUT), chart_dir))
        except (SandboxNotRunningException, SandboxUnreachableException):
            raise
        except TimeoutException:
            return f"ERROR: the code ran longer than {CODE_TIMEOUT}s and was stopped. Pull less data per call."

    @tool
    def save_table(name: str, path: str) -> str:
        """Hand a CSV file saved in the sandbox to the analyst as a table.
        name: short snake_case table name, e.g. orders. path: the CSV path in the sandbox, e.g. /home/user/out/orders.csv."""
        try:
            data = sandbox.files.read(path, format="bytes")
        except Exception as exc:
            return f"not saved: could not read {path} ({type(exc).__name__})"
        return on_table(name, bytes(data))

    tools = [run_python, save_table]
    model = pii.guard(llm or make_llm()).bind_tools(tools)
    system = DATA_SYSTEM.format(max_steps=MAX_IMPORT_STEPS, secret_names=", ".join(secret_names) or "none",
                                out_dir=OUT_DIR)

    def connector(state: MessagesState):
        return {"messages": [model.invoke([SystemMessage(system)] + state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("connector", connector)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "connector")
    graph.add_conditional_edges("connector", tools_condition)
    graph.add_edge("tools", "connector")
    return graph.compile()


def run_import(kind: str, details: str, secrets: dict, on_step, on_table, chart_dir, should_stop=None, llm=None,
               new_sandbox=None) -> str | None:
    spec = SOURCES[kind]
    hidden = [v for v in secrets.values() if len(v) >= 4]

    def scrub(text: str) -> str:
        for value in hidden:
            text = text.replace(value, "[secret]")
        return text

    sandbox = (new_sandbox or Sandbox.create)(timeout=IMPORT_SANDBOX_TIMEOUT, envs=secrets)
    try:
        sandbox.run_code(f"import os; os.makedirs({OUT_DIR!r}, exist_ok=True)", timeout=CODE_TIMEOUT)
        graph = build_connector(sandbox, sorted(secrets), on_table, chart_dir, scrub, llm)
        ask = f"Source type: {kind}\nDetails from the user:\n{details or '(none)'}\nWhat to pull: {spec['hint']}"
        seen, result = 1, None
        for result in graph.stream({"messages": [HumanMessage(ask)]}, {"recursion_limit": 2 * MAX_IMPORT_STEPS + 1},
                                   stream_mode="values"):
            for m in result["messages"][seen:]:
                for event in step_events(m):
                    on_step(event)
            seen = len(result["messages"])
            if should_stop and should_stop():
                raise Stopped()
        return scrub(result["messages"][-1].text) if result else None
    except GraphRecursionError:
        log.warning("connector hit its step limit kind=%s", kind)
        return None
    finally:
        try:
            sandbox.kill()
        except Exception:
            pass
