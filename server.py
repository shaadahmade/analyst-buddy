import base64
import hashlib
import html
import json
import logging
import os
import queue
import re
import secrets
import sys
from urllib.parse import urlparse
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from e2b.exceptions import RateLimitException as SandboxRateLimit
from e2b.exceptions import SandboxException, ServiceBusyException
from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from langchain_google_genai.chat_models import GoogleAPIError, GoogleGenerativeAIError, GoogleRateLimitError
from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import BaseModel

from agent import DATA_SUFFIXES, MAX_LLM_CALLS, SANDBOX_DATA, SANDBOX_IDLE, Stopped, build_agent, preload, start_sandbox
from team import TeamContext
from team import answer as ask
import connections
import tracing
import sources
from connector import SOURCES, run_import
from sources import CONNECTORS, SourceError
import mcp_auth
import mcp_oauth
import mcp_server
import persist
import reports
from tenants import (ROLES, Memory, Tenant, account_exists, check_account, create_account, create_workspace,
                     ensure_google_account,
                     last_workspace, migrate_accounts, normal_email, open_index, permissions, public_user,
                     set_last_workspace, workspaces_of)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("server")

BUSY = "The analyst is busy right now. Try again in a minute."
UNAVAILABLE = "The analyst is unavailable right now. We have been notified."
RESTARTED = "Your workspace restarted. Ask your question again."
NO_RESTART = "Your workspace stopped and could not restart. Please sign in again."
NO_START = "We could not start your workspace. Try again in a minute."
FILE_MAGIC = {".xlsx": b"PK\x03\x04", ".xls": b"\xd0\xcf\x11\xe0", ".parquet": b"PAR1"}
MAX_UPLOAD = 50 * 1024 * 1024
MAX_QUESTION = 4000
MAX_CONTEXT = 8000
LOGIN_DAYS = 7
LOGINS_FILE = Path(__file__).parent / "logins.json"
MAX_IMAGE = 4_000_000
MAX_IMAGES = 5
IMAGE_URL = re.compile(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}")
LOGIN_LIMIT = (20, 600)
SIGNUP_LIMIT = (5, 3600)
WEB_DIST = Path(__file__).parent / "web" / "dist"
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()
_feedback_lock = threading.Lock()


@dataclass
class Session:
    tenant: Tenant
    sandbox: object
    agent: object
    memory: Memory
    files: list[str]
    user: str
    role: str
    scope: dict | None
    charts: Path
    data: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)
    last_used: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)
    stop: threading.Event = field(default_factory=threading.Event)
    importing: bool = False


SESSIONS: dict[str, Session] = {}
_logins_lock = threading.Lock()
_revive_lock = threading.Lock()
_index = None


def memory_index():
    global _index
    if _index is None:
        try:
            _index = open_index()
        except Exception:
            log.warning("memory index unavailable", exc_info=True)
    return _index


def friendly(exc: Exception) -> str | None:
    if isinstance(exc, (GoogleRateLimitError, GoogleAPIError, SandboxRateLimit, ServiceBusyException, RateLimitError,
                        APIConnectionError, APITimeoutError, InternalServerError)):
        return BUSY
    if isinstance(exc, (GoogleGenerativeAIError, APIStatusError)):
        return UNAVAILABLE
    return None


def restart_sandbox(s: "Session"):
    try:
        s.sandbox.kill()
    except Exception:
        pass
    s.sandbox, s.files, s.data["overview"] = start_sandbox(s.tenant, s.scope)
    s.agent = build_agent(s.sandbox, s.tenant, s.memory, s.data, chart_dir=s.charts)


def close_session(token: str):
    s = SESSIONS.pop(token, None)
    if s:
        try:
            s.sandbox.kill()
        except Exception:
            pass


def end_session(token: str):
    close_session(token)
    forget_login(token)


def token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _logins() -> dict:
    return json.loads(LOGINS_FILE.read_text(encoding="utf-8")) if LOGINS_FILE.exists() else {}


def _write_logins(logins: dict):
    now = time.time()
    LOGINS_FILE.write_text(json.dumps({k: v for k, v in logins.items() if v["exp"] > now}), encoding="utf-8")


def remember_login(token: str, tenant: Tenant, email: str):
    with _logins_lock:
        logins = _logins()
        logins[token_key(token)] = {"t": tenant.id, "u": email, "exp": time.time() + LOGIN_DAYS * 86400}
        _write_logins(logins)


def forget_login(token: str):
    with _logins_lock:
        logins = _logins()
        if logins.pop(token_key(token), None):
            _write_logins(logins)


def forget_user_logins(tenant: Tenant, email: str):
    with _logins_lock:
        logins = _logins()
        kept = {k: v for k, v in logins.items() if not (v["t"] == tenant.id and v["u"] == email)}
        if len(kept) != len(logins):
            _write_logins(kept)


