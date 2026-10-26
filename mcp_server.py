import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

import connections
import reports
from agent import READERS, apply_scope
from connector import run_import
from team import TeamContext
from team import answer as ask
from tenants import PERMISSIONS, Tenant, permissions

TOKENS_FILE = Path(__file__).parent / "mcp_tokens.json"
TOKEN_PREFIX = "ab_mcp_"
READ_ONLY = PERMISSIONS["viewer"]
CALL_LIMIT = (60, 60)
log = logging.getLogger("mcp")
_tokens_lock = threading.Lock()
_calls: dict[str, list[float]] = {}
SESSIONS: dict[str, object] = {}
_session_lock = threading.Lock()
srv = None


@dataclass
class Caller:
    key: str
    tenant: Tenant
    user: str
    role: str
    scope: dict | None
    access: str
    perms: set


def token_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _load() -> dict:
    return json.loads(TOKENS_FILE.read_text(encoding="utf-8")) if TOKENS_FILE.exists() else {}


def _save(tokens: dict):
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")


def create_token(tenant: Tenant, user: str, name: str, access: str) -> tuple[str, dict]:
    if access not in ("read", "full"):
        raise ValueError("Access must be read or full")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    record = {"id": secrets.token_hex(6), "t": tenant.id, "u": user, "name": name.strip()[:60] or "MCP client",
              "access": access, "created": now_iso(), "last_used": None, "kind": "pat"}
    with _tokens_lock:
        tokens = _load()
        tokens[token_key(token)] = record
        _save(tokens)
    return token, record


ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def issue_grant(tenant_id: str, user: str, access: str, client_name: str, grant_id: str | None = None) -> dict:
    grant_id = grant_id or secrets.token_hex(6)
    access_token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    refresh_token = "ab_rt_" + secrets.token_urlsafe(40)
    base = {"id": grant_id, "t": tenant_id, "u": user, "name": client_name[:60] or "Connected app", "access": access,
            "created": now_iso(), "last_used": None}
    with _tokens_lock:
        tokens = _load()
        old = {k: r for k, r in tokens.items() if r["id"] == grant_id}
        for k, r in old.items():
            base["created"], base["last_used"] = r.get("created", base["created"]), r.get("last_used")
            del tokens[k]
        tokens[token_key(access_token)] = {**base, "kind": "access", "exp": time.time() + ACCESS_TTL}
        tokens[token_key(refresh_token)] = {**base, "kind": "refresh", "exp": time.time() + REFRESH_TTL}
        _save(tokens)
    return {"access_token": access_token, "token_type": "Bearer", "expires_in": ACCESS_TTL, "refresh_token": refresh_token,
            "scope": f"mcp:{access}"}


def use_refresh_token(refresh_token: str) -> dict | None:
    with _tokens_lock:
        record = _load().get(token_key(refresh_token))
    if not record or record.get("kind") != "refresh" or record["exp"] < time.time():
        return None
    try:
        member = Tenant(record["t"]).users().get(record["u"])
    except ValueError:
        member = None
    if not member:
        return None
    return issue_grant(record["t"], record["u"], record["access"], record["name"], record["id"])


def list_tokens(tenant: Tenant, user: str | None = None) -> list[dict]:
    return [{k: v for k, v in r.items() if k not in ("exp",)} for r in _load().values()
            if r["t"] == tenant.id and (user is None or r["u"] == user) and r.get("kind", "pat") != "access"]


def revoke_token(tenant: Tenant, token_id: str, user: str | None = None) -> bool:
    with _tokens_lock:
        tokens = _load()
        match = [k for k, r in tokens.items() if r["id"] == token_id and r["t"] == tenant.id and (user is None or r["u"] == user)]
        for k in match:
            del tokens[k]
        if match:
            SESSIONS.pop(token_id, None)
        if match:
            _save(tokens)
    return bool(match)


def resolve(authorization: str) -> Caller | None:
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith(TOKEN_PREFIX):
        return None
    key = token_key(token)
    record = _load().get(key)
    if not record or record.get("kind") == "refresh" or record.get("exp", float("inf")) < time.time():
        return None
    try:
        tenant = Tenant(record["t"])
    except ValueError:
        return None
    member = tenant.users().get(record["u"])
    if not member:
        return None
    role, scope = member["role"], member.get("scope")
    perms = set(permissions(role, scope))
    if record["access"] == "read":
        perms &= READ_ONLY
    return Caller(record["id"], tenant, record["u"], role, scope, record["access"], perms)


def touch(caller: Caller):
    with _tokens_lock:
        tokens = _load()
        for record in tokens.values():
            if record["id"] == caller.key:
                record["last_used"] = now_iso()
        _save(tokens)


def allowed_rate(caller: Caller) -> bool:
    count, window = CALL_LIMIT
    now = time.time()
    hits = [t for t in _calls.get(caller.key, []) if now - t < window]
    _calls[caller.key] = hits + [now]
    return len(hits) < count


def visible_files(caller: Caller) -> list[str]:
    files = sorted(f.name for f in caller.tenant.data_dir.glob("*") if f.suffix.lower() in READERS) \
        if caller.tenant.data_dir.exists() else []
    return files if caller.scope is None else [f for f in files if f in caller.scope]


