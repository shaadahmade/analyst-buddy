import json
import shutil
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import requests
import uvicorn

import connections
import mcp_auth
import mcp_oauth
import mcp_server
import reports
import server
import sources
import tenants
from tenants import TENANTS_DIR, Tenant

tid = "test-signin"
mcp_server.TOKENS_FILE = TENANTS_DIR / "test-signin-tokens.json"
mcp_oauth.CLIENTS_FILE = TENANTS_DIR / "test-signin-clients.json"
server.LOGINS_FILE = TENANTS_DIR / "test-signin-logins.json"
tenants.ACCOUNTS_FILE = TENANTS_DIR / "test-signin-accounts.json"
for f in (mcp_server.TOKENS_FILE, server.LOGINS_FILE, tenants.ACCOUNTS_FILE, mcp_oauth.CLIENTS_FILE):
    f.unlink(missing_ok=True)
(TENANTS_DIR / tid / "data").mkdir(parents=True, exist_ok=True)
(TENANTS_DIR / tid / "data" / "orders.csv").write_text("region,revenue\nNorth,10\nSouth,20\n")
(TENANTS_DIR / tid / "users.json").write_text(json.dumps({"boss@m.in": {"role": "owner", "scope": None},
                                                          "ana@m.in": {"role": "analyst", "scope": None}}))
for email in ("boss@m.in", "ana@m.in"):
    tenants.create_account(email, "member-password")
server.start_sandbox = lambda tenant, scope=None: (SimpleNamespace(kill=lambda: None, files=SimpleNamespace(write=lambda p, d: None), run_code=lambda c: None), ["orders.csv"], "overview")
server.preload = lambda sandbox, names, context=None: "overview"
server.build_agent = lambda *a, **k: "agent"
server.memory_index = lambda: None
reports.generate = lambda tenant, index: None
sources.ALLOW_PRIVATE_MCP = True

PORT = 8767
BASE = f"http://127.0.0.1:{PORT}"
uv = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=uv.run, daemon=True).start()
while not uv.started:
    time.sleep(0.05)

try:
    def login(email):
        r = requests.post(f"{BASE}/api/login", json={"email": email, "password": "member-password", "workspace": tid}, timeout=30)
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    boss, ana = login("boss@m.in"), login("ana@m.in")
    mcp = f"{BASE}/mcp"

    probe = requests.post(f"{BASE}/api/connections/mcp/inspect", json={"url": mcp}, headers=boss, timeout=30).json()
    assert probe == {"needs_signin": True, "message": "This MCP server needs you to sign in."}, probe

    start = requests.post(f"{BASE}/api/connections/mcp/signin", json={"url": mcp}, headers=boss, timeout=30).json()
    grant, auth = start["grant"], urlparse(start["url"])
    q = {k: v[0] for k, v in parse_qs(auth.query).items()}
    assert q["redirect_uri"] == BASE + mcp_auth.CALLBACK and q["code_challenge_method"] == "S256" and q["state"] == grant
    assert q["client_id"].startswith("abc_"), "our server has no client document support, so the client registers itself"
    assert requests.get(f"{BASE}/api/connections/mcp/signin/{grant}", headers=ana, timeout=10).status_code == 404, \
        "another member cannot see someone else's sign-in"

    consent = requests.get(start["url"], allow_redirects=False, timeout=10).headers["location"]
    rid = consent.split("mcp_consent=", 1)[1]
    back = requests.post(f"{BASE}/api/mcp/oauth/{rid}", json={"allow": True, "access": "read"}, headers=boss, timeout=10).json()["redirect"]
    page = requests.get(back, timeout=30)
    assert "Connected" in page.text, page.text
    assert requests.get(back, timeout=30).text.count("Not connected") == 1, "a callback works only once"
    assert "Not connected" in requests.get(f"{BASE}{mcp_auth.CALLBACK}?state=nope&code=x", timeout=10).text
    assert requests.get(f"{BASE}/api/connections/mcp/signin/{grant}", headers=boss, timeout=10).json()["status"] == "ready"

    r = requests.post(f"{BASE}/api/connections/mcp/inspect", json={"url": mcp, "grant": grant}, headers=ana, timeout=30)
    assert r.status_code == 400, "a grant only works for the member who signed in"
    found = requests.post(f"{BASE}/api/connections/mcp/inspect", json={"url": mcp, "grant": grant}, headers=boss, timeout=30).json()
    names = {t["name"] for t in found["tools"]}
    assert "list_tables" in names and "list_members" not in names and found["signin"] is True, found

    item = requests.post(f"{BASE}/api/connections", headers=boss, timeout=60, json={
        "kind": "mcp", "config": {"url": mcp, "tools": [{"name": "list_tables", "args": {}}]}, "secrets": {"grant": grant}}).json()
    assert item["syncing"], item
    for _ in range(100):
        state = next(i for i in connections.overview(Tenant(tid))["items"] if i["id"] == item["id"])
        if state["status"] in ("ok", "error"):
            break
        time.sleep(0.2)
    assert state["status"] == "ok" and state["rows"] >= 1, state
    assert requests.get(f"{BASE}/api/connections/mcp/signin/{grant}", headers=boss, timeout=10).status_code == 404, "a grant is used once"

    stored = next(i for i in connections._load(Tenant(tid))["items"] if i["id"] == item["id"])
    secret = connections.unseal(stored["secret"], Tenant(tid), item["id"])
    assert secret["refresh_token"] and secret["token_endpoint"].endswith("/oauth/token") and "grant" not in secret
    assert "ab_" not in json.dumps(stored), "keys are stored encrypted only"
    old = secret["token"]
    connections._update(Tenant(tid), item["id"], secret=connections.seal({**secret, "expires_at": 0}, Tenant(tid), item["id"]))
    assert connections.sync(Tenant(tid), item["id"])["status"] == "ok"
    renewed = connections.unseal(next(i for i in connections._load(Tenant(tid))["items"] if i["id"] == item["id"])["secret"], Tenant(tid), item["id"])
    assert renewed["token"] != old and renewed["expires_at"] > time.time(), "an expiring sign-in renews itself on sync"

    connections._update(Tenant(tid), item["id"], secret=connections.seal({**renewed, "expires_at": 0, "refresh_token": "bad"}, Tenant(tid), item["id"]))
    failed = connections.sync(Tenant(tid), item["id"])
    assert failed["status"] == "error" and "sign in again" in failed["message"], failed

    sources.ALLOW_PRIVATE_MCP = False
    r = requests.post(f"{BASE}/api/connections/mcp/signin", json={"url": mcp}, headers=boss, timeout=10)
    assert r.status_code == 400, "sign-in discovery obeys the same public-address rule"

    doc = requests.get(f"{BASE}{mcp_auth.CLIENT_DOC}", timeout=10).json()
    assert doc["client_id"] == BASE + mcp_auth.CLIENT_DOC and doc["redirect_uris"] == [BASE + mcp_auth.CALLBACK]
    assert doc["token_endpoint_auth_method"] == "none"
    assert mcp_auth.client_for({"cimd": True, "registration_endpoint": None}, "https://ab.example")[0] == "https://ab.example" + mcp_auth.CLIENT_DOC
    print("mcp sign-in checks passed")
finally:
    uv.should_exit = True
    shutil.rmtree(TENANTS_DIR / tid, ignore_errors=True)
    for f in (mcp_server.TOKENS_FILE, server.LOGINS_FILE, tenants.ACCOUNTS_FILE, mcp_oauth.CLIENTS_FILE):
        f.unlink(missing_ok=True)
