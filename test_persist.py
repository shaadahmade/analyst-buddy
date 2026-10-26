import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import persist

calls = []


class FakeApi:
    def create_repo(self, repo_id, **kw):
        calls.append(("create", repo_id, kw["private"]))

    def upload_folder(self, **kw):
        calls.append(("upload", kw["repo_id"], kw["allow_patterns"], kw["ignore_patterns"]))


sys.modules["huggingface_hub"] = SimpleNamespace(
    HfApi=FakeApi, snapshot_download=lambda repo, **kw: calls.append(("download", repo, kw["allow_patterns"])))

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    persist.ROOT, persist.REPO, persist.SYNC_EVERY = root, None, 0.05
    persist.restore()
    persist.start_sync()()
    assert calls == [], "nothing may sync without STATE_REPO"

    persist.REPO = "me/state"
    persist.restore()
    assert calls == [("create", "me/state", True), ("download", "me/state", persist.PATTERNS)], calls

    (root / "tenants" / "acme" / "outputs").mkdir(parents=True)
    (root / "accounts.json").write_text("{}")
    before = persist.fingerprint()
    (root / "tenants" / "acme" / "outputs" / "chart_1.png").write_bytes(b"x")
    assert persist.fingerprint() == before, "charts must not trigger a sync"

    calls.clear()
    finish = persist.start_sync()
    time.sleep(0.2)
    assert calls == [], "synced with nothing changed"
    (root / "tenants" / "acme" / "users.json").write_text("{}")
    time.sleep(0.3)
    assert [c[0] for c in calls] == ["upload"] and "tenants/*/outputs/**" in calls[0][3], calls
    (root / "accounts.json").write_text('{"a": 1}')
    finish()
    assert len(calls) == 2, "the last change must be pushed on shutdown"

print("persist checks passed")