def session_for(caller: Caller):
    with _session_lock:
        s = SESSIONS.get(caller.key)
        if s is not None and (time.time() - s.last_used > srv.SANDBOX_IDLE or s.role != caller.role or s.scope != caller.scope):
            SESSIONS.pop(caller.key, None)
            try:
                s.sandbox.kill()
            except Exception:
                pass
            s = None
        if s is None:
            s = srv.build_session(caller.tenant, caller.user)
            SESSIONS[caller.key] = s
        s.last_used = time.time()
        return s


def text(body) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=body if isinstance(body, str) else json.dumps(body, indent=2, ensure_ascii=False))])


def error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=message)], is_error=True)


def t_list_tables(caller, args):
    notes = caller.tenant.knowledge().get("data_notes", []) if caller.scope is None else []
    return {"tables": visible_files(caller), "notes": [n["note"] for n in notes[-6:]]}


def t_describe_table(caller, args):
    name = str(args.get("name", ""))
    if name not in visible_files(caller):
        return error(f"No table named {name!r} that you can see. Call list_tables first.")
    path = caller.tenant.data_dir / name
    try:
        df = READERS[path.suffix.lower()](path)
    except Exception:
        return error(f"{name} cannot be read here; ask_analyst can still use it.")
    if caller.scope is not None:
        df = apply_scope(df, caller.scope[name])
    return {"table": name, "rows": len(df), "columns": {c: str(t) for c, t in df.dtypes.items()},
            "sample": json.loads(df.head(5).to_json(orient="records", date_format="iso"))}


def t_ask_analyst(caller, args):
    question = str(args.get("question", "")).strip()
    if not question or len(question) > srv.MAX_QUESTION:
        return error(f"Ask a question of 1-{srv.MAX_QUESTION} characters.")
    s = session_for(caller)
    if not s.lock.acquire(blocking=False):
        return error("Still working on your previous question.")
    try:
        events = []
        crew = TeamContext(s.tenant, s.data, list(s.files), s.charts) if args.get("team", True) else None
        caller.tenant.audit(caller.user, "ask", question=question[:300], via="mcp")
        s.messages, final, calls = ask(s.agent, s.sandbox, s.memory, s.messages, question, on_step=events.append,
                                       should_stop=lambda: False, team=crew)
        checks = [e["text"] for e in events if e.get("type") == "stage" and e.get("agent") == "Verifier" and e["text"][:1] in "✓✗"]
        return {"answer": final or "The analyst ran out of steps without a final answer. Ask a narrower question.",
                "verified_checks": checks, "llm_calls": calls,
                "code_runs": sum(1 for e in events if e.get("type") == "call")}
    finally:
        s.last_used = time.time()
        s.lock.release()


def t_list_reports(caller, args):
    return {"reports": reports.list_reports(caller.tenant)}


def t_get_report(caller, args):
    try:
        return reports.report_html(caller.tenant, str(args.get("date", "")))
    except FileNotFoundError:
        return error("No report for that date. Call list_reports first.")


def t_list_connections(caller, args):
    return connections.overview(caller.tenant)["items"]


def t_sync_connection(caller, args):
    conn_id = str(args.get("connection_id", ""))
    if not any(i["id"] == conn_id for i in connections.overview(caller.tenant)["items"]):
        return error("No such connection. Call list_connections first.")
    caller.tenant.audit(caller.user, "data sync", connection=conn_id, via="mcp")
    return connections.sync(caller.tenant, conn_id, srv.refresh_live)


def t_add_data_from_link(caller, args):
    url = str(args.get("url", "")).strip()
    if not url.startswith(("https://", "http://")) or len(url) > 2000:
        return error("Give a full http(s) link to a CSV, Excel, JSON or Parquet file.")
    if srv.BLOCKED_SOURCE.search(url):
        return error("Stripe and Razorpay are not supported as data sources.")
    s = session_for(caller)
    saved = []

    def on_table(name, data):
        file_name, message = srv.store_table(s, name, data)
        if file_name:
            saved.append(file_name)
            caller.tenant.audit(caller.user, "upload", file=file_name, bytes=len(data), source="url", via="mcp")
        return message

    note = run_import("url", f"Link to the file: {url}", {}, lambda e: None, on_table, s.charts)
    if saved and note:
        caller.tenant.add_data_note("url", saved, note)
    return {"tables": saved, "note": note or "The data agent ran out of steps."}


def t_create_report_now(caller, args):
    if caller.tenant.id in reports._running:
        return error("This week's report is already being created.")
    caller.tenant.audit(caller.user, "report run", via="mcp")
    threading.Thread(target=reports.generate, args=(caller.tenant, srv.memory_index()), daemon=True).start()
    return "Started. It takes a few minutes; then call list_reports."


def t_list_members(caller, args):
    from tenants import public_user
    return [public_user(e, u) for e, u in sorted(caller.tenant.users().items())]


def t_activity_log(caller, args):
    return caller.tenant.audit_log(min(int(args.get("limit", 50) or 50), 200))


