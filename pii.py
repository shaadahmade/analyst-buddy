import hashlib
import hmac
import re
import secrets

from langchain_core.messages import BaseMessage, SystemMessage
from pydantic import BaseModel

PATTERNS = [
    ("CARD", re.compile(r"(?<![\d.])\d(?:[ -]?\d){12,18}(?!\d|\.\d)")),
    ("AADHAAR", re.compile(r"(?<![\d.])[2-9]\d{3}[ -]\d{4}[ -]\d{4}(?!\d|\.\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"\+\d{1,3}[ -]?\(?\d{2,5}\)?(?:[ -]?\d){5,10}(?!\d|\.\d)"
                         r"|(?<![\d.,])[6-9]\d{9}(?!\d|[.,]\d)"
                         r"|(?<![\d.])\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d|\.\d)")),
]
PLACEHOLDER = re.compile(r"\b(?:CARD|AADHAAR|PAN|EMAIL|PHONE)_[0-9a-f]{8}\b")
NOTE = ("\n\nPrivacy: personal details (emails, phone, card, Aadhaar and PAN numbers) are shown to you as placeholders "
        "like EMAIL_xxxxxxxx (eight hex characters). Use them exactly as written, also inside code; they are swapped back to the real values "
        "automatically. Never guess the real value behind one.")
SKIP_KEYS = {"image_url"}


def luhn(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


class Redactor:
    def __init__(self, key: bytes | None = None):
        self.key = key or secrets.token_bytes(32)
        self.values: dict[str, str] = {}

    def _token(self, kind: str, value: str) -> str:
        token = f"{kind}_{hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()[:8]}"
        self.values[token] = value
        return token

    def mask(self, text: str) -> str:
        for kind, pattern in PATTERNS:
            def swap(m, kind=kind):
                if kind == "CARD" and not luhn(re.sub(r"\D", "", m.group())):
                    return m.group()
                return self._token(kind, m.group())
            text = pattern.sub(swap, text)
        return text

    def restore(self, text: str) -> str:
        return PLACEHOLDER.sub(lambda m: self.values.get(m.group(), m.group()), text)

    def walk(self, value, fn):
        if isinstance(value, str):
            return fn(value)
        if isinstance(value, list):
            return [self.walk(v, fn) for v in value]
        if isinstance(value, dict):
            return {k: v if k in SKIP_KEYS else self.walk(v, fn) for k, v in value.items()}
        return value

    def message(self, m, fn):
        update = {"content": self.walk(m.content, fn)}
        if getattr(m, "tool_calls", None):
            update["tool_calls"] = [{**c, "args": self.walk(c["args"], fn)} for c in m.tool_calls]
        return m.model_copy(update=update)


class Guarded:
    def __init__(self, inner, redactor: Redactor | None = None):
        self.inner, self.redactor = inner, redactor or Redactor()

    def _outgoing(self, messages):
        r = self.redactor
        out = [r.message(m, r.mask) if isinstance(m, BaseMessage) else r.walk(m, r.mask) for m in messages]
        if out and isinstance(out[0], SystemMessage) and isinstance(out[0].content, str):
            out[0] = out[0].model_copy(update={"content": out[0].content + NOTE})
        return out

    def _incoming(self, result):
        r = self.redactor
        if isinstance(result, BaseMessage):
            return r.message(result, r.restore)
        if isinstance(result, BaseModel):
            return type(result).model_validate_json(r.restore(result.model_dump_json()))
        return r.walk(result, r.restore)

    def invoke(self, messages, *args, **kwargs):
        return self._incoming(self.inner.invoke(self._outgoing(messages), *args, **kwargs))

    def bind_tools(self, *args, **kwargs):
        return Guarded(self.inner.bind_tools(*args, **kwargs), self.redactor)

    def with_structured_output(self, *args, **kwargs):
        return Guarded(self.inner.with_structured_output(*args, **kwargs), self.redactor)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def guard(llm) -> Guarded:
    return llm if isinstance(llm, Guarded) else Guarded(llm)
