import json
import os

import langsmith
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langsmith import Client

import pii
import tracing

c = tracing.checks("Revenue was 1,23,456 from 44 orders, up 12%.", ["total 123456.0\norders 44", "ERROR KeyError"], 3)
assert c == {"answered": 1, "steps": 3, "tool_errors": 1, "recovered": 1, "numbers_grounded": 1.0, "placeholder_leak": 0}, c
c = tracing.checks("Revenue was 99,999 for EMAIL_1a2b3c4d.", ["total 123456.0"], 2)
assert c["numbers_grounded"] == 0.0 and c["placeholder_leak"] == 1 and c["recovered"] is None, c
assert tracing.checks(None, [], 8)["answered"] == 0

os.environ.pop("LANGSMITH_API_KEY", None)
assert not tracing.setup()
with tracing.question("t1", "a@x.in", "owner", "auto", "hi") as run:
    assert run is None

sent, feedback = [], []


class Recorder(Client):
    def _create_run(self, run, *a, **k):
        sent.append(run)

    def _update_run(self, run, *a, **k):
        sent.append(run)

    def create_feedback(self, run_id=None, key="unnamed", **k):
        feedback.append((str(run_id), key, k.get("score"), k.get("comment")))


client = Recorder(api_url="http://127.0.0.1:9", api_key="test", auto_batch_tracing=False,
                  hide_inputs=tracing.scrub, hide_outputs=tracing.scrub)
try:
    assert tracing.setup(client)
    llm = pii.guard(FakeMessagesListChatModel(responses=[AIMessage("The top buyer is asha@shop.in")]))
    with tracing.question("t1", "boss@x.in", "owner", "single", "Who is asha@shop.in? Call +91 98765 43210") as run:
        reply = llm.invoke([HumanMessage("data: asha@shop.in bought 4 items")])
        tracing.finish(run, reply.text, ["asha@shop.in 4"], 2)
    assert reply.text == "The top buyer is asha@shop.in", "the user still gets the real value"
    dump = json.dumps([{k: v for k, v in r.items() if k != "serialized"} for r in sent], default=str)
    assert "asha@shop.in" not in dump and "98765" not in dump, "traces never carry personal data"
    assert "EMAIL_" in dump
    root = str(run.id)
    assert any(str(r.get("parent_run_id")) == root for r in sent), "LLM calls nest under the question trace"
    keys = {k for rid, k, *_ in feedback if rid == root}
    assert {"answered", "steps", "placeholder_leak"} <= keys and "numbers_grounded" not in keys, keys
    assert tracing.user_feedback(root, "t1", "boss@x.in", "down", "wrong, ask asha@shop.in")
    assert feedback[-1][1:3] == ("user_score", 0) and "asha@shop.in" not in feedback[-1][3]
    assert not tracing.user_feedback(root, "t1", "intruder@x.in", "up", ""), "only the asker can rate their trace"
    assert not tracing.user_feedback("not-a-run", "t1", "boss@x.in", "up", "")
finally:
    langsmith.configure(enabled=False)
    tracing._client = None
print("tracing checks passed")
