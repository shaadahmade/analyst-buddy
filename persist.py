import logging
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent
REPO = os.getenv("STATE_REPO")
PATTERNS = ["accounts.json", "logins.json", "mcp_tokens.json", "oauth_clients.json", "tenants/**"]
SKIP = ["tenants/*/outputs/**", "tenants/test-*/**", "**/.cache/**"]
SYNC_EVERY = 30
log = logging.getLogger("persist")


def fingerprint() -> frozenset:
    files = [ROOT / n for n in ("accounts.json", "logins.json", "mcp_tokens.json", "oauth_clients.json") if (ROOT / n).exists()]
    tenants = ROOT / "tenants"
    if tenants.exists():
        files += [p for p in tenants.rglob("*") if p.is_file() and p.relative_to(tenants).parts[1:2] != ("outputs",)]
    return frozenset((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files)


def restore():
    if not REPO:
        return
    from huggingface_hub import HfApi, snapshot_download

    HfApi().create_repo(REPO, repo_type="dataset", private=True, exist_ok=True)
    snapshot_download(REPO, repo_type="dataset", local_dir=ROOT, allow_patterns=PATTERNS)
    log.info("restored state from %s", REPO)


def push():
    from huggingface_hub import HfApi

    HfApi().upload_folder(repo_id=REPO, repo_type="dataset", folder_path=ROOT, allow_patterns=PATTERNS,
                          ignore_patterns=SKIP, commit_message="sync app state")


def start_sync():
    stop = threading.Event()
    if not REPO:
        return lambda: None
    seen = {"last": fingerprint()}

    def sync_if_changed():
        now = fingerprint()
        if now != seen["last"]:
            try:
                push()
                seen["last"] = now
            except Exception:
                log.warning("state sync to %s failed, will retry", REPO, exc_info=True)

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
    if sys.argv[1:] != ["push"] or not REPO:
        sys.exit("usage: STATE_REPO=<user>/<dataset> HF_TOKEN=<token> python persist.py push")
    from huggingface_hub import HfApi

    HfApi().create_repo(REPO, repo_type="dataset", private=True, exist_ok=True)
    push()
    print(f"pushed accounts and workspaces to {REPO}")