def revive(token: str) -> "Session | None":
    if not token:
        return None
    with _revive_lock:
        if token in SESSIONS:
            return SESSIONS[token]
        saved = _logins().get(token_key(token))
        if not saved or saved["exp"] < time.time():
            return None
        try:
            tenant = Tenant(saved["t"])
        except ValueError:
            forget_login(token)
            return None
        if saved["u"] not in tenant.users():
            forget_login(token)
            return None
        SESSIONS[token] = build_session(tenant, saved["u"])
        log.info("revived a saved sign-in tenant=%s", tenant.id)
        return SESSIONS[token]


REPORT_ERRORS: dict[str, str] = {}


@asynccontextmanager
async def lifespan(_app):
    persist.restore()
    migrate_accounts()
    tracing.setup()
    if rewrapped := connections.rewrap_all():
        log.info("re-encrypted %d saved secrets under the current key", rewrapped)
    stop_scheduler = reports.start_scheduler(memory_index)
    finish_sync = persist.start_sync()
    stop_data_sync = connections.start_scheduler(refresh_live)
    async with mcp_server.server.session_manager.run():
        yield
    stop_scheduler.set()
    stop_data_sync.set()
    mcp_server.close_sessions()
    for token in list(SESSIONS):
        close_session(token)
    finish_sync()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    ref = secrets.token_hex(3)
    log.error("unexpected error ref=%s %s %s", ref, request.method, request.url.path, exc_info=exc)
    return JSONResponse({"detail": f"Something went wrong on our side. Reference: {ref}"}, status_code=500)


def current(authorization: str = Header("")) -> tuple[str, Session]:
    token = authorization.removeprefix("Bearer ")
    s = SESSIONS.get(token)
    if s and time.time() - s.last_used > SANDBOX_IDLE:
        close_session(token)
        s = None
    s = s or revive(token)
    if not s:
        raise HTTPException(401, "Please sign in again")
    return token, s


def need(permission: str):
    def check(cur=Depends(current)):
        s = cur[1]
        if permission not in permissions(s.role, s.scope):
            s.tenant.audit(s.user, "denied", permission=permission)
            raise HTTPException(403, "Your role does not allow this. Ask an owner or admin.")
        return cur
    return check


def end_user_sessions(tenant: Tenant, email: str):
    for token in [t for t, s in SESSIONS.items() if s.tenant.id == tenant.id and s.user == email]:
        close_session(token)
    forget_user_logins(tenant, email)


def session_info(s: Session) -> dict:
    return {"tenant": s.tenant.id, "workspace": s.tenant.name(), "workspaces": workspaces_of(s.user),
            "files": s.files, "knowledge": s.tenant.knowledge(), "user": s.user, "role": s.role,
            "scoped": s.scope is not None, "permissions": sorted(permissions(s.role, s.scope))}


class Login(BaseModel):
    email: str
    password: str
    workspace: str | None = None


class Member(BaseModel):
    email: str
    role: Literal[ROLES]
    scope: dict | None = None
    password: str | None = None


class Question(BaseModel):
    question: str
    context: str = ""
    images: list[str] = []
    mode: Literal["auto", "single"] = "auto"


class Feedback(BaseModel):
    question: str
    answer: str
    rating: Literal["up", "down"]
    note: str = ""
    trace: str = ""


class SignUp(BaseModel):
    workspace: str
    email: str
    password: str


class NewWorkspace(BaseModel):
    name: str


def build_session(tenant: Tenant, email: str) -> Session:
    user = tenant.users().get(email)
    if not user:
        raise HTTPException(403, "You are not a member of this workspace")
    role, scope = user["role"], user.get("scope")
    try:
        sandbox, files, overview = start_sandbox(tenant, scope)
    except Exception as exc:
        log.warning("sandbox start failed tenant=%s", tenant.id, exc_info=True)
        raise HTTPException(503, NO_START) from exc
    memory = Memory(tenant, memory_index(), email, role, scope)
    data = {"overview": overview, "live": scope is None}
    charts = tenant.output_dir / secrets.token_hex(8)
    agent = build_agent(sandbox, tenant, memory, data, chart_dir=charts)
    return Session(tenant, sandbox, agent, memory, files, email, role, scope, charts, data)


def open_session(tenant: Tenant, email: str) -> dict:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = build_session(tenant, email)
    remember_login(token, tenant, email)
    set_last_workspace(email, tenant.id)
    tenant.audit(email, "login", role=SESSIONS[token].role)
    return {"token": token, **session_info(SESSIONS[token])}


