import json
import shutil
from types import SimpleNamespace

from fastapi.testclient import TestClient

import mcp_oauth
import mcp_server
import reports
import server
import tenants
from tenants import TENANTS_DIR, Tenant

tid = "test-mcp"
mcp_server.TOKENS_FILE = TENANTS_DIR / "test-mcp-tokens.json"
mcp_oauth.CLIENTS_FILE = TENANTS_DIR / "test-mcp-clients.json"
server.LOGINS_FILE = TENANTS_DIR / "test-mcp-logins.json"
tenants.ACCOUNTS_FILE = TENANTS_DIR / "test-mcp-accounts.json"
for f in (mcp_server.TOKENS_FILE, server.LOGINS_FILE, tenants.ACCOUNTS_FILE, mcp_oauth.CLIENTS_FILE):
    f.unlink(missing_ok=True)
(TENANTS_DIR / tid / "data").mkdir(parents=True, exist_ok=True)
(TENANTS_DIR / tid / "data" / "orders.csv").write_text("region,revenue,customer_id\nNorth,10,c1\nSouth,20,c2\nNorth,30,c3\n")
(TENANTS_DIR / tid / "data" / "salaries.csv").write_text("name,salary\nA,100\n")
north = {"orders.csv": {"rows": {"region": ["North"]}, "hide": ["customer_id"]}}
(TENANTS_DIR / tid / "users.json").write_text(json.dumps({
    "boss@m.in": {"role": "owner", "scope": None}, "ad@m.in": {"role": "admin", "scope": None},
    "ana@m.in": {"role": "analyst", "scope": None}, "vi@m.in": {"role": "viewer", "scope": None},
    "rep@m.in": {"role": "analyst", "scope": north}}))
for email in ("boss@m.in", "vi@m.in", "ad@m.in"):
    tenants.create_account(email, "member-password")
t = Tenant(tid)

scopes, asked, written = [], [], []
server.start_sandbox = lambda tenant, scope=None: (scopes.append(scope) or SimpleNamespace(
    kill=lambda: None, files=SimpleNamespace(write=lambda p, d: written.append(p))), ["orders.csv"], "overview")
server.build_agent = lambda *a, **k: "agent"
server.memory_index = lambda: None
server.preload = lambda sandbox, names, context=None: f"overview {names}"


def fake_ask(agent, sandbox, memory, messages, q, on_step=None, should_stop=None, images=None, team=None):
    asked.append((q, team is not None))
    on_step({"type": "stage", "id": "s1", "agent": "Verifier", "text": "✓ North revenue 40 → 40"})
    on_step({"type": "call", "id": "c1", "agent": "Analyst 1", "tool": "run_python", "args": {"code": "1"}})
    return messages + [q], "North made 40 ✓", 7


mcp_server.ask = fake_ask
mcp_server.run_import = lambda kind, details, keys, on_step, on_table, charts: (on_table("Link Data", b"a,b\n1,2\n"), "1 row")[1]
reports.generate = lambda tenant, index: None
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
ALL = {"list_tables", "describe_table", "ask_analyst", "list_reports", "get_report", "list_connections", "sync_connection",
       "add_data_from_link", "create_report_now", "list_members", "activity_log"}

