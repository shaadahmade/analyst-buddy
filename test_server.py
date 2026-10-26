import json
import os
import shutil
from types import SimpleNamespace

from fastapi.testclient import TestClient

import server
import tenants
from tenants import TENANTS_DIR, Tenant

tenants.ACCOUNTS_FILE = TENANTS_DIR / "test-accounts.json"
tenants.ACCOUNTS_FILE.unlink(missing_ok=True)
server.LOGINS_FILE = TENANTS_DIR / "test-logins.json"
server.LOGINS_FILE.unlink(missing_ok=True)
for tid in ("test-a", "test-b"):
    (TENANTS_DIR / tid / "data").mkdir(parents=True, exist_ok=True)
    (TENANTS_DIR / tid / "users.json").write_text(json.dumps({f"boss@{tid}.in": {"role": "owner", "scope": None}}))
    tenants.create_account(f"boss@{tid}.in", f"{tid}-password")
(TENANTS_DIR / "test-old" / "data").mkdir(parents=True, exist_ok=True)
Tenant("test-old").auth_file.write_text(json.dumps({"salt": "00" * 16, "hash": tenants._hash("old-password", b"\0" * 16).hex()}))
tenants.migrate_accounts([Tenant("test-old")])
assert tenants.check_account("owner", "old-password") == "owner", "the old company password did not carry over"
assert "hash" not in Tenant("test-old").users()["owner"]
made = []

killed, started, scopes = [], [], []
fail = {"exc": None, "start": False}


def fake_start(t, scope=None):
    if fail["start"]:
        raise RuntimeError("E2B down")
    started.append(t.id)
    scopes.append(scope)
    return SimpleNamespace(kill=lambda: killed.append(t.id), files=SimpleNamespace(write=lambda p, d: None)), [], "overview"


def fake_ask(agent, sandbox, memory, messages, q, on_step=None, should_stop=None, images=None, team=None):
    fail["images"] = images
    fail["team"] = team
    on_step({"type": "call", "id": "c1", "tool": "run_python", "args": {"code": "print(1)"}})
    on_step({"type": "output", "id": "c1", "output": "1"})
    if fail["exc"]:
        exc, fail["exc"] = fail["exc"], None
        raise exc
    if fail.get("stop_now"):
        token, fail["stop_now"] = fail["stop_now"], None
        server.SESSIONS[token].stop.set()
    if should_stop():
        raise server.Stopped()
    return messages + [q], f"{agent} answered: {q}", 2


server.start_sandbox = fake_start
server.build_agent = lambda sandbox, tenant, memory, data, chart_dir=None: tenant.id
server.preload = lambda sandbox, names: f"overview with {names}"
server.memory_index = lambda: None
server.ask = fake_ask
os.environ.pop("GOOGLE_CLIENT_ID", None)
GOOGLE = {"good-new": {"email": "Gina@gmail.com", "email_verified": True},
          "unverified": {"email": "x@gmail.com", "email_verified": False},
          "boss-a": {"email": "boss@test-a.in", "email_verified": True},
          "invited": {"email": "guest@gmail.com", "email_verified": True}}


def fake_verify(credential, request, client_id, **kw):
    assert client_id == "test-client-id", client_id
    if credential not in GOOGLE:
        raise ValueError("bad token")
    return GOOGLE[credential]


server.google_id_token = SimpleNamespace(verify_oauth2_token=fake_verify)

