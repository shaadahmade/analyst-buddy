import base64
import json
import os
import shutil
import time

import pandas as pd
from cryptography.fernet import Fernet

import connections
import sources
from sources import SourceError
from tenants import TENANTS_DIR, Tenant

connections.KEY_FILE = TENANTS_DIR / "test-conn.key"
connections._keys = None
tid = "test-conn"
(TENANTS_DIR / tid / "data").mkdir(parents=True, exist_ok=True)
(TENANTS_DIR / tid / "users.json").write_text(json.dumps({"boss@x.in": {"role": "owner", "scope": None}}))
t = Tenant(tid)
calls = []


def fake_test(cfg, secret, http):
    calls.append(("test", secret))
    if secret.get("api_key") == "bad":
        raise SourceError("Fake app refused the request (401).")
    return "Fake test mode"


def fake_fetch(cfg, secret, http):
    calls.append(("fetch", secret))
    if secret.get("api_key") == "boom":
        raise RuntimeError("network died")
    return {"sales_orders": pd.DataFrame({"created": ["2026-01-02 10:00:00", "2026-10-01 09:00:00"], "amount": [12.5, 3.0]}),
            "sales_refunds": pd.DataFrame()}


sources.CONNECTORS["fake"] = {"name": "Fake app", "secrets": ["api_key"], "config": [], "test": fake_test, "fetch": fake_fetch}
try:
    assert connections.unseal(connections.seal({"a": "b"}, t, "c1"), t, "c1") == {"a": "b"}
    sealed = connections.seal({"api_key": "sk_live_x"}, t, "c1")
    assert sealed.startswith("v2:") and "sk_live_x" not in sealed and sealed != connections.seal({"api_key": "sk_live_x"}, t, "c1")
    for other_tenant, purpose in ((type("T", (), {"id": "someone-else"})(), "c1"), (t, "c2")):
        try:
            connections.unseal(sealed, other_tenant, purpose)
            raise AssertionError("a secret must only open for its own tenant and connection")
        except SourceError:
            pass
    old_key = connections.master_keys()[0]
    legacy = Fernet(old_key).encrypt(b'{"api_key": "legacy"}').decode()
    assert connections.unseal(legacy, t, "c1") == {"api_key": "legacy"}, "secrets saved before v2 still open"
    try:
        connections.create(t, "fake", {}, {"api_key": "bad"}, "boss@x.in")
        raise AssertionError("a failing key test must not save the connection")
    except SourceError:
        assert connections.overview(t)["items"] == []
    try:
        connections.create(t, "fake", {}, {}, "boss@x.in")
        raise AssertionError("a missing key must be refused")
    except SourceError as exc:
        assert "api_key" in str(exc)

    item = connections.create(t, "fake", {}, {"api_key": "rk_test_secret_123"}, "boss@x.in")
    assert item["label"] == "Fake test mode" and "secret" not in item and item["status"] == "connected"
    connections._update(t, item["id"], status="syncing")
    stale = connections.overview(t)["items"][0]
    assert stale["status"] == "error" and "interrupted" in stale["message"] and not stale["syncing"], "a sync cut off by a restart must not spin forever"
    connections._update(t, item["id"], status="connected")
    raw = (t.dir / "connections.json").read_text()
    assert "rk_test_secret_123" not in raw, "keys must be stored encrypted"

    pushed = []
    done = connections.sync(t, item["id"], lambda tenant, files: pushed.append(files))
    assert done["status"] == "ok" and done["tables"] == ["sales_orders.csv"] and done["rows"] == 2, done
    assert "sales_refunds" in done["message"], "an empty table is reported, not saved"
    assert (t.data_dir / "sales_orders.csv").read_text().startswith("created,amount")
    assert pushed == [["sales_orders.csv"]]
    note = t.knowledge()["data_notes"][-1]
    assert note["tables"] == ["sales_orders.csv"] and "dates 2026-01-02 to 2026-10-01" in note["note"] and "Fake app" in note["note"]
    assert calls[-1] == ("fetch", {"api_key": "rk_test_secret_123"})

    assert not connections.due(connections._load(t)["items"][0], time.time())
    assert connections.due(connections._load(t)["items"][0], time.time() + connections.SYNC_EVERY_SECONDS + 1)
    calls.clear()
    connections.run_due(at=time.time() + connections.SYNC_EVERY_SECONDS + 1)
    assert [c[0] for c in calls] == ["fetch"], "the scheduler syncs a connection that is a day old"

    broken = connections.create(t, "fake", {}, {"api_key": "boom"}, "boss@x.in")
    out = connections.sync(t, broken["id"])
    assert out["status"] == "error" and "unexpectedly" in out["message"] and "network died" not in out["message"]

    connections._syncing.add(item["id"])
    assert connections.sync(t, item["id"]) is None, "a sync already running must not start twice"
    connections._syncing.discard(item["id"])

    assert connections.remove(t, broken["id"]) and not connections.remove(t, broken["id"])

    try:
        connections.create(t, "sheets", {"sheet_url": "https://docs.google.com/spreadsheets/d/" + "x" * 30}, {}, "boss@x.in")
        raise AssertionError("sheets need a Google account first")
    except SourceError as exc:
        assert "Connect a Google account" in str(exc)
    connections.save_google(t, "me@gmail.com", "refresh-abc", "boss@x.in")
    assert "refresh-abc" not in (t.dir / "connections.json").read_text()
    assert connections.overview(t)["google"] == {"email": "me@gmail.com", "connected_by": "boss@x.in"}
    assert connections.google_secret(t) == {"refresh_token": "refresh-abc"}
    sources.CONNECTORS["sheets"]["test"] = lambda cfg, secret, http: f"sheet {cfg['sheet_id'][:3]} via {secret['refresh_token']}"
    sheet = connections.create(t, "sheets", {"sheet_url": "https://docs.google.com/spreadsheets/d/" + "s" * 30 + "/edit"}, {}, "boss@x.in")
    assert sheet["label"] == "sheet sss via refresh-abc" and sheet["config"] == {"sheet_id": "s" * 30}
    connections.forget_google(t)
    assert connections.overview(t)["google"] is None
    assert [i["kind"] for i in connections.overview(t)["items"]] == ["fake"], "forgetting Google removes Google sources"

    state = connections.sign_state({"t": tid, "u": "boss@x.in"})
    assert connections.read_state(state) == {"t": tid, "u": "boss@x.in", "exp": json.loads(base64.urlsafe_b64decode(state.split(".")[0]))["exp"]}
    raw, mac = state.split(".")
    forged = base64.urlsafe_b64encode(json.dumps({"t": "other", "u": "boss@x.in", "exp": time.time() + 600}).encode()).decode()
    assert connections.read_state(forged + "." + mac) is None, "a state for another workspace must be rejected"
    assert connections.read_state(raw + ".0000") is None
    old = connections.STATE_MAX_AGE
    connections.STATE_MAX_AGE = -1
    assert connections.read_state(connections.sign_state({"t": tid})) is None, "an old state must be rejected"
    connections.STATE_MAX_AGE = old

    claims = base64.urlsafe_b64encode(json.dumps({"email": "Me@Gmail.com"}).encode()).decode().rstrip("=")

    class TokenHTTP:
        def post(self, url, **kw):
            assert kw["data"]["grant_type"] == "authorization_code" and kw["data"]["code"] == "c0de"
            return type("R", (), {"status_code": 200, "json": lambda self: {"refresh_token": "r9", "id_token": f"h.{claims}.s"}})()

    assert connections.google_exchange("c0de", "https://x/cb", TokenHTTP()) == ("me@gmail.com", "r9")
    assert "access_type=offline" in connections.google_auth_url("st", "https://x/cb") and "spreadsheets.readonly" in connections.google_auth_url("st", "https://x/cb")
    connections._save(t, {**connections._load(t), "google": {"email": "me@gmail.com", "connected_by": "boss@x.in", "at": "",
                                                               "secret": Fernet(old_key).encrypt(b'{"refresh_token": "r1"}').decode()}})
    assert connections.rewrap(t) >= 1 and connections.rewrap(t) == 0, "old secrets are re-encrypted once"
    new_key = Fernet.generate_key()
    os.environ["CONNECTIONS_KEY"] = f"{new_key.decode()},{old_key.decode()}"
    connections._keys = None
    assert connections.google_secret(t) == {"refresh_token": "r1"}, "an old key still opens secrets after rotation"
    assert connections.rewrap(t) >= 1 and all(i["secret"].startswith(f"v2:{connections.key_id(new_key)}:")
                                              for i in connections._load(t)["items"] if i.get("secret"))
    assert connections._load(t)["google"]["secret"].startswith(f"v2:{connections.key_id(new_key)}:")
    os.environ["CONNECTIONS_KEY"] = new_key.decode()
    connections._keys = None
    assert connections.google_secret(t) == {"refresh_token": "r1"}, "rotation is complete once the old key is dropped"
finally:
    os.environ.pop("CONNECTIONS_KEY", None)
    connections._keys = None
    shutil.rmtree(TENANTS_DIR / tid, ignore_errors=True)
    connections.KEY_FILE.unlink(missing_ok=True)
    sources.CONNECTORS.pop("fake", None)

print("connection checks passed")
