import logging
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent
URL = None
TOP = ("accounts.json", "logins.json", "mcp_tokens.json", "oauth_clients.json")
TABLE = "app_files"
SCHEMA = (f"CREATE TABLE IF NOT EXISTS {TABLE} (path text PRIMARY KEY, content bytea NOT NULL, "
          f"updated_at timestamptz NOT NULL DEFAULT now())")
SYNC_EVERY = 30
log = logging.getLogger("persist")
_synced: dict[str, tuple[int, int]] = {}


def allowed(path: str) -> bool:
    parts = path.split("/")
    if path in TOP:
        return True
    return (len(parts) >= 3 and parts[0] == "tenants" and parts[2] != "outputs" and not parts[1].startswith("test-")
            and ".cache" not in parts and ".." not in parts)


def snapshot() -> dict[str, tuple[int, int]]:
    files = [ROOT / n for n in TOP if (ROOT / n).is_file()]
    if (ROOT / "tenants").exists():
        files += [p for p in (ROOT / "tenants").rglob("*") if p.is_file()]
    found = {}
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        if allowed(rel):
            stat = p.stat()
            found[rel] = (stat.st_mtime_ns, stat.st_size)
    return found


def url() -> str | None:
    return URL or os.getenv("STATE_DATABASE_URL")


def connect():
    import psycopg

    return psycopg.connect(url(), prepare_threshold=None)


def restore():
    global _synced
    if not url():
        return
    with connect() as conn:
        conn.execute(SCHEMA)
        rows = conn.execute(f"SELECT path, content FROM {TABLE}").fetchall()
    root = ROOT.resolve()
    for path, content in rows:
        target = (ROOT / path).resolve()
        if not allowed(path) or root not in target.parents:
            log.warning("skipped unexpected path in %s: %r", TABLE, path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(bytes(content))
    _synced = {p: v for p, v in snapshot().items() if p in {r[0] for r in rows}}
    log.info("restored %d files from the state database", len(rows))


def push(done: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    now = snapshot()
    changed = [p for p, v in now.items() if done.get(p) != v]
    gone = [p for p in done if p not in now]
    if changed or gone:
        with connect() as conn, conn.cursor() as cur:
            if changed:
                cur.executemany(f"INSERT INTO {TABLE} (path, content, updated_at) VALUES (%s, %s, now()) "
                                f"ON CONFLICT (path) DO UPDATE SET content = EXCLUDED.content, updated_at = now()",
                                [(p, (ROOT / p).read_bytes()) for p in changed])
            if gone:
                cur.execute(f"DELETE FROM {TABLE} WHERE path = ANY(%s)", (gone,))
        log.info("synced state: %d changed, %d removed", len(changed), len(gone))
    return now


def start_sync():
    stop = threading.Event()
    if not url():
        return lambda: None
    seen = {"done": dict(_synced)}

    def sync_if_changed():
        try:
            seen["done"] = push(seen["done"])
        except Exception:
            log.warning("state sync failed, will retry", exc_info=True)

    def loop():
        while not stop.wait(SYNC_EVERY):
            sync_if_changed()
        sync_if_changed()

    thread = threading.Thread(target=loop, name="state-sync", daemon=True)
    thread.start()

    def finish():
        stop.set()
        thread.join(timeout=60)

    return finish


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    if sys.argv[1:] != ["push"] or not url():
        sys.exit("usage: python persist.py push  (with STATE_DATABASE_URL in .env)")
    with connect() as conn:
        conn.execute(SCHEMA)
    print(f"pushed {len(push({}))} files to the state database")