server.LOGIN_LIMIT = server.SIGNUP_LIMIT = (1000, 600)
try:
    client = TestClient(server.app, raise_server_exceptions=False)

    def login(tenant, email, password):
        return client.post("/api/login", json={"workspace": tenant, "email": email, "password": password})

    assert login("test-a", "boss@test-a.in", "wrong").status_code == 401
    assert login("test-a", "nobody@test-a.in", "test-a-password").status_code == 401
    assert login("test-a", "boss@test-b.in", "test-b-password").json()["tenant"] == "test-b", "opened a workspace they are not in"
    assert login("../test-a", "boss@test-a.in", "test-a-password").json()["tenant"] == "test-a"

    r = client.post("/api/signup", json={"workspace": "Shop & Co", "email": "new@shop.in", "password": "shop-password"})
    assert r.status_code == 200, r.text
    made.append(r.json()["tenant"])
    assert r.json()["tenant"].startswith("shop-co-") and r.json()["workspace"] == "Shop & Co" and r.json()["role"] == "owner"
    assert client.post("/api/signup", json={"workspace": "Again", "email": "new@shop.in", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/signup", json={"workspace": "X", "email": "x@shop.in", "password": "short"}).status_code == 400
    assert client.post("/api/signup", json={"workspace": " ", "email": "y@shop.in", "password": "long-enough"}).status_code == 400
    assert not tenants.account_exists("y@shop.in"), "a failed sign-up left an account behind"
    second = client.post("/api/signup", json={"workspace": "Shop Two", "email": "new@shop.in", "password": "shop-password"}).json()
    made.append(second["tenant"])
    assert sorted(w["name"] for w in second["workspaces"]) == ["Shop & Co", "Shop Two"]
    assert login(None, "new@shop.in", "shop-password").json()["tenant"] == second["tenant"], "login must reopen the last workspace"
    hs = {"Authorization": f"Bearer {second['token']}"}
    switched = client.post(f"/api/workspaces/{made[0]}/open", headers=hs).json()
    assert switched["tenant"] == made[0] and client.get("/api/me", headers=hs).status_code == 401, "switching must end the old session"
    hs = {"Authorization": f"Bearer {switched['token']}"}
    assert client.post("/api/workspaces/test-a/open", headers=hs).status_code == 403, "switched into a workspace they are not in"
    third = client.post("/api/workspaces", json={"name": "Side project"}, headers=hs).json()
    made.append(third["tenant"])
    assert third["role"] == "owner" and len(third["workspaces"]) == 3

    a = login("test-a", "Boss@test-a.in ", "test-a-password").json()
    b = login("test-b", "boss@test-b.in", "test-b-password").json()
    assert a["role"] == "owner" and "users" in a["permissions"] and a["user"] == "boss@test-a.in"
    ha, hb = {"Authorization": f"Bearer {a['token']}"}, {"Authorization": f"Bearer {b['token']}"}

    def ask_events(headers, q="hi"):
        r = client.post("/api/ask", json={"question": q}, headers=headers)
        assert r.status_code == 200, r.text
        return [json.loads(line) for line in r.text.splitlines()]

    assert client.get("/api/me").status_code == 401
    assert client.post("/api/ask", json={"question": "hi"}, headers={"Authorization": "Bearer forged"}).status_code == 401
    events = ask_events(ha)
    assert [e["type"] for e in events] == ["call", "output", "done"], events
    assert events[-1]["answer"] == "test-a answered: hi"
    assert ask_events(hb)[-1]["answer"] == "test-b answered: hi"
    r = client.post("/api/ask", json={"question": "why?", "context": "North | 3381"}, headers=ha)
    assert "circled" in r.text and "North | 3381" in r.text, r.text
    shot = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    r = client.post("/api/ask", json={"question": "what is this?", "images": [shot, shot, shot]}, headers=ha)
    assert r.status_code == 200 and fail["images"] == [shot] * 3 and "3 attached image(s)" in r.text, r.text
    assert ask_events(ha)[-1]["type"] == "done" and fail["images"] == [], "a plain question must not carry images"
    assert fail["team"] is not None and fail["team"].tenant.id == "test-a", "questions go to the team by default"
    client.post("/api/ask", json={"question": "quick", "mode": "single"}, headers=ha)
    assert fail["team"] is None, "mode=single must skip the team"
    assert client.post("/api/ask", json={"question": "x", "mode": "swarm"}, headers=ha).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "images": [shot] * 6}, headers=ha).status_code == 400, "allowed 6 circles"
    assert client.post("/api/ask", json={"question": "x", "images": [shot] * 5}, headers=ha).status_code == 200
    big = "data:image/png;base64," + "A" * (server.MAX_IMAGE // 2)
    for bad in [["data:text/html;base64,PGgxPg=="], ["https://evil.example/x.png"], ["data:image/png;base64,not base64!"],
                [shot, "data:image/png;base64," + "A" * server.MAX_IMAGE], [big, big]]:
        assert client.post("/api/ask", json={"question": "x", "images": bad}, headers=ha).status_code == 400, bad[-1][:40]
    assert client.post("/api/ask", json={"question": "hi", "context": "x" * 9000}, headers=ha).status_code == 400
    assert client.post("/api/ask", json={"question": "  "}, headers=ha).status_code == 400

    from e2b.exceptions import SandboxNotFoundException
    from langchain_google_genai.chat_models import GoogleInvalidRequestError, GoogleRateLimitError

    def ask_failing(exc):
        fail["exc"] = exc
        return ask_events(ha)[-1]

    import httpx
    from openai import APIConnectionError
    assert server.friendly(APIConnectionError(request=httpx.Request("POST", "https://api.deepseek.com"))) == server.BUSY
    e = ask_failing(GoogleRateLimitError("429 quota"))
    assert e == {"type": "error", "message": server.BUSY, "retry": True}, e
    e = ask_failing(GoogleInvalidRequestError("API key not valid"))
    assert e["type"] == "error" and e["message"] == server.UNAVAILABLE, e
    starts = started.count("test-a")
    e = ask_failing(SandboxNotFoundException("sandbox gone"))
    assert e["type"] == "error" and e["message"] == server.RESTARTED, e
    assert started.count("test-a") == starts + 1, "sandbox was not restarted"
    e = ask_failing(ValueError("boom"))
    assert e["type"] == "error" and "Reference:" in e["message"] and "boom" not in str(e) and not e["retry"], e
    assert ask_events(ha)[-1]["type"] == "done", "lock not released"

    before = list(server.SESSIONS[a["token"]].messages)
    fail["stop_now"] = a["token"]
    assert ask_events(ha)[-1] == {"type": "stopped"}
    assert server.SESSIONS[a["token"]].messages == before, "a stopped question must not be added to the history"
    assert client.post("/api/ask/stop", headers=ha).json() == {"ok": True}
    assert ask_events(ha)[-1]["type"] == "done", "a Stop pressed between questions must not stop the next one"
    assert client.post("/api/ask/stop").status_code == 401

    fb = {"question": "Why did revenue drop?", "answer": "Revenue fell 12%", "rating": "down", "note": "Ignore refunds"}
    r = client.post("/api/feedback", json=fb, headers=ha)
    assert r.status_code == 200 and r.json() == {"ok": True, "remembered": False, "traced": False}, r.text
    saved = []
    server.SESSIONS[a["token"]].memory = SimpleNamespace(remember=lambda text, kind: saved.append((kind, text)))
    assert client.post("/api/feedback", json=fb, headers=ha).json()["remembered"] is True
    assert saved[0][0] == "correction" and "Ignore refunds" in saved[0][1]
    client.post("/api/feedback", json={**fb, "rating": "up", "note": ""}, headers=ha)
    assert saved[1][0] == "liked"
    assert client.post("/api/feedback", json={**fb, "rating": "meh"}, headers=ha).status_code == 422
    log_lines = (TENANTS_DIR / "test-a" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log_lines) == 3 and not (TENANTS_DIR / "test-b" / "feedback.jsonl").exists()

    r = client.post("/api/upload", files={"file": ("../../test-b/data/evil.csv", b"a,b\n1,2")}, headers=ha)
    assert r.status_code == 200 and "evil.csv" in r.json()["files"], r.text
    assert (TENANTS_DIR / "test-a" / "data" / "evil.csv").exists()
    assert not (TENANTS_DIR / "test-b" / "data" / "evil.csv").exists()
    assert client.post("/api/upload", files={"file": ("run.py", b"x")}, headers=ha).status_code == 400
    assert client.post("/api/upload", files={"file": (".env.csv", b"x")}, headers=ha).status_code == 400
    for broken in [("sales.xlsx", b"not a zip"), ("sales.json", b"{bad"), ("sales.csv", b"   "), ("sales.csv", b"a\x00b")]:
        r = client.post("/api/upload", files={"file": broken}, headers=ha)
        assert r.status_code == 400 and "could not read" in r.json()["detail"], (broken, r.text)
    assert client.post("/api/upload", files={"file": ("ok.xlsx", b"PK\x03\x04rest")}, headers=ha).status_code == 200
    assert "ok.xlsx" in server.SESSIONS[a["token"]].data["overview"], "upload did not refresh the data overview"

    def fake_import(kind, details, keys, on_step, on_table, chart_dir):
        on_step({"type": "call", "id": "d1", "tool": "run_python", "args": {"code": "pull()"}})
        assert on_table("Sales Orders!", b"x" * (server.MAX_UPLOAD + 1)).startswith("not saved")
        assert on_table("../Sales Orders!", b"date,amount\n2026-10-01,12.5\n").startswith("saved as sales_orders.csv")
        return f"charges: 1 row ({kind}, keys {sorted(keys)})"

    server.run_import = fake_import

    def connect(body, headers=ha):
        r = client.post("/api/sources", json=body, headers=headers)
        return r.status_code, [json.loads(line) for line in r.text.splitlines()] if r.status_code == 200 else r.text

    assert connect({"kind": "ftp"})[0] == 400
    assert connect({"kind": "database"})[0] == 400, "a connection URL is required"
    assert connect({"kind": "database", "secrets": {"DATABASE_URL": "pg://x", "AWS_KEY": "x"}})[0] == 400, "unknown secret names are refused"
    assert connect({"kind": "url"})[0] == 400, "a link is required"
    assert connect({"kind": "shopify", "secrets": {"SHOPIFY_TOKEN": "x"}})[0] == 400, "apps use saved connections, not the data agent"
    for blocked in [{"kind": "other", "details": "pull my Stripe payouts"}, {"kind": "url", "details": "https://api.razorpay.com/v1/payments"},
                    {"kind": "other", "details": "my payments API", "secrets": {"SOURCE_SECRET": "sk_live_abc"}},
                    {"kind": "other", "details": "payments", "secrets": {"SOURCE_SECRET": "rzp_live_abc"}}]:
        code, detail = connect(blocked)
        assert code == 400 and "not supported" in detail, (blocked, detail)
    assert connect({"kind": "connection", "details": "x"})[0] == 400
    code, events = connect({"kind": "database", "secrets": {"DATABASE_URL": "postgresql://reader:pw_123@db/shop"}})
    assert code == 200 and [e["type"] for e in events] == ["call", "table", "done"], events
    done = events[-1]
    assert done["tables"] == ["sales_orders.csv"] and "sales_orders.csv" in done["session"]["files"]
    assert "pw_123" not in json.dumps(events) and "DATABASE_URL" in done["note"]
    assert (TENANTS_DIR / "test-a" / "data" / "sales_orders.csv").read_bytes().startswith(b"date,amount")
    notes = Tenant("test-a").knowledge()["data_notes"]
    assert notes[-1]["tables"] == ["sales_orders.csv"] and notes[-1]["source"] == "database"
    assert "pw_123" not in (TENANTS_DIR / "test-a" / "audit.jsonl").read_text(), "a secret reached the audit log"
    code, events = connect({"kind": "other", "details": "the public API at api.example.com/sales"})
    assert code == 200 and events[-1]["type"] == "done", "other sources may skip the secret"
    assert len(Tenant("test-a").knowledge()["data_notes"]) == 1, "re-connecting the same table replaces its note"

    r = client.put("/api/goals", json={"goals": ["Grow repeat orders 10%", "grow  repeat orders 10%", "  Cut refunds  "]}, headers=ha)
    assert r.status_code == 200 and r.json()["knowledge"]["goals"] == ["Grow repeat orders 10%", "Cut refunds"], r.text
    assert client.put("/api/goals", json={"goals": ["x"] * 0 + [str(i) for i in range(21)]}, headers=ha).status_code == 400
    assert client.put("/api/goals", json={"goals": [""]}, headers=ha).status_code == 400
    assert client.put("/api/goals", json={"goals": ["y" * 201]}, headers=ha).status_code == 400
    assert any(e["action"] == "goals changed" for e in Tenant("test-a").audit_log())

    assert client.delete("/api/data/sales_orders.csv", headers=ha).json()["files"].count("sales_orders.csv") == 0
    assert not (TENANTS_DIR / "test-a" / "data" / "sales_orders.csv").exists()
    assert Tenant("test-a").knowledge()["data_notes"] == [], "a deleted table's note must go too"
    assert client.delete("/api/data/sales_orders.csv", headers=ha).status_code == 404
    assert client.delete("/api/data/..%2Fusers.json", headers=ha).status_code in (404, 405)
    assert (TENANTS_DIR / "test-a" / "users.json").exists(), "deleting must never reach outside the data folder"
    assert any(e["action"] == "data deleted" for e in Tenant("test-a").audit_log())

    import connections
    import sources
    connections.KEY_FILE = TENANTS_DIR / "test-a" / "conn.key"
    connections._keys = None
    synced = []
    sources.CONNECTORS["shopify"]["test"] = lambda cfg, sec, http: "Haad Store (INR)" if sec["client_secret"] == "good" else (_ for _ in ()).throw(server.SourceError("Shopify refused the request (401)."))
    server.start_sync = lambda t, cid: synced.append(cid)
    rz = {"kind": "shopify", "config": {"shop": "haad.myshopify.com"}, "secrets": {"client_id": "c1", "client_secret": "bad"}}
    r = client.post("/api/connections", json=rz, headers=ha)
    assert r.status_code == 400 and "refused" in r.json()["detail"], r.text
    r = client.post("/api/connections", json={**rz, "secrets": {"client_id": "c1", "client_secret": "good"}}, headers=ha)
    conn = r.json()
    assert r.status_code == 200 and conn["label"] == "Haad Store (INR)" and conn["config"] == {"shop": "haad.myshopify.com"} and "secret" not in conn and synced == [conn["id"]], r.text
    listing = client.get("/api/connections", headers=ha).json()
    assert [i["id"] for i in listing["items"]] == [conn["id"]] and "good" not in json.dumps(listing)
    assert client.post(f"/api/connections/{conn['id']}/sync", headers=ha).status_code == 202 and synced[-1] == conn["id"]
    assert client.post("/api/connections/nope/sync", headers=ha).status_code == 404
    assert client.post("/api/connections", json={"kind": "ftp"}, headers=ha).status_code == 400

    os.environ["GOOGLE_CLIENT_ID"], os.environ["GOOGLE_CLIENT_SECRET"] = "cid", "csecret"
    start = client.get("/api/connections/google/start", headers=ha).json()["url"]
    assert "accounts.google.com" in start and "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Foauth%2Fgoogle%2Fcallback" in start
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(start).query)["state"][0]
    server.connections.google_exchange = lambda code, redirect: ("me@gmail.com", "refresh-1")
    r = client.get(f"/api/oauth/google/callback?state={state}&code=abc", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?google=connected", r.headers
    assert client.get("/api/connections", headers=ha).json()["google"]["email"] == "me@gmail.com"
    r = client.get(f"/api/oauth/google/callback?state={state[:-3]}xyz&code=abc", follow_redirects=False)
    assert r.headers["location"] == "/?google=failed", "a tampered state must be refused"
    r = client.get(f"/api/oauth/google/callback?state={state}&error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/?google=failed"
    assert client.delete("/api/connections/google", headers=ha).json() == {"ok": True}
    assert client.get("/api/connections", headers=ha).json()["google"] is None
    os.environ.pop("GOOGLE_CLIENT_SECRET")
    assert client.get("/api/connections/google/start", headers=ha).status_code == 400
    os.environ.pop("GOOGLE_CLIENT_ID")
    assert client.delete(f"/api/connections/{conn['id']}", headers=ha).json() == {"ok": True}
    assert client.delete(f"/api/connections/{conn['id']}", headers=ha).status_code == 404

    def add(email, role, scope=None, headers=ha):
        return client.post("/api/users", json={"email": email, "role": role, "scope": scope,
                                               "password": "member-password"}, headers=headers)

    assert add("ad@test-a.in", "admin").status_code == 200
    assert add("an@test-a.in", "analyst").status_code == 200
    assert add("vi@test-a.in", "viewer").status_code == 200
    north = {"orders.csv": {"rows": {"region": ["North"]}, "hide": ["customer_id"]}}
    assert add("rep@test-a.in", "analyst", north).status_code == 200
    assert add("vi@test-a.in", "viewer").status_code == 400, "added the same member twice"
    assert add("x@test-a.in", "admin", north).status_code == 400, "an admin cannot have a data scope"
    assert add("x@test-a.in", "superuser").status_code == 422
    assert client.post("/api/users", json={"email": "nopw@test-a.in", "role": "viewer"}, headers=ha).status_code == 400
    assert not tenants.account_exists("nopw@test-a.in") and "nopw@test-a.in" not in Tenant("test-a").users()
    joined = client.post("/api/users", json={"email": "boss@test-b.in", "role": "analyst"}, headers=ha).json()
    assert joined["joins"] == "existing", "an existing account must join without a new password"
    assert {w["id"] for w in tenants.workspaces_of("boss@test-b.in")} == {"test-a", "test-b"}
    assert add("y@test-a.in", "viewer", headers=hb).status_code == 200
    assert "y@test-a.in" not in Tenant("test-a").users(), "an owner added a member to another company"

    tok = {e: login("test-a", e, "member-password").json() for e in ["ad@test-a.in", "an@test-a.in", "vi@test-a.in", "rep@test-a.in"]}
    hdr = {e: {"Authorization": f"Bearer {t['token']}"} for e, t in tok.items()}
    assert scopes[-1] == north, "the scoped sandbox did not get the scope"
    assert tok["rep@test-a.in"]["scoped"] and tok["rep@test-a.in"]["permissions"] == []
    assert tok["vi@test-a.in"]["permissions"] == ["reports"]

    csv = {"file": ("x.csv", b"a,b\n1,2")}
    matrix = [
        ("post", "/api/upload", {"files": csv}, {"ad": 200, "an": 200, "vi": 403, "rep": 403}),
        ("get", "/api/reports", {}, {"ad": 200, "an": 200, "vi": 200, "rep": 403}),
        ("put", "/api/reports/settings", {"json": {}}, {"ad": 200, "an": 403, "vi": 403, "rep": 403}),
        ("post", "/api/reports/run", {}, {"ad": 403, "an": 403, "vi": 403, "rep": 403}),
        ("get", "/api/users", {}, {"ad": 200, "an": 403, "vi": 403, "rep": 403}),
        ("post", "/api/sources", {"json": {"kind": "ftp"}}, {"ad": 400, "an": 400, "vi": 403, "rep": 403}),
        ("get", "/api/connections", {}, {"ad": 200, "an": 200, "vi": 403, "rep": 403}),
        ("put", "/api/goals", {"json": {"goals": ["Keep churn under 3%"]}}, {"ad": 200, "an": 200, "vi": 403, "rep": 403}),
        ("delete", "/api/data/missing.csv", {}, {"ad": 404, "an": 404, "vi": 403, "rep": 403}),
        ("post", "/api/connections", {"json": {"kind": "ftp"}}, {"ad": 400, "an": 400, "vi": 403, "rep": 403}),
    ]
    server.reports._running.add("test-a")
    for method, path, kwargs, expected in matrix:
        for who, code in expected.items():
            if path == "/api/reports/run" and who == "ad":
                continue
            got = getattr(client, method)(path, headers=hdr[f"{who}@test-a.in"], **kwargs).status_code
            assert got == code, f"{who} {method} {path}: {got}, expected {code}"
    assert client.post("/api/reports/run", headers=hdr["ad@test-a.in"]).status_code == 409, "admin passes the role check"
    server.reports._running.discard("test-a")
    for who in hdr:
        assert ask_events(hdr[who])[-1]["type"] == "done", f"{who} could not ask"

    assert add("own2@test-a.in", "owner", headers=hdr["ad@test-a.in"]).status_code == 403, "an admin created an owner"
    assert client.delete("/api/users/boss@test-a.in", headers=hdr["ad@test-a.in"]).status_code == 403
    assert client.delete("/api/users/boss@test-a.in", headers=ha).status_code == 400, "an owner removed themselves"
    assert client.put("/api/users/boss@test-a.in", json={"email": "boss@test-a.in", "role": "viewer"},
                      headers=ha).status_code == 400
    assert client.delete("/api/users/ghost@test-a.in", headers=ha).status_code == 404

    r = client.put("/api/users/an@test-a.in", json={"email": "an@test-a.in", "role": "viewer"}, headers=hdr["ad@test-a.in"])
    assert r.json()["role"] == "viewer"
    assert client.get("/api/me", headers=hdr["an@test-a.in"]).status_code == 401, "a role change must sign the member out"
    assert login("test-a", "an@test-a.in", "member-password").json()["role"] == "viewer"
    assert client.delete("/api/users/vi@test-a.in", headers=ha).json() == {"ok": True}
    assert client.get("/api/me", headers=hdr["vi@test-a.in"]).status_code == 401, "a removed member kept their session"
    assert login("test-a", "vi@test-a.in", "member-password").status_code == 403

    audit = client.get("/api/users", headers=ha).json()["audit"]
    actions = {(e["user"], e["action"]) for e in audit}
    for expected in [("boss@test-a.in", "member removed"), ("ad@test-a.in", "member changed"), ("vi@test-a.in", "denied"),
                     ("rep@test-a.in", "ask"), ("ad@test-a.in", "upload")]:
        assert expected in actions, f"missing audit entry {expected}"
    assert "rep@test-a.in" not in (TENANTS_DIR / "test-b" / "audit.jsonl").read_text(), "audit leaked across companies"

    assert b["token"] not in server.LOGINS_FILE.read_text(), "only a fingerprint of the token may be saved"
    starts = started.count("test-b")
    server.SESSIONS[b["token"]].last_used -= server.SANDBOX_IDLE + 1
    assert client.get("/api/me", headers=hb).status_code == 200, "an idle sandbox must not sign the person out"
    assert "test-b" in killed and started.count("test-b") == starts + 1, "the idle sandbox is closed and a fresh one started"
    server.SESSIONS.clear()
    me = client.get("/api/me", headers=hb)
    assert me.status_code == 200 and me.json()["user"] == "boss@test-b.in", "a server restart must not sign people out"
    assert started.count("test-b") == starts + 2
    assert client.get("/api/me", headers={"Authorization": "Bearer made-up-token"}).status_code == 401
    import json as _json
    saved = _json.loads(server.LOGINS_FILE.read_text())
    saved[server.token_key(b["token"])]["exp"] = 1
    server.LOGINS_FILE.write_text(_json.dumps(saved))
    server.SESSIONS.clear()
    assert client.get("/api/me", headers=hb).status_code == 401, "a sign-in older than 7 days must expire"
    b = login("test-b", "boss@test-b.in", "test-b-password").json()
    hb = {"Authorization": f"Bearer {b['token']}"}
    assert client.delete("/api/session", headers=ha).json() == {"ok": True} and "test-a" in killed
    assert client.get("/api/me", headers=ha).status_code == 401, "signing out must forget the saved sign-in"
    server.SESSIONS.clear()
    assert client.get("/api/me", headers=ha).status_code == 401, "a signed-out token must not revive after a restart"

    def google(credential, workspace=""):
        return client.post("/api/auth/google", json={"credential": credential, "workspace": workspace})

    assert client.get("/api/config").json() == {"google_client_id": None}
    assert google("good-new").status_code == 404, "Google sign-in must be off without a client id"
    os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
    assert client.get("/api/config").json() == {"google_client_id": "test-client-id"}
    assert google("forged").status_code == 401
    assert google("unverified").status_code == 401
    assert google("good-new").json() == {"needs_workspace": True, "email": "gina@gmail.com"}
    assert not tenants.account_exists("gina@gmail.com"), "an account was made before a workspace was named"
    g = google("good-new", "Gina's Shop").json()
    made.append(g["tenant"])
    assert g["role"] == "owner" and g["user"] == "gina@gmail.com"
    assert google("good-new").json()["tenant"] == g["tenant"], "a returning Google user must land in their workspace"
    assert login(None, "gina@gmail.com", "").status_code == 401, "a Google-only account has no password to guess"
    assert login(None, "gina@gmail.com", "anything-at-all").status_code == 401
    boss = google("boss-a").json()
    assert boss["tenant"] == "test-a", "Google must open an existing password account"
    assert login("test-a", "boss@test-a.in", "test-a-password").status_code == 200, "Google broke the password"
    r = client.post("/api/users", json={"email": "guest@gmail.com", "role": "viewer"},
                    headers={"Authorization": f"Bearer {boss['token']}"})
    assert r.json()["joins"] == "google", r.text
    joined = google("invited").json()
    assert joined["tenant"] == "test-a" and joined["role"] == "viewer"
    os.environ.pop("GOOGLE_CLIENT_ID")

    server._hits.clear()
    server.LOGIN_LIMIT = (3, 600)
    codes = [login("test-a", "boss@test-a.in", "wrong").status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429], codes
    server._hits.clear()
    server.LOGIN_LIMIT = (1000, 600)

    fail["start"] = True
    r = login("test-a", "boss@test-a.in", "test-a-password")
    assert r.status_code == 503 and r.json()["detail"] == server.NO_START, r.text
    fail["start"] = False
finally:
    for tid in ("test-a", "test-b", "test-old", *made):
        shutil.rmtree(TENANTS_DIR / tid, ignore_errors=True)
    tenants.ACCOUNTS_FILE.unlink(missing_ok=True)
    server.LOGINS_FILE.unlink(missing_ok=True)

print("all server checks passed")