def throttle(request: Request, action: str, limit: tuple[int, int]):
    count, window = limit
    key, now = f"{action}:{request.client.host if request.client else '?'}", time.time()
    with _hits_lock:
        hits = _hits.setdefault(key, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= count:
            raise HTTPException(429, "Too many attempts. Wait a few minutes and try again.")
        hits.append(now)


@app.post("/api/signup")
def signup(body: SignUp, request: Request):
    throttle(request, "signup", SIGNUP_LIMIT)
    try:
        email = normal_email(body.email)
        new_account = not account_exists(email)
        if not new_account and not check_account(email, body.password):
            raise HTTPException(401, f"{email} already has an account and that password is wrong")
        if new_account and len(body.password) < 8:
            raise ValueError("Password must be at least 8 characters")
        tenant = create_workspace(body.workspace, email)
        if new_account:
            create_account(email, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return open_session(tenant, email)


@app.post("/api/login")
def login(body: Login, request: Request):
    throttle(request, "login", LOGIN_LIMIT)
    email = check_account(body.email, body.password)
    if not email:
        raise HTTPException(401, "Wrong email or password")
    return open_last(email, body.workspace)


def open_last(email: str, wanted: str | None = None) -> dict:
    ids = [w["id"] for w in workspaces_of(email)]
    if not ids:
        raise HTTPException(403, "You are not in any workspace yet. Create one, or ask an admin to add you.")
    pick = next((i for i in (wanted, last_workspace(email)) if i in ids), ids[0])
    return open_session(Tenant(pick), email)


class GoogleLogin(BaseModel):
    credential: str
    workspace: str = ""


def verify_google(credential: str) -> str:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(404, "Google sign-in is not set up")
    try:
        info = google_id_token.verify_oauth2_token(credential, google_requests.Request(), client_id,
                                                   clock_skew_in_seconds=10)
    except ValueError as exc:
        log.warning("google sign-in rejected: %s", exc)
        raise HTTPException(401, "Google sign-in failed. Try again.") from None
    if not info.get("email") or not info.get("email_verified"):
        raise HTTPException(401, "Your Google email address is not verified")
    return info["email"].lower()


@app.get("/api/config")
def config():
    return {"google_client_id": os.getenv("GOOGLE_CLIENT_ID") or None}


@app.post("/api/auth/google")
def google_login(body: GoogleLogin, request: Request):
    throttle(request, "login", LOGIN_LIMIT)
    email = verify_google(body.credential)
    if workspaces_of(email):
        ensure_google_account(email)
        return open_last(email)
    if not body.workspace.strip():
        return {"needs_workspace": True, "email": email}
    try:
        tenant = create_workspace(body.workspace, email)
        ensure_google_account(email)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return open_session(tenant, email)


@app.post("/api/workspaces")
def new_workspace(body: NewWorkspace, cur=Depends(current)):
    token, s = cur
    try:
        tenant = create_workspace(body.name, s.user)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    opened = open_session(tenant, s.user)
    end_session(token)
    return opened


@app.post("/api/workspaces/{tenant_id}/open")
def switch_workspace(tenant_id: str, cur=Depends(current)):
    token, s = cur
    if tenant_id not in [w["id"] for w in workspaces_of(s.user)]:
        raise HTTPException(403, "You are not a member of this workspace")
    opened = open_session(Tenant(tenant_id), s.user)
    end_session(token)
    return opened


@app.get("/api/me")
def me(cur=Depends(current)):
    return session_info(cur[1])


@app.delete("/api/session")
def logout(cur=Depends(current)):
    end_session(cur[0])
    return {"ok": True}


@app.post("/api/ask")
def ask_route(body: Question, cur=Depends(current)):
    _, s = cur
    question = body.question.strip()
    if not question or len(question) > MAX_QUESTION:
        raise HTTPException(400, f"Question must be 1-{MAX_QUESTION} characters")
    context = body.context.strip()
    if len(context) > MAX_CONTEXT:
        raise HTTPException(400, f"The marked area is too big (over {MAX_CONTEXT} characters). Circle less.")
    images = [i.strip() for i in body.images if i.strip()]
    if len(images) > MAX_IMAGES:
        raise HTTPException(400, f"Circle at most {MAX_IMAGES} areas per question.")
    if sum(map(len, images)) > MAX_IMAGE or not all(IMAGE_URL.fullmatch(i) for i in images):
        raise HTTPException(400, "The circled images are too big or not pictures. Circle smaller areas.")
    log.info("ask tenant=%s circled=%d chars images=%d", s.tenant.id, len(context), len(images))
    s.tenant.audit(s.user, "ask", question=question[:300], circled=len(context), images=len(images))
    if context or images:
        question += "\n\n[The user circled parts of the board with the AI marker; the question is about them."
        question += f" The {len(images)} attached image(s) show exactly what they circled, in order.]" if images else "]"
    if context:
        question += f"\n{context}"
    if not s.lock.acquire(blocking=False):
        raise HTTPException(409, "Still working on your previous question")
    events = queue.Queue()
    s.stop.clear()

    def work():
        try:
            before = set(s.charts.glob("chart_*.png"))
            crew = TeamContext(s.tenant, s.data, list(s.files), s.charts) if body.mode == "auto" else None
            outputs = []

            def step(event):
                if event.get("type") == "output":
                    outputs.append(str(event.get("output", "")))
                events.put(event)

            with tracing.question(s.tenant.id, s.user, s.role, body.mode, question) as run:
                s.messages, answer, calls = ask(s.agent, s.sandbox, s.memory, s.messages, question, on_step=step,
                                                should_stop=s.stop.is_set, images=images, team=crew)
                tracing.finish(run, answer, outputs, calls)
            s.last_used = time.time()
            new_charts = sorted(set(s.charts.glob("chart_*.png")) - before, key=lambda p: p.stat().st_mtime)
            events.put({
                "type": "done",
                "answer": answer or f"I hit the limit of {MAX_LLM_CALLS} steps without a final answer. Try a narrower question.",
                "calls": calls,
                "trace": str(run.id) if run else None,
                "charts": ["data:image/png;base64," + base64.b64encode(p.read_bytes()).decode() for p in new_charts],
            })
        except Stopped:
            events.put({"type": "stopped"})
        except Exception as exc:
            message = friendly(exc)
            if message is None and isinstance(exc, SandboxException):
                try:
                    restart_sandbox(s)
                    message = RESTARTED
                except Exception:
                    log.error("sandbox restart failed tenant=%s", s.tenant.id, exc_info=True)
                    message = NO_RESTART
            if message is None:
                ref = secrets.token_hex(3)
                log.error("unexpected error ref=%s ask tenant=%s", ref, s.tenant.id, exc_info=True)
                events.put({"type": "error", "message": f"Something went wrong on our side. Reference: {ref}", "retry": False})
            else:
                log.warning("ask failed tenant=%s: %s", s.tenant.id, message, exc_info=True)
                events.put({"type": "error", "message": message, "retry": True})
        finally:
            s.lock.release()
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (event := events.get()) is not None:
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.post("/api/ask/stop")
def stop_ask(cur=Depends(current)):
    cur[1].stop.set()
    return {"ok": True}


@app.post("/api/feedback")
def feedback(body: Feedback, cur=Depends(current)):
    _, s = cur
    question, answer, note = body.question.strip()[:500], body.answer.strip()[:600], body.note.strip()[:1000]
    if not question:
        raise HTTPException(400, "Missing the question this feedback is about")
    if body.rating == "down":
        kind = "correction" if note else "dislike"
        text = f"The user marked an answer as wrong or unhelpful. Question: {question}. " + (
            f"What was wrong: {note}" if note else "No reason given.")
    else:
        kind = "liked"
        text = f"The user found this answer useful. Question: {question}. Answer began: {answer[:300]}"
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": s.user, "rating": body.rating, "question": question,
             "note": note}
    with _feedback_lock, (s.tenant.dir / "feedback.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    try:
        s.memory.remember(text, kind)
        remembered = True
    except Exception:
        log.warning("feedback not saved to memory tenant=%s", s.tenant.id, exc_info=True)
        remembered = False
    traced = bool(body.trace) and tracing.user_feedback(body.trace, s.tenant.id, s.user, body.rating, note)
    return {"ok": True, "remembered": remembered, "traced": traced}


@app.get("/api/reports")
def list_reports(cur=Depends(need("reports"))):
    t = cur[1].tenant
    return {"settings": reports.load_settings(t), "reports": reports.list_reports(t),
            "running": t.id in reports._running, "error": REPORT_ERRORS.get(t.id)}


@app.get("/api/reports/{name}")
def get_report(name: str, cur=Depends(need("reports"))):
    try:
        return {"name": name, "html": reports.report_html(cur[1].tenant, name)}
    except FileNotFoundError:
        raise HTTPException(404, "Report not found") from None


@app.post("/api/reports/run", status_code=202)
def run_report(cur=Depends(need("reports.manage"))):
    t = cur[1].tenant
    t.audit(cur[1].user, "report run")
    if t.id in reports._running:
        raise HTTPException(409, "This week's report is already being created")
    REPORT_ERRORS.pop(t.id, None)

    def work():
        try:
            reports.generate(t, memory_index())
        except Exception as exc:
            log.warning("manual report failed tenant=%s", t.id, exc_info=True)
            REPORT_ERRORS[t.id] = friendly(exc) or "Could not create the report. Try again in a few minutes."

    threading.Thread(target=work, name=f"report-{t.id}", daemon=True).start()
    return {"started": True}


@app.put("/api/reports/settings")
def put_report_settings(body: dict, cur=Depends(need("reports.manage"))):
    try:
        settings = reports.save_settings(cur[1].tenant, body)
        cur[1].tenant.audit(cur[1].user, "report settings", enabled=settings["enabled"],
                            recipients=len(settings["recipients"]))
        return {"settings": settings}
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/upload")
def upload(file: UploadFile, cur=Depends(need("upload"))):
    _, s = cur
    name = Path(file.filename or "").name
    if not name or name.startswith(".") or Path(name).suffix.lower() not in DATA_SUFFIXES:
        raise HTTPException(400, f"Allowed file types: {', '.join(sorted(DATA_SUFFIXES))}")
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File is larger than 50 MB")
    if not looks_readable(name, data):
        raise HTTPException(400, "We could not read this file. Save it again as CSV or XLSX and upload it again.")
    s.tenant.data_dir.mkdir(parents=True, exist_ok=True)
    (s.tenant.data_dir / name).write_bytes(data)
    s.tenant.audit(s.user, "upload", file=name, bytes=len(data))
    if name not in s.files:
        s.files.append(name)
    try:
        s.sandbox.files.write(f"{SANDBOX_DATA}/{name}", data)
        s.data["overview"] = preload(s.sandbox, [name])
    except SandboxException:
        log.warning("sandbox gone during upload tenant=%s, restarting", s.tenant.id, exc_info=True)
        restart_sandbox(s)
    return session_info(s)


class Source(BaseModel):
    kind: str
    details: str = ""
    secrets: dict[str, str] = {}


TABLE_NAME = re.compile(r"[^a-z0-9_]+")
BLOCKED_SOURCE = re.compile(r"stripe|razorpay|rzp_(live|test)_", re.I)
BLOCKED_KEY = re.compile(r"(sk|rk|pk)_(live|test)_|rzp_(live|test)_")


def store_table(s: "Session", name: str, data: bytes) -> tuple[str | None, str]:
    clean = TABLE_NAME.sub("_", name.lower()).strip("_")[:40] or "table"
    file_name = f"{clean}.csv"
    if len(data) > MAX_UPLOAD:
        return None, "not saved: the table is larger than 50 MB. Filter or aggregate it, then save again."
    if not looks_readable(file_name, data):
        return None, "not saved: the file is empty or not a text CSV."
    s.tenant.data_dir.mkdir(parents=True, exist_ok=True)
    (s.tenant.data_dir / file_name).write_bytes(data)
    if file_name not in s.files:
        s.files.append(file_name)
    try:
        s.sandbox.files.write(f"{SANDBOX_DATA}/{file_name}", data)
        s.data["overview"] = preload(s.sandbox, [file_name])
    except SandboxException:
        log.warning("sandbox gone while saving a connected table tenant=%s, restarting", s.tenant.id, exc_info=True)
        restart_sandbox(s)
    return file_name, f"saved as {file_name}; the analyst can use it now"


@app.post("/api/sources")
def connect_source(body: Source, cur=Depends(need("upload"))):
    _, s = cur
    spec = SOURCES.get(body.kind)
    if not spec:
        raise HTTPException(400, "Pick a data source")
    details = body.details.strip()
    if len(details) > 2000:
        raise HTTPException(400, "Keep the details under 2000 characters")
    if spec["needs_details"] and not details:
        raise HTTPException(400, "Add the link or details for this source")
    if BLOCKED_SOURCE.search(details) or any(BLOCKED_KEY.match(v.strip()) for v in body.secrets.values()):
        raise HTTPException(400, "Stripe and Razorpay are not supported as data sources.")
    keys = {k: v.strip() for k, v in body.secrets.items() if v.strip()}
    if set(keys) - set(spec["secrets"]) or any(len(v) > 20000 for v in keys.values()):
        raise HTTPException(400, "Unexpected or oversized secret for this source")
    missing = [k for k in spec["secrets"] if k not in keys]
    if missing and not spec.get("optional_secrets"):
        raise HTTPException(400, f"Fill in: {', '.join(missing)}")
    if s.importing:
        raise HTTPException(409, "Already connecting a source. Wait for it to finish.")
    s.importing = True
    s.tenant.audit(s.user, "data connect", source=body.kind)
    events = queue.Queue()
    saved = []

    def on_table(name, data):
        file_name, message = store_table(s, name, data)
        if file_name:
            saved.append(file_name)
            s.tenant.audit(s.user, "upload", file=file_name, bytes=len(data), source=body.kind)
            events.put({"type": "table", "name": file_name, "bytes": len(data)})
        return message

    def work():
        try:
            note = run_import(body.kind, details, keys, events.put, on_table, s.charts)
            if saved and note:
                s.tenant.add_data_note(body.kind, saved, note)
                s.agent = build_agent(s.sandbox, s.tenant, s.memory, s.data, chart_dir=s.charts)
            events.put({"type": "done", "note": note or "The connector ran out of steps before writing its note.",
                        "tables": saved, "session": session_info(s)})
        except Exception as exc:
            message = friendly(exc)
            if message is None:
                ref = secrets.token_hex(3)
                log.error("unexpected error ref=%s connect tenant=%s kind=%s", ref, s.tenant.id, body.kind, exc_info=True)
                message = f"Something went wrong while connecting. Reference: {ref}"
            events.put({"type": "error", "message": message, "tables": saved, "session": session_info(s)})
        finally:
            s.importing = False
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (event := events.get()) is not None:
            yield json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


def refresh_live(tenant: Tenant, files: list[str]):
    for s in [s for s in list(SESSIONS.values()) if s.tenant.id == tenant.id and s.scope is None]:
        try:
            for name in files:
                s.sandbox.files.write(f"{SANDBOX_DATA}/{name}", (tenant.data_dir / name).read_bytes())
                if name not in s.files:
                    s.files.append(name)
            s.data["overview"] = preload(s.sandbox, files)
            s.agent = build_agent(s.sandbox, s.tenant, s.memory, s.data, chart_dir=s.charts)
        except Exception:
            log.warning("could not push synced tables into a live session tenant=%s", tenant.id, exc_info=True)


class Connection(BaseModel):
    kind: str
    config: dict = {}
    secrets: dict[str, str] = {}


class McpProbe(BaseModel):
    url: str
    token: str = ""
    grant: str = ""


class McpSignIn(BaseModel):
    url: str


def start_sync(t: Tenant, conn_id: str):
    threading.Thread(target=connections.sync, args=(t, conn_id, refresh_live), daemon=True).start()


def public_url(request: Request) -> str:
    return os.getenv("PUBLIC_URL", "").rstrip("/") or str(request.base_url).rstrip("/")


@app.get("/api/connections")
def list_connections(cur=Depends(need("upload"))):
    return connections.overview(cur[1].tenant)


@app.post("/api/connections")
def add_connection(body: Connection, cur=Depends(need("upload"))):
    s = cur[1]
    if body.kind not in CONNECTORS:
        raise HTTPException(400, "Pick a data source")
    if len(json.dumps(body.config)) > 20000 or any(len(v) > 20000 for v in body.secrets.values()):
        raise HTTPException(400, "That value is too long")
    try:
        signed_in = None
        if body.kind == "mcp" and body.secrets.get("grant"):
            signed_in = mcp_auth.take(body.secrets["grant"], s.tenant.id, s.user, str(body.config.get("url", "")))
        item = connections.create(s.tenant, body.kind, body.config, body.secrets, s.user, signed_in=signed_in)
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    s.tenant.audit(s.user, "data connected", source=body.kind, label=item["label"])
    start_sync(s.tenant, item["id"])
    return {**item, "syncing": True}


@app.delete("/api/connections/google")
def google_disconnect(cur=Depends(need("upload"))):
    s = cur[1]
    connections.forget_google(s.tenant)
    s.tenant.audit(s.user, "google disconnected")
    return {"ok": True}


@app.post("/api/connections/{conn_id}/sync", status_code=202)
def sync_connection(conn_id: str, cur=Depends(need("upload"))):
    s = cur[1]
    if not any(i["id"] == conn_id for i in connections.overview(s.tenant)["items"]):
        raise HTTPException(404, "No such connection")
    start_sync(s.tenant, conn_id)
    return {"started": True}


@app.delete("/api/connections/{conn_id}")
def remove_connection(conn_id: str, cur=Depends(need("upload"))):
    s = cur[1]
    if not connections.remove(s.tenant, conn_id):
        raise HTTPException(404, "No such connection")
    s.tenant.audit(s.user, "data disconnected", connection=conn_id)
    return {"ok": True}


@app.get("/api/connections/google/start")
def google_connect_start(request: Request, cur=Depends(need("upload"))):
    s = cur[1]
    if not (os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")):
        raise HTTPException(400, "Google connections are not set up on this server (GOOGLE_CLIENT_SECRET is missing).")
    state = connections.sign_state({"t": s.tenant.id, "u": s.user})
    return {"url": connections.google_auth_url(state, public_url(request) + "/api/oauth/google/callback")}


@app.get("/api/oauth/google/callback")
def google_connect_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    claims = connections.read_state(state) if state else None
    if not claims or error or not code:
        return RedirectResponse("/?google=failed", status_code=303)
    try:
        tenant = Tenant(claims["t"])
        if claims["u"] not in tenant.users():
            return RedirectResponse("/?google=failed", status_code=303)
        email, refresh_token = connections.google_exchange(code, public_url(request) + "/api/oauth/google/callback")
    except (SourceError, ValueError, KeyError):
        log.warning("google connect failed", exc_info=True)
        return RedirectResponse("/?google=failed", status_code=303)
    connections.save_google(tenant, email, refresh_token, claims["u"])
    tenant.audit(claims["u"], "google connected", account=email)
    return RedirectResponse("/?google=connected", status_code=303)


@app.post("/api/connections/mcp/inspect")
def mcp_source_inspect(body: McpProbe, request: Request, cur=Depends(need("upload"))):
    throttle(request, "mcp-inspect", LOGIN_LIMIT)
    s = cur[1]
    try:
        token = mcp_auth.token_for(body.grant, s.tenant.id, s.user, body.url) if body.grant else body.token.strip()
        found = sources.mcp_inspect(body.url, token)
    except sources.NeedsSignIn as exc:
        return {"needs_signin": True, "message": str(exc)}
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        found["signin"] = mcp_auth.resource_metadata(sources.mcp_url(body.url)) is not None
    except SourceError:
        found["signin"] = False
    return found


@app.post("/api/connections/mcp/signin")
def mcp_source_signin(body: McpSignIn, request: Request, cur=Depends(need("upload"))):
    throttle(request, "mcp-signin", LOGIN_LIMIT)
    s = cur[1]
    try:
        grant, url = mcp_auth.start(s.tenant.id, s.user, body.url, public_url(request))
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"grant": grant, "url": url}


@app.get("/api/connections/mcp/signin/{grant}")
def mcp_source_signin_status(grant: str, cur=Depends(need("upload"))):
    s = cur[1]
    try:
        pending = mcp_auth.lookup(grant, s.tenant.id, s.user)
    except SourceError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"status": pending["status"], "message": pending["message"]}


@app.get(mcp_auth.CLIENT_DOC)
def mcp_client_document(request: Request):
    return mcp_auth.client_document(public_url(request))


@app.get(mcp_auth.CALLBACK, response_class=HTMLResponse)
def mcp_source_callback(state: str = "", code: str = "", error: str = ""):
    pending = mcp_auth.finish(state, code, error)
    ok = pending is not None and pending["status"] == "ready"
    if pending is not None:
        Tenant(pending["tenant"]).audit(pending["user"], "mcp source signed in" if ok else "mcp source sign-in failed",
                                        server=urlparse(pending["url"]).hostname)
    text = "Signed in. You can close this window and pick your tools in Analyst Buddy." if ok else \
        html.escape(pending["message"] if pending else "This sign-in link expired. Start again from Analyst Buddy.")
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                        f"<title>Analyst Buddy</title><body style='font:16px system-ui;padding:40px;max-width:520px;margin:auto'>"
                        f"<h2>{'Connected' if ok else 'Not connected'}</h2><p>{text}</p>"
                        f"<script>{'setTimeout(()=>window.close(),1200)' if ok else ''}</script>")


