import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from datetime import date
from pathlib import Path

TENANTS_DIR = Path(__file__).parent / "tenants"
ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"
INDEX_NAME = "analyst-memory"
EMBED_MODEL = "llama-text-embed-v2"
TENANT_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,39}")
EMPTY_KNOWLEDGE = {"company": "", "goals": [], "kpis": [], "definitions": {}}
MAX_GOALS = 20
ROLES = ("owner", "admin", "analyst", "viewer")
PERMISSIONS = {
    "owner": {"upload", "teach", "reports", "reports.manage", "users"},
    "admin": {"upload", "teach", "reports", "reports.manage", "users"},
    "analyst": {"upload", "teach", "reports"},
    "viewer": {"reports"},
}
USER_ID = re.compile(r"[^\s@]+(@[^\s@]+\.[^\s@]+)?")
_users_lock = threading.Lock()
_audit_lock = threading.Lock()
_accounts_lock = threading.RLock()


def normal_email(email: str) -> str:
    email = email.strip().lower()
    if not USER_ID.fullmatch(email) or len(email) > 254:
        raise ValueError("Enter a valid email address")
    return email


def load_accounts() -> dict:
    return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8")) if ACCOUNTS_FILE.exists() else {}


def _save_accounts(accounts: dict):
    ACCOUNTS_FILE.write_text(json.dumps(accounts, indent=2), encoding="utf-8")


def create_account(email: str, password: str) -> str:
    email = normal_email(email)
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    with _accounts_lock:
        accounts = load_accounts()
        if email in accounts:
            raise ValueError(f"{email} already has an account. Sign in instead.")
        accounts[email] = {"salt": salt.hex(), "hash": _hash(password, salt).hex()}
        _save_accounts(accounts)
    return email


def check_account(email: str, password: str) -> str | None:
    email = email.strip().lower()
    account = load_accounts().get(email)
    if not account or "hash" not in account:
        _hash(password, b"0" * 16)
        return None
    if not hmac.compare_digest(_hash(password, bytes.fromhex(account["salt"])).hex(), account["hash"]):
        return None
    return email


def ensure_google_account(email: str) -> str:
    email = normal_email(email)
    with _accounts_lock:
        accounts = load_accounts()
        accounts.setdefault(email, {})["google"] = True
        _save_accounts(accounts)
    return email


def account_exists(email: str) -> bool:
    return email.strip().lower() in load_accounts()


def set_last_workspace(email: str, tenant_id: str):
    with _accounts_lock:
        accounts = load_accounts()
        if email in accounts:
            accounts[email]["last"] = tenant_id
            _save_accounts(accounts)


def last_workspace(email: str) -> str | None:
    return load_accounts().get(email, {}).get("last")


def all_tenants() -> list["Tenant"]:
    return [Tenant(p.name) for p in sorted(TENANTS_DIR.iterdir()) if p.is_dir() and TENANT_ID.fullmatch(p.name)] \
        if TENANTS_DIR.exists() else []


def workspaces_of(email: str) -> list[dict]:
    return [{"id": t.id, "name": t.name(), "role": u["role"]} for t in all_tenants() if (u := t.users().get(email))]


