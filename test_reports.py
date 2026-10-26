import shutil
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import reports
import server
from tenants import TENANTS_DIR, Tenant

good = """Here you go:
```json
{"period": "13 to 19 Oct 2026", "headline": "Revenue fell 12%", "figure": "-12%", "figure_tone": "red",
 "figure_note": "Revenue vs last 4 weeks", "figure_source": "orders.csv",
 "findings": [{"tone": "red", "text": "South stopped", "source": "orders.csv"}, {"tone": "purple", "text": "x", "source": ""}],
 "goals": [{"goal": "Reach 1.2 Cr", "status": "at_risk", "note": "82%"}, {"goal": "g2", "status": "weird"}],
 "actions": ["a1", "a2", "a3", "a4"]}
```"""
r = reports.parse_report(good)
assert r["parsed"] and r["figure"] == "-12%" and r["figure_tone"] == "red"
assert r["findings"][1]["tone"] == "ink", "unknown tone must fall back to ink"
assert r["goals"][1]["status"] == "unknown" and len(r["actions"]) == 3
broken = reports.parse_report("I could not finish, sorry {not json")
assert not broken["parsed"] and "could not finish" in broken["findings"][0]["text"]

evil = {**r, "headline": "<script>alert(1)</script>", "findings": [{"tone": "red", "text": "<img src=x onerror=1>", "source": ""}]}
page = reports.render_email(evil, "Acme & Co")
assert "<script>" not in page and "&lt;script&gt;" in page and "<img src=x" not in page and "Acme &amp; Co" in page
assert "At risk" in page and "Do this week" in page

ist = dict(reports.DEFAULT_SETTINGS, enabled=True, weekday=0, hour=8, timezone="Asia/Kolkata")
mon_0730_ist = datetime(2026, 10, 26, 2, 0, tzinfo=timezone.utc)
mon_0830_ist = datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc)
wed_ist = datetime(2026, 10, 28, 6, 0, tzinfo=timezone.utc)
assert reports.is_due(ist, mon_0730_ist, None)[0] is False, "too early"
due, week = reports.is_due(ist, mon_0830_ist, None)
assert due and week == "2026-W44"
assert reports.is_due(ist, mon_0830_ist, "2026-W44")[0] is False, "already sent this week"
assert reports.is_due(ist, wed_ist, None)[0] is True, "catches up later in the week after downtime"
assert reports.is_due({**ist, "enabled": False}, mon_0830_ist, None)[0] is False

tid = "test-reports"
(TENANTS_DIR / tid / "data").mkdir(parents=True, exist_ok=True)
import tenants
tenants.ACCOUNTS_FILE = TENANTS_DIR / "test-reports-accounts.json"
import server as _server
_server.LOGINS_FILE = TENANTS_DIR / "test-reports-logins.json"
tenants.create_account("boss@test.in", "test-reports-pw") if not tenants.account_exists("boss@test.in") else None
Tenant(tid).save_user("boss@test.in", "owner", new=True)
try:
    t = Tenant(tid)
    assert reports.load_settings(t)["enabled"] is False
    saved = reports.save_settings(t, {"enabled": True, "weekday": 0, "hour": 9, "timezone": "Europe/London", "recipients": ["a@b.co"]})
    assert reports.load_settings(t) == saved
    for bad in [{"timezone": "Mars/Base"}, {"hour": 30}, {"recipients": ["nope"]}]:
        try:
            reports.save_settings(t, {**saved, **bad})
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    try:
        reports.report_html(t, "../../acme/knowledge")
        raise AssertionError("path traversal accepted")
    except FileNotFoundError:
        pass

    made = []
    real_generate = reports.generate
    reports.generate = lambda tenant, index: made.append(tenant.id)
    assert reports.run_due(lambda: None, mon_0830_ist.replace(hour=12)) == [tid] or tid in made
    made.clear()
    reports.run_due(lambda: None, mon_0830_ist.replace(hour=13))
    assert tid not in made, "report created twice in one week"
    reports.generate = real_generate

    server.start_sandbox = lambda tn, scope=None: (SimpleNamespace(kill=lambda: None, files=SimpleNamespace(write=lambda p, d: None)), [], "")
    server.build_agent = lambda *a, **k: None
    server.memory_index = lambda: None
    folder = t.dir / "reports"
    folder.mkdir(exist_ok=True)

    def fake_generate(tenant, index):
        rep = reports.parse_report(good)
        (folder / "2026-10-26.json").write_text(__import__("json").dumps(rep), encoding="utf-8")
        (folder / "2026-10-26.html").write_text(reports.render_email(rep, "Test"), encoding="utf-8")

    reports.generate = fake_generate
    client = TestClient(server.app)
    tok = client.post("/api/login", json={"workspace": tid, "email": "boss@test.in", "password": "test-reports-pw"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/reports").status_code == 401
    assert client.post("/api/reports/run", headers=h).status_code == 202
    for _ in range(50):
        if client.get("/api/reports", headers=h).json()["reports"]:
            break
        time.sleep(0.05)
    listing = client.get("/api/reports", headers=h).json()
    assert listing["reports"][0]["name"] == "2026-10-26" and listing["reports"][0]["figure"] == "-12%"
    assert "Revenue fell 12%" in client.get("/api/reports/2026-10-26", headers=h).json()["html"]
    assert client.get("/api/reports/2026-01-01", headers=h).status_code == 404
    assert client.put("/api/reports/settings", json={"timezone": "Mars/Base"}, headers=h).status_code == 400
    assert client.put("/api/reports/settings", json={**saved, "hour": 7}, headers=h).json()["settings"]["hour"] == 7
finally:
    shutil.rmtree(TENANTS_DIR / tid, ignore_errors=True)
    tenants.ACCOUNTS_FILE.unlink(missing_ok=True)
    _server.LOGINS_FILE.unlink(missing_ok=True)

print("all report checks passed")
