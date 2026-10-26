import hashlib
import logging
import os
import re
import secrets
import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager

import langsmith
from langsmith import Client

from pii import PLACEHOLDER, Redactor

PROJECT = "analyst-buddy"
MAX_TRACKED = 2000
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?![\d.]|\s?%)")
log = logging.getLogger("tracing")
_key = secrets.token_bytes(32)
_issued: OrderedDict[str, str] = OrderedDict()
_lock = threading.Lock()
_client: Client | None = None


def scrub(data: dict) -> dict:
    r = Redactor(_key)
    return r.walk(data, r.mask)


def setup(client: Client | None = None) -> bool:
    global _client, PROJECT
    PROJECT = os.getenv("LANGSMITH_PROJECT") or PROJECT
    if not (client or os.getenv("LANGSMITH_API_KEY")):
        langsmith.configure(enabled=False)
        return False
    _client = client or Client(hide_inputs=scrub, hide_outputs=scrub)
    langsmith.configure(client=_client, enabled=True, project_name=PROJECT)
    log.info("LangSmith tracing on, project=%s", PROJECT)
    return True


def owner(tenant_id: str, user: str) -> str:
    return hashlib.sha256(f"{tenant_id}/{user}".encode()).hexdigest()[:16]


@contextmanager
def question(tenant_id: str, user: str, role: str, mode: str, text: str):
    if _client is None:
        yield None
        return
    run_id = str(uuid.uuid4())
    with _lock:
        _issued[run_id] = owner(tenant_id, user)
        while len(_issued) > MAX_TRACKED:
            _issued.popitem(last=False)
    metadata = {"tenant": tenant_id, "user": owner(tenant_id, user), "role": role, "mode": mode}
    with langsmith.trace("question", inputs={"question": text}, metadata=metadata, tags=[mode, role],
                         run_id=run_id, client=_client, project_name=PROJECT) as run:
        yield run


def numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in NUMBER.findall(text or "")]


def checks(answer: str | None, outputs: list[str], calls: int) -> dict:
    seen = [n for o in outputs for n in numbers(o)]
    claimed = [n for n in numbers(answer) if abs(n) >= 10]
    grounded = [n for n in claimed if any(abs(n - s) <= max(abs(s) * 0.01, 0.01) for s in seen)]
    errors = sum(o.startswith("ERROR") or "Traceback" in o for o in outputs)
    return {"answered": int(bool(answer)), "steps": calls, "tool_errors": errors,
            "recovered": int(bool(answer)) if errors else None,
            "numbers_grounded": round(len(grounded) / len(claimed), 2) if claimed else None,
            "placeholder_leak": int(bool(PLACEHOLDER.search(answer or "")))}


def finish(run, answer: str | None, outputs: list[str], calls: int):
    if run is None:
        return
    try:
        run.end(outputs={"answer": answer or ""})
        for key, score in checks(answer, outputs, calls).items():
            if score is not None:
                _client.create_feedback(run.id, key=key, score=score, feedback_source_type="model", trace_id=run.id)
    except Exception:
        log.warning("could not send automatic checks to LangSmith", exc_info=True)


def user_feedback(run_id: str, tenant_id: str, user: str, rating: str, note: str) -> bool:
    if _client is None or _issued.get(run_id) != owner(tenant_id, user):
        return False
    try:
        r = Redactor(_key)
        _client.create_feedback(run_id, key="user_score", score=int(rating == "up"), comment=r.mask(note) or None,
                                trace_id=run_id)
        return True
    except Exception:
        log.warning("could not send user feedback to LangSmith", exc_info=True)
        return False