def create_workspace(name: str, owner: str) -> "Tenant":
    name = name.strip()
    if not 1 <= len(name) <= 60:
        raise ValueError("Give the workspace a name (up to 60 characters)")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "workspace"
    tenant_id = f"{slug}-{secrets.token_hex(3)}"
    (TENANTS_DIR / tenant_id / "data").mkdir(parents=True)
    t = Tenant(tenant_id)
    (t.dir / "workspace.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    t.users_file.write_text(json.dumps({owner: {"role": "owner", "scope": None}}, indent=2), encoding="utf-8")
    t.audit(owner, "workspace created", name=name)
    return t


def migrate_accounts(workspaces: list["Tenant"] | None = None):
    with _accounts_lock:
        accounts = load_accounts()
        for t in all_tenants() if workspaces is None else workspaces:
            users = t.users()
            if t.auth_file.exists() and "owner" in users:
                users["owner"] = {**users["owner"], **json.loads(t.auth_file.read_text())}
            if not any("hash" in u for u in users.values()):
                continue
            for email, u in users.items():
                if "hash" in u:
                    accounts.setdefault(email, {"salt": u.pop("salt"), "hash": u.pop("hash")})
            _save_accounts(accounts)
            t.users_file.write_text(json.dumps(users, indent=2), encoding="utf-8")
            if t.auth_file.exists():
                t.auth_file.rename(t.auth_file.with_suffix(".json.migrated"))


def permissions(role: str, scope: dict | None) -> set[str]:
    return set() if scope is not None else PERMISSIONS[role]


def clean_scope(scope, role: str) -> dict | None:
    if scope is None:
        return None
    if role in ("owner", "admin"):
        raise ValueError("Owners and admins always see all data")
    if not isinstance(scope, dict) or len(scope) > 50:
        raise ValueError("Data access must list the files this person can see")
    clean = {}
    for name, rule in scope.items():
        rule = rule or {}
        rows, hide = rule.get("rows") or {}, rule.get("hide") or []
        if not isinstance(name, str) or not isinstance(rows, dict) or not isinstance(hide, list):
            raise ValueError(f"Invalid data access rule for {name}")
        if any(not isinstance(v, list) or not v for v in rows.values()):
            raise ValueError(f"{name}: each row filter needs at least one allowed value")
        clean[Path(name).name] = {"rows": {str(c): [str(v) for v in vs] for c, vs in rows.items()},
                                  "hide": [str(c) for c in hide]}
    return clean


class Tenant:
    def __init__(self, tenant_id: str):
        if not TENANT_ID.fullmatch(tenant_id):
            raise ValueError(f"invalid tenant id: {tenant_id!r} (use lowercase letters, digits, '-')")
        self.id = tenant_id
        self.dir = TENANTS_DIR / tenant_id
        if not self.dir.is_dir():
            raise ValueError(f"unknown tenant: {tenant_id!r} (create {self.dir})")
        self.data_dir = self.dir / "data"
        self.output_dir = self.dir / "outputs"
        self.knowledge_file = self.dir / "knowledge.json"
        self.auth_file = self.dir / "auth.json"
        self.users_file = self.dir / "users.json"

    def users(self) -> dict:
        if self.users_file.exists():
            return json.loads(self.users_file.read_text(encoding="utf-8"))
        if self.auth_file.exists():
            return {"owner": {**json.loads(self.auth_file.read_text()), "role": "owner", "scope": None}}
        return {}

    def name(self) -> str:
        path = self.dir / "workspace.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["name"]
        return self.knowledge().get("company") or self.id

    def save_user(self, email: str, role: str, scope=None, new: bool = False) -> dict:
        email = normal_email(email)
        if role not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        scope = clean_scope(scope, role)
        with _users_lock:
            users = self.users()
            if new and email in users:
                raise ValueError(f"{email} is already a member")
            if not new and email not in users:
                raise KeyError(email)
            users[email] = {"role": role, "scope": scope}
            self._save_users(users)
        return public_user(email, users[email])

    def remove_user(self, email: str):
        with _users_lock:
            users = self.users()
            del users[email]
            self._save_users(users)

    def _save_users(self, users: dict):
        if not any(u["role"] == "owner" for u in users.values()):
            raise ValueError("The company needs at least one owner")
        self.users_file.write_text(json.dumps(users, indent=2), encoding="utf-8")

    def audit(self, user: str | None, action: str, **detail):
        entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": user, "action": action, **detail}
        with _audit_lock, (self.dir / "audit.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def audit_log(self, limit: int = 100) -> list[dict]:
        path = self.dir / "audit.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()[-limit:]][::-1]

    def knowledge(self) -> dict:
        if not self.knowledge_file.exists():
            return dict(EMPTY_KNOWLEDGE)
        return json.loads(self.knowledge_file.read_text(encoding="utf-8"))

    def save_goals(self, goals) -> list[str]:
        if not isinstance(goals, list) or len(goals) > MAX_GOALS:
            raise ValueError(f"Keep at most {MAX_GOALS} goals")
        clean = []
        for g in goals:
            text = " ".join(str(g).split())
            if not 1 <= len(text) <= 200:
                raise ValueError("Each goal must be 1 to 200 characters")
            if text.lower() not in (c.lower() for c in clean):
                clean.append(text)
        with _users_lock:
            knowledge = self.knowledge()
            knowledge["goals"] = clean
            self.knowledge_file.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")
        return clean

    def forget_tables(self, names: list[str]):
        with _users_lock:
            knowledge = self.knowledge()
            notes = []
            for n in knowledge.get("data_notes", []):
                left = [t for t in n["tables"] if t not in names]
                if left:
                    notes.append({**n, "tables": left})
            knowledge["data_notes"] = notes
            self.knowledge_file.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")

    def add_data_note(self, source: str, tables: list[str], note: str):
        with _users_lock:
            knowledge = self.knowledge()
            notes = [n for n in knowledge.get("data_notes", []) if not set(n["tables"]) & set(tables)]
            notes.append({"source": source, "tables": tables, "added": date.today().isoformat(), "note": note[:3000]})
            knowledge["data_notes"] = notes[-20:]
            self.knowledge_file.write_text(json.dumps(knowledge, indent=2, ensure_ascii=False), encoding="utf-8")


def public_user(email: str, user: dict) -> dict:
    return {"email": email, "role": user["role"], "scope": user.get("scope")}


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


class Memory:

    def __init__(self, tenant: Tenant, index, user: str | None = None, role: str = "owner", scope: dict | None = None):
        self.namespace = tenant.id
        self.index = index
        self.owner = "company" if user is None or "teach" in permissions(role, scope) else user
        if scope is not None:
            self.filter = {"owner": {"$eq": user}}
        else:
            self.filter = {"$or": [{"owner": {"$in": ["company", user or "company"]}}, {"owner": {"$exists": False}}]}

    def remember(self, text: str, kind: str = "insight") -> str:
        record_id = uuid.uuid4().hex
        self.index.upsert_records(namespace=self.namespace, records=[
            {"_id": record_id, "text": text, "kind": kind, "created": date.today().isoformat(), "owner": self.owner},
        ])
        return record_id

    def recall(self, query: str, top_k: int = 5) -> list[str]:
        response = self.index.search(
            namespace=self.namespace, top_k=top_k, inputs={"text": query}, fields=["text", "kind", "created"],
            filter=self.filter,
        )
        return [f"[{h.fields.get('kind')}, {h.fields.get('created')}] {h.fields['text']}" for h in response.result.hits]


def open_index():
    from pinecone import Pinecone

    pc = Pinecone()
    if not pc.has_index(INDEX_NAME):
        pc.create_index_for_model(
            name=INDEX_NAME, cloud="aws", region="us-east-1",
            embed={"model": EMBED_MODEL, "field_map": {"text": "text"}},
        )
    return pc.Index(name=INDEX_NAME)


if __name__ == "__main__":
    import getpass
    import sys

    if sys.argv[1:2] != ["add-user"] or len(sys.argv) != 5:
        sys.exit(f"usage: python tenants.py add-user <tenant_id> <email> <{'|'.join(ROLES)}>")
    t, email, role = Tenant(sys.argv[2]), sys.argv[3], sys.argv[4]
    try:
        migrate_accounts()
        if not account_exists(email):
            create_account(email, getpass.getpass("Password for the new account: "))
        t.save_user(email, role, new=email.strip().lower() not in t.users())
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{email} saved as {role}")