@app.get("/api/connections/ga4/properties")
def ga4_properties(cur=Depends(need("upload"))):
    try:
        return {"properties": sources.ga4_properties(connections.google_secret(cur[1].tenant), sources.new_http())}
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc


class McpToken(BaseModel):
    name: str = ""
    access: Literal["read", "full"] = "read"


@app.get("/api/mcp/tokens")
def mcp_tokens(request: Request, cur=Depends(current)):
    s = cur[1]
    everyone = "users" in permissions(s.role, s.scope)
    return {"url": public_url(request) + "/mcp", "can_manage_all": everyone,
            "tokens": mcp_server.list_tokens(s.tenant, None if everyone else s.user)}


@app.post("/api/mcp/tokens")
def mcp_token_create(body: McpToken, cur=Depends(current)):
    s = cur[1]
    if len(mcp_server.list_tokens(s.tenant, s.user)) >= 10:
        raise HTTPException(400, "You have 10 tokens already. Revoke one first.")
    token, record = mcp_server.create_token(s.tenant, s.user, body.name, body.access)
    s.tenant.audit(s.user, "mcp token created", name=record["name"], access=body.access)
    return {"token": token, **record}


@app.delete("/api/mcp/tokens/{token_id}")
def mcp_token_revoke(token_id: str, cur=Depends(current)):
    s = cur[1]
    everyone = "users" in permissions(s.role, s.scope)
    if not mcp_server.revoke_token(s.tenant, token_id, None if everyone else s.user):
        raise HTTPException(404, "No such token")
    s.tenant.audit(s.user, "mcp token revoked", token=token_id)
    return {"ok": True}