def schema(props: dict | None = None, required: list | None = None) -> dict:
    return {"type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}


TOOLS = {
    "list_tables": (None, t_list_tables, "List the data tables you can see in this workspace, with the data agent's notes.", schema()),
    "describe_table": (None, t_describe_table, "Show a table's row count, column types and 5 sample rows (only the rows and columns you are allowed to see).",
                       schema({"name": {"type": "string", "description": "Table file name from list_tables"}}, ["name"])),
    "ask_analyst": (None, t_ask_analyst, "Ask Analyst Buddy a business question. A supervisor plans, parallel analysts run Python on your data, a verifier rechecks the key numbers and a writer answers. Can take a few minutes.",
                    schema({"question": {"type": "string"}, "team": {"type": "boolean", "description": "Use the agent team (default true); false = one faster analyst"}}, ["question"])),
    "list_reports": ("reports", t_list_reports, "List the weekly reports.", schema()),
    "get_report": ("reports", t_get_report, "Get one weekly report as HTML.", schema({"date": {"type": "string", "description": "YYYY-MM-DD from list_reports"}}, ["date"])),
    "list_connections": ("upload", t_list_connections, "List saved data connections (Google Sheets, GA4, Shopify) and their sync status.", schema()),
    "sync_connection": ("upload", t_sync_connection, "Refresh one saved data connection now.", schema({"connection_id": {"type": "string"}}, ["connection_id"])),
    "add_data_from_link": ("upload", t_add_data_from_link, "Import a file from a public link; the data agent cleans it into a table.", schema({"url": {"type": "string"}}, ["url"])),
    "create_report_now": ("reports.manage", t_create_report_now, "Start this week's report now.", schema()),
    "list_members": ("users", t_list_members, "List the workspace members, roles and data access.", schema()),
    "activity_log": ("users", t_activity_log, "Read the latest activity log entries.", schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200}})),
}


def tools_for(caller: Caller) -> list[str]:
    return [name for name, (perm, *_rest) in TOOLS.items() if perm is None or perm in caller.perms]


def caller_from(ctx) -> Caller | None:
    request = getattr(ctx, "request", None)
    return resolve(request.headers.get("authorization", "")) if request is not None else None


async def on_list_tools(ctx, params) -> types.ListToolsResult:
    caller = caller_from(ctx)
    names = tools_for(caller) if caller else []
    return types.ListToolsResult(tools=[types.Tool(name=n, description=TOOLS[n][2], input_schema=TOOLS[n][3]) for n in names],
                                 cache_scope="private", ttl_ms=0)


async def on_call_tool(ctx, params) -> types.CallToolResult:
    caller = caller_from(ctx)
    if caller is None:
        return error("Your MCP token is missing, revoked, or you are no longer a member of this workspace.")
    name, args = params.name, params.arguments or {}
    if name not in TOOLS:
        return error(f"Unknown tool {name!r}.")
    if name not in tools_for(caller):
        caller.tenant.audit(caller.user, "denied", permission=TOOLS[name][0], tool=name, via="mcp")
        return error(f"Your role ({caller.role}{', read-only token' if caller.access == 'read' else ''}) cannot use {name}.")
    if not allowed_rate(caller):
        return error("Too many calls. Wait a minute and try again.")
    touch(caller)
    try:
        result = await anyio.to_thread.run_sync(TOOLS[name][1], caller, args)
    except Exception:
        ref = secrets.token_hex(3)
        log.error("mcp tool failed ref=%s tool=%s tenant=%s", ref, name, caller.tenant.id, exc_info=True)
        return error(f"The tool failed on our side. Reference: {ref}")
    return result if isinstance(result, types.CallToolResult) else text(result)


server = Server("analyst-buddy", version="1.0", title="Analyst Buddy",
                instructions="Ask business questions about this workspace's data. Start with list_tables, then ask_analyst.",
                on_list_tools=on_list_tools, on_call_tool=on_call_tool)
mcp_app = server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                     transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


async def guarded(scope, receive, send):
    if scope["type"] == "http":
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if resolve(headers.get("authorization", "")) is None:
            base = srv.os.getenv("PUBLIC_URL", "").rstrip("/") or f"{scope.get('scheme', 'https')}://{headers.get('host', 'localhost')}"
            challenge = f'Bearer realm="analyst-buddy", resource_metadata="{base}/.well-known/oauth-protected-resource"'
            response = JSONResponse({"error": "invalid_token", "detail": "Sign in with OAuth, or send an Analyst Buddy token as: Authorization: Bearer ab_mcp_..."},
                                    status_code=401, headers={"WWW-Authenticate": challenge})
            await response(scope, receive, send)
            return
    await mcp_app(scope, receive, send)


class McpSlash:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


def attach(app, server_module):
    global srv
    srv = server_module
    app.mount("/mcp", guarded)
    app.add_middleware(McpSlash)


def close_sessions():
    for key in list(SESSIONS):
        s = SESSIONS.pop(key, None)
        try:
            s.sandbox.kill()
        except Exception:
            pass
