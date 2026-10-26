from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

import pii

r = pii.Redactor()
text = ("Top: asha@shop.in (+91 98765 43210), card 4111 1111 1111 1111, Aadhaar 2345 6789 0123, PAN ABCDE1234F, "
        "call 9876543210. Revenue 9876543210.50, 1,23,456 orders, order 4111111111111112, date 2026-10-26, id 12345678")
masked = r.mask(text)
for raw in ("asha@shop.in", "98765 43210", "4111 1111 1111 1111", "2345 6789 0123", "ABCDE1234F", "call 9876543210"):
    assert raw not in masked, (raw, masked)
for kept in ("9876543210.50", "1,23,456", "4111111111111112", "2026-10-26", "12345678"):
    assert kept in masked, (kept, masked)
assert r.mask("asha@shop.in") == r.mask("asha@shop.in"), "the same value gets the same placeholder"
assert r.restore(masked) == text
assert r.restore("EMAIL_00000000 stays") == "EMAIL_00000000 stays", "unknown placeholders are left alone"
assert pii.Redactor().mask("asha@shop.in") != r.mask("asha@shop.in"), "placeholders are keyed per session"


class Plan(BaseModel):
    task: str


class FakeLLM:
    def __init__(self):
        self.seen = []

    def bind_tools(self, tools, **kw):
        return self

    def with_structured_output(self, schema, **kw):
        llm = FakeLLM()
        llm.seen, llm.schema = self.seen, schema
        return llm

    def invoke(self, messages, **kw):
        self.seen.append(messages)
        sent = " ".join(str(m.content) for m in messages)
        token = next(t for t in pii.PLACEHOLDER.findall(sent) if t.startswith("EMAIL_"))
        if getattr(self, "schema", None):
            return self.schema(task=f"look up {token}")
        return AIMessage(f"Best customer is {token}.", tool_calls=[{"id": "c1", "name": "run_python",
                                                                   "args": {"code": f"df[df.email == '{token}']"}}])


fake = FakeLLM()
llm = pii.guard(fake).bind_tools([])
assert pii.guard(llm) is llm
image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,9876543210"}}
reply = llm.invoke([SystemMessage("You are an analyst."), HumanMessage([{"type": "text", "text": "who?"}, image]),
                    AIMessage("", tool_calls=[{"id": "c0", "name": "run_python", "args": {"code": "print(df.head())"}}]),
                    ToolMessage("email\nasha@shop.in  9876543210", tool_call_id="c0")])
sent = fake.seen[-1]
assert "asha@shop.in" not in str([m.content for m in sent]) and "9876543210" not in sent[3].content
assert sent[1].content[1] == image, "images are sent untouched"
assert sent[0].content.endswith(pii.NOTE.strip()[-40:]) and isinstance(sent[0], SystemMessage)
assert reply.content == "Best customer is asha@shop.in." and reply.tool_calls[0]["args"]["code"] == "df[df.email == 'asha@shop.in']"
assert pii.guard(fake).with_structured_output(Plan).invoke([HumanMessage("asha@shop.in")]).task == "look up asha@shop.in"
print("pii checks passed")