def oauth_error(exc: "mcp_oauth.OAuthError", status: int = 400) -> JSONResponse:
    return JSONResponse({"error": exc.error, "error_description": exc.description}, status_code=status,
                        headers={"Cache-Control": "no-store"})


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
def oauth_resource(request: Request):
    return mcp_oauth.resource_metadata(public_url(request))


@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/oauth-authorization-server/mcp")
@app.get("/.well-known/openid-configuration")
def oauth_server(request: Request):
    return mcp_oauth.metadata(public_url(request))


@app.post("/oauth/register", status_code=201)
async def oauth_register(request: Request):
    throttle(request, "oauth-register", SIGNUP_LIMIT)
    try:
        body = await request.json()
        return mcp_oauth.register(body if isinstance(body, dict) else {})
    except mcp_oauth.OAuthError as exc:
        log.warning("oauth register refused: %s redirect_uris=%r", exc, body.get("redirect_uris") if isinstance(body, dict) else body)
        return oauth_error(exc)
    except ValueError:
        return oauth_error(mcp_oauth.OAuthError("invalid_client_metadata", "Send the registration as JSON."))


@app.get("/oauth/authorize")
def oauth_authorize(request: Request):
    try:
        rid = mcp_oauth.start(dict(request.query_params))
    except mcp_oauth.OAuthError as exc:
        return oauth_error(exc)
    return RedirectResponse(f"/?mcp_consent={rid}", status_code=302)