try:
    with TestClient(server.app) as c:
        def rpc(token, method, params=None):
            r = c.post("/mcp", headers={**ACCEPT, "Authorization": f"Bearer {token}"},
                       json={"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params else {})})
            return r.status_code, (r.json() if r.status_code == 200 else r.text)

        def tools(token):
            return {x["name"] for x in rpc(token, "tools/list")[1]["result"]["tools"]}

        def call(token, tool, **args):
            res = rpc(token, "tools/call", {"name": tool, "arguments": args})[1]["result"]
            body = res["content"][0]["text"]
            return res.get("isError", False), (json.loads(body) if body[:1] in "[{" else body)

        tok = {}
        for user, access in [("boss@m.in", "full"), ("ad@m.in", "full"), ("ana@m.in", "full"), ("vi@m.in", "full"),
                             ("rep@m.in", "full"), ("boss@m.in", "read")]:
            tok[(user, access)] = mcp_server.create_token(t, user, f"{user} {access}", access)[0]
        assert "ab_mcp_" not in mcp_server.TOKENS_FILE.read_text(), "tokens must be stored as fingerprints only"

        assert tools(tok[("boss@m.in", "full")]) == ALL
        assert tools(tok[("ad@m.in", "full")]) == ALL
        assert tools(tok[("ana@m.in", "full")]) == ALL - {"create_report_now", "list_members", "activity_log"}
        viewer_tools = {"list_tables", "describe_table", "ask_analyst", "list_reports", "get_report"}
        assert tools(tok[("vi@m.in", "full")]) == viewer_tools, "a full token can never exceed the member's role"
        assert tools(tok[("boss@m.in", "read")]) == viewer_tools, "a read-only token narrows even an owner"
        assert tools(tok[("rep@m.in", "full")]) == {"list_tables", "describe_table", "ask_analyst"}, "limited members see no reports or uploads"

        bad, msg = call(tok[("vi@m.in", "full")], "list_members")
        assert bad and "cannot use list_members" in msg, "a hidden tool must be refused on call, not just hidden"
        bad, msg = call(tok[("ana@m.in", "full")], "activity_log")
        assert bad and "analyst" in msg
        bad, msg = call(tok[("boss@m.in", "read")], "add_data_from_link", url="https://x.io/a.csv")
        assert bad and "read-only token" in msg
        assert call(tok[("boss@m.in", "full")], "no_such_tool")[0]
        denied = [e for e in t.audit_log() if e["action"] == "denied" and e.get("via") == "mcp"]
        assert {e["user"] for e in denied} >= {"vi@m.in", "ana@m.in", "boss@m.in"}

        assert call(tok[("rep@m.in", "full")], "list_tables")[1]["tables"] == ["orders.csv"], "limited member saw a file outside their scope"
        bad, desc = call(tok[("rep@m.in", "full")], "describe_table", name="orders.csv")
        assert not bad and desc["rows"] == 2 and "customer_id" not in desc["columns"] and {r["region"] for r in desc["sample"]} == {"North"}, desc
        assert call(tok[("rep@m.in", "full")], "describe_table", name="salaries.csv")[0]
        assert call(tok[("boss@m.in", "full")], "describe_table", name="salaries.csv")[1]["rows"] == 1

        bad, out = call(tok[("rep@m.in", "full")], "ask_analyst", question="How is North doing?")
        assert not bad and out["answer"] == "North made 40 ✓" and out["verified_checks"] == ["✓ North revenue 40 → 40"] and out["code_runs"] == 1, out
        assert scopes[-1] == north, "ask_analyst must run in the member's own limited sandbox"
        call(tok[("rep@m.in", "full")], "ask_analyst", question="again", team=False)
        assert asked[-1] == ("again", False) and scopes.count(north) == 1, "the sandbox is reused between calls"
        assert any(e["action"] == "ask" and e.get("via") == "mcp" and e["user"] == "rep@m.in" for e in t.audit_log())

        bad, added = call(tok[("ana@m.in", "full")], "add_data_from_link", url="https://x.io/data.csv")
        assert not bad and added["tables"] == ["link_data.csv"] and (t.data_dir / "link_data.csv").exists()
        assert call(tok[("ana@m.in", "full")], "add_data_from_link", url="https://api.stripe.com/v1/charges")[0]
        assert "Started" in call(tok[("ad@m.in", "full")], "create_report_now")[1]
        assert len(call(tok[("boss@m.in", "full")], "list_members")[1]) == 5

        t.save_user("ana@m.in", "viewer")
        assert tools(tok[("ana@m.in", "full")]) == viewer_tools, "a role change must apply to tokens immediately"
        t.remove_user("vi@m.in")
        assert rpc(tok[("vi@m.in", "full")], "tools/list")[0] == 401, "a removed member's token must stop working"
        assert c.post("/mcp", headers=ACCEPT, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
        assert rpc("ab_mcp_forged", "tools/list")[0] == 401

        old = mcp_server.CALL_LIMIT
        mcp_server.CALL_LIMIT = (2, 60)
        mcp_server._calls.clear()
        results = [call(tok[("boss@m.in", "full")], "list_tables")[0] for _ in range(3)]
        assert results == [False, False, True], results
        mcp_server.CALL_LIMIT = old

        def login(email):
            r = c.post("/api/login", json={"email": email, "password": "member-password", "workspace": tid})
            return {"Authorization": f"Bearer {r.json()['token']}"}

        hb, hd = login("boss@m.in"), login("ad@m.in")
        made = c.post("/api/mcp/tokens", json={"name": "Claude Desktop", "access": "read"}, headers=hd).json()
        assert made["token"].startswith("ab_mcp_") and made["access"] == "read" and made["u"] == "ad@m.in"
        assert tools(made["token"]) == viewer_tools
        assert c.post("/api/mcp/tokens", json={"name": "x", "access": "root"}, headers=hd).status_code == 422
        listing = c.get("/api/mcp/tokens", headers=hb).json()
        assert listing["url"].endswith("/mcp") and listing["can_manage_all"] and len(listing["tokens"]) == 7
        assert "ab_mcp_" not in json.dumps(listing), "listing must never return token values"
        assert c.delete(f"/api/mcp/tokens/{made['id']}", headers=hb).json() == {"ok": True}, "an owner can revoke anyone's token"
        assert rpc(made["token"], "tools/list")[0] == 401, "a revoked token must stop working at once"
        assert c.delete(f"/api/mcp/tokens/{made['id']}", headers=hb).status_code == 404

        import base64
        import hashlib
        from urllib.parse import parse_qs, urlparse
        res_meta = c.get("/.well-known/oauth-protected-resource").json()
        assert res_meta["resource"].endswith("/mcp") and res_meta["authorization_servers"] == ["http://testserver"]
        meta = c.get("/.well-known/oauth-authorization-server").json()
        assert meta["token_endpoint"].endswith("/oauth/token") and meta["code_challenge_methods_supported"] == ["S256"]
        r = c.post("/mcp", headers=ACCEPT, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r.status_code == 401 and 'resource_metadata="http://testserver/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]

        cb = "https://claude.ai/api/mcp/auth_callback"
        assert c.post("/oauth/register", json={"redirect_uris": ["http://evil.example/cb"]}).status_code == 400
        gem = [f"https://oauth-redirect{s}.googleusercontent.com/{k}/user_bound_custom-mcp-1-x" for s in ("", "-test", "-sandbox") for k in "ra"]
        assert c.post("/oauth/register", json={"redirect_uris": gem, "client_name": "Gemini"}).status_code == 201, "Gemini sends 6 redirect URIs"
        assert c.post("/oauth/register", json={"redirect_uris": gem * 2}).status_code == 400
        client = c.post("/oauth/register", json={"redirect_uris": [cb], "client_name": "Claude"}).json()
        assert client["client_id"].startswith("abc_") and client["token_endpoint_auth_method"] == "none"

        def pkce():
            verifier = base64.urlsafe_b64encode(hashlib.sha256(str(len(mcp_oauth.CODES)).encode() + b"x" * 40).digest()).rstrip(b"=").decode() + "abcdefghijk"
            return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

        def authorize(challenge, **extra):
            q = {"response_type": "code", "client_id": client["client_id"], "redirect_uri": cb, "code_challenge": challenge,
                 "code_challenge_method": "S256", "state": "st8", "scope": "mcp:full", **extra}
            return c.get("/oauth/authorize", params=q, follow_redirects=False)

        verifier, challenge = pkce()
        assert authorize(challenge, redirect_uri="https://evil.example/cb").status_code == 400, "unregistered redirect must be refused"
        assert authorize(challenge, code_challenge_method="plain").status_code == 400, "PKCE S256 is required"
        r = authorize(challenge)
        assert r.status_code == 302 and r.headers["location"].startswith("/?mcp_consent=")
        rid = r.headers["location"].split("=", 1)[1]
        assert c.get(f"/api/mcp/oauth/{rid}").status_code == 401, "the consent page needs a signed-in member"
        info = c.get(f"/api/mcp/oauth/{rid}", headers=hd).json()
        assert info == {"client_name": "Claude", "redirect_host": "claude.ai", "access": "full"}
        back = c.post(f"/api/mcp/oauth/{rid}", json={"allow": True, "access": "full"}, headers=hd).json()["redirect"]
        q = parse_qs(urlparse(back).query)
        assert back.startswith(cb) and q["state"] == ["st8"] and q["code"]
        code = q["code"][0]
        form = {"grant_type": "authorization_code", "code": code, "client_id": client["client_id"], "redirect_uri": cb, "code_verifier": verifier}
        issued = c.post("/oauth/token", data=form).json()
        assert issued["token_type"] == "Bearer" and issued["expires_in"] == 3600 and issued["refresh_token"].startswith("ab_rt_")
        assert c.post("/oauth/token", data=form).json()["error"] == "invalid_grant", "a code works only once"
        assert tools(issued["access_token"]) == ALL, "an approved admin with full access gets every tool"
        assert rpc(issued["refresh_token"], "tools/list")[0] == 401, "a refresh token is not an access token"

        v2, ch2 = pkce()
        rid2 = authorize(ch2).headers["location"].split("=", 1)[1]
        code2 = parse_qs(urlparse(c.post(f"/api/mcp/oauth/{rid2}", json={"allow": True, "access": "read"}, headers=hd).json()["redirect"]).query)["code"][0]
        assert c.post("/oauth/token", data={**form, "code": code2, "code_verifier": "x" * 50}).json()["error"] == "invalid_grant", "a wrong PKCE verifier must fail"

        rid3 = authorize(ch2).headers["location"].split("=", 1)[1]
        denied = c.post(f"/api/mcp/oauth/{rid3}", json={"allow": False}, headers=hd).json()["redirect"]
        assert "error=access_denied" in denied and "state=st8" in denied and "code=" not in denied
        assert c.post(f"/api/mcp/oauth/{rid3}", json={"allow": True}, headers=hd).status_code == 404, "a request can be decided only once"

        renewed = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": issued["refresh_token"]}).json()
        assert renewed["access_token"] != issued["access_token"] and tools(renewed["access_token"]) == ALL
        assert rpc(issued["access_token"], "tools/list")[0] == 401, "refreshing retires the old access token"
        assert c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": issued["refresh_token"]}).json()["error"] == "invalid_grant", "refresh tokens rotate"

        grants = [x for x in c.get("/api/mcp/tokens", headers=hd).json()["tokens"] if x["name"] == "Claude"]
        assert len(grants) == 1 and "ab_" not in json.dumps(grants), "a connected app shows once, without secrets"
        saved = json.loads(mcp_server.TOKENS_FILE.read_text())
        for rec in saved.values():
            if rec.get("kind") == "access":
                rec["exp"] = 1
        mcp_server.TOKENS_FILE.write_text(json.dumps(saved))
        assert rpc(renewed["access_token"], "tools/list")[0] == 401, "an expired access token must be refused"
        again = c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": renewed["refresh_token"]}).json()
        assert tools(again["access_token"]) == ALL
        assert c.delete(f"/api/mcp/tokens/{grants[0]['id']}", headers=hd).json() == {"ok": True}
        assert rpc(again["access_token"], "tools/list")[0] == 401, "revoking the app kills its access token"
        assert c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": again["refresh_token"]}).json()["error"] == "invalid_grant"
        assert any(e["action"] == "mcp app connected" and e["user"] == "ad@m.in" for e in t.audit_log())
finally:
    shutil.rmtree(TENANTS_DIR / tid, ignore_errors=True)
    for f in (mcp_server.TOKENS_FILE, server.LOGINS_FILE, tenants.ACCOUNTS_FILE, mcp_oauth.CLIENTS_FILE):
        f.unlink(missing_ok=True)

print("mcp checks passed")
