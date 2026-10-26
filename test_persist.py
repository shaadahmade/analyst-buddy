import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import persist

table: dict[str, bytes] = {}
log = []


class FakeCursor:
    def __init__(self):
        self.rows = []

    def execute(self, sql, params=()):
        log.append(sql.split()[0])
        if sql.startswith("SELECT"):
            self.rows = sorted(table.items())
        elif sql.startswith("DELETE"):
            for p in params[0]:
                table.pop(p, None)
        return self

    def executemany(self, sql, rows):
        log.append("UPSERT")
        table.update({p: bytes(c) for p, c in rows})

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn(FakeCursor):
    def cursor(self):
        return FakeCursor()


connected = []
sys.modules["psycopg"] = SimpleNamespace(connect=lambda url, **kw: connected.append((url, kw)) or FakeConn())

assert persist.allowed("accounts.json") and persist.allowed("tenants/acme/data/orders.csv")
for bad in ("tenants/acme/outputs/chart.png", "tenants/test-x/users.json", "tenants/../../etc/passwd", ".env",
            "connections.key", "tenants/acme/.cache/x"):
    assert not persist.allowed(bad), bad

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    persist.ROOT, persist.URL, persist.SYNC_EVERY = root, None, 0.05
    persist.os.environ.pop("STATE_DATABASE_URL", None)
    persist.restore()
    persist.start_sync()()
    assert connected == [], "nothing may sync without STATE_DATABASE_URL"

    persist.URL = "postgresql://u:p@db.supabase.co:5432/postgres"
    table.update({"accounts.json": b'{"a@x.in": {}}', "tenants/acme/users.json": b"{}",
                  "tenants/acme/data/orders.csv": b"id\n1\n", "../evil.json": b"x"})
    persist.restore()
    assert connected[0][1]["prepare_threshold"] is None, "must work through Supabase's pooler"
    assert (root / "tenants/acme/data/orders.csv").read_bytes() == b"id\n1\n"
    assert not (root.parent / "evil.json").exists(), "rows may not write outside the app folder"

    (root / "tenants/acme/outputs").mkdir(parents=True)
    (root / "tenants/acme/outputs/chart_1.png").write_bytes(b"x")
    (root / ".env").write_text("SECRET=1")
    log.clear()
    finish = persist.start_sync()
    time.sleep(0.2)
    assert "UPSERT" not in log, "synced with nothing changed"
    (root / "tenants/acme/workspace.json").write_text("{}")
    time.sleep(0.3)
    assert table["tenants/acme/workspace.json"] == b"{}"
    assert "tenants/acme/outputs/chart_1.png" not in table and ".env" not in table
    (root / "tenants/acme/data/orders.csv").unlink()
    (root / "accounts.json").write_text('{"b@x.in": {}}')
    finish()
    assert "tenants/acme/data/orders.csv" not in table, "deleted files are removed from the database"
    assert table["accounts.json"] == b'{"b@x.in": {}}', "the last change must be saved on shutdown"

print("persist checks passed")