@app.post("/oauth/token")
async def oauth_token(request: Request):
    throttle(request, "oauth-token", LOGIN_LIMIT)
    form = {k: str(v) for k, v in (await request.form()).items()}
    try:
        return JSONResponse(mcp_oauth.token(form), headers={"Cache-Control": "no-store"})
    except mcp_oauth.OAuthError as exc:
        return oauth_error(exc)


class Consent(BaseModel):
    allow: bool
    access: Literal["read", "full"] = "read"


@app.get("/api/mcp/oauth/{rid}")
def oauth_consent_info(rid: str, cur=Depends(current)):
    info = mcp_oauth.describe(rid)
    if not info:
        raise HTTPException(404, "This connection request has expired. Start again from Claude.")
    return info


@app.post("/api/mcp/oauth/{rid}")
def oauth_consent(rid: str, body: Consent, cur=Depends(current)):
    s = cur[1]
    info = mcp_oauth.describe(rid)
    url = mcp_oauth.decide(rid, body.allow, s.tenant.id, s.user, body.access)
    if not url:
        raise HTTPException(404, "This connection request has expired. Start again from Claude.")
    s.tenant.audit(s.user, "mcp app connected" if body.allow else "mcp app denied", client=info["client_name"] if info else "",
                   access=body.access if body.allow else None)
    return {"redirect": url}


class Goals(BaseModel):
    goals: list[str]


def rebuild_agents(tenant: Tenant):
    for live in [x for x in list(SESSIONS.values()) if x.tenant.id == tenant.id]:
        live.agent = build_agent(live.sandbox, live.tenant, live.memory, live.data, chart_dir=live.charts)


@app.put("/api/goals")
def put_goals(body: Goals, cur=Depends(need("teach"))):
    s = cur[1]
    before = s.tenant.knowledge().get("goals", [])
    try:
        goals = s.tenant.save_goals(body.goals)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    rebuild_agents(s.tenant)
    s.tenant.audit(s.user, "goals changed", added=[g for g in goals if g not in before][:5],
                   removed=[g for g in before if g not in goals][:5])
    return session_info(s)


@app.delete("/api/data/{name}")
def delete_data(name: str, cur=Depends(need("upload"))):
    s = cur[1]
    files = {f.name: f for f in s.tenant.data_dir.glob("*") if f.suffix.lower() in DATA_SUFFIXES} if s.tenant.data_dir.exists() else {}
    if name not in files:
        raise HTTPException(404, "No data file with that name")
    files[name].unlink()
    s.tenant.forget_tables([name])
    for live in [x for x in list(SESSIONS.values()) if x.tenant.id == s.tenant.id]:
        if name in live.files:
            live.files.remove(name)
        try:
            live.sandbox.run_code(f"dfs.pop({name!r}, None)\nimport os\nos.path.exists({SANDBOX_DATA + '/' + name!r}) and os.remove({SANDBOX_DATA + '/' + name!r})")
            live.data["overview"] = preload(live.sandbox, [])
        except Exception:
            log.warning("could not drop %s from a live sandbox tenant=%s", name, s.tenant.id, exc_info=True)
        live.agent = build_agent(live.sandbox, live.tenant, live.memory, live.data, chart_dir=live.charts)
    s.tenant.audit(s.user, "data deleted", file=name)
    return session_info(s)


@app.get("/api/users")
def list_users(cur=Depends(need("users"))):
    t = cur[1].tenant
    files = sorted(f.name for f in t.data_dir.glob("*") if f.suffix.lower() in DATA_SUFFIXES)
    return {"users": [public_user(e, u) for e, u in sorted(t.users().items())], "files": files,
            "audit": t.audit_log()}


def check_can_manage(s: Session, email: str, role: str | None = None):
    if email == s.user:
        raise HTTPException(400, "You cannot change your own access. Ask another owner or admin.")
    target = s.tenant.users().get(email)
    if s.role != "owner" and ((target and target["role"] == "owner") or role == "owner"):
        raise HTTPException(403, "Only an owner can add, change or remove owners")


@app.post("/api/users")
def add_user(body: Member, cur=Depends(need("users"))):
    s, email = cur[1], body.email.strip().lower()
    check_can_manage(s, email, body.role)
    new_account = not account_exists(email)
    google_only = new_account and not body.password and bool(os.getenv("GOOGLE_CLIENT_ID"))
    if new_account and not google_only and len(body.password or "") < 8:
        raise HTTPException(400, f"{email} has no account yet. Set a first password of at least 8 characters.")
    try:
        member = s.tenant.save_user(email, body.role, body.scope, new=True)
        if new_account and not google_only:
            create_account(email, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    s.tenant.audit(s.user, "member added", member=member["email"], role=body.role, scoped=body.scope is not None,
                   new_account=new_account)
    return {**member, "joins": "google" if google_only else "password" if new_account else "existing"}


@app.put("/api/users/{email}")
def update_user(email: str, body: Member, cur=Depends(need("users"))):
    s, email = cur[1], email.strip().lower()
    check_can_manage(s, email, body.role)
    try:
        member = s.tenant.save_user(email, body.role, body.scope)
    except KeyError:
        raise HTTPException(404, "No such member") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    end_user_sessions(s.tenant, email)
    s.tenant.audit(s.user, "member changed", member=email, role=body.role, scoped=body.scope is not None)
    return member


@app.delete("/api/users/{email}")
def remove_user(email: str, cur=Depends(need("users"))):
    s, email = cur[1], email.strip().lower()
    check_can_manage(s, email)
    try:
        s.tenant.remove_user(email)
    except KeyError:
        raise HTTPException(404, "No such member") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    end_user_sessions(s.tenant, email)
    s.tenant.audit(s.user, "member removed", member=email)
    return {"ok": True}


def looks_readable(name: str, data: bytes) -> bool:
    suffix = Path(name).suffix.lower()
    if not data.strip():
        return False
    if suffix in FILE_MAGIC:
        return data.startswith(FILE_MAGIC[suffix])
    if suffix == ".json":
        try:
            json.loads(data)
            return True
        except ValueError:
            return False
    return b"\x00" not in data[:65536]


mcp_server.attach(app, sys.modules[__name__])

if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
