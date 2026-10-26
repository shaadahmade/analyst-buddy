import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import mcp_auth
import sources
from sources import CONNECTORS, SourceError
from tenants import Tenant, all_tenants

KEY_FILE = Path(__file__).parent / "connections.key"
SYNC_EVERY_SECONDS = 24 * 3600
MAX_TABLE_BYTES = 50 * 1024 * 1024
STATE_MAX_AGE = 600
log = logging.getLogger("connections")
_lock = threading.Lock()
_syncing: set[str] = set()
_shopify_tokens: dict[str, dict] = {}
_keys = None


def master_keys() -> list[bytes]:
    global _keys
    if _keys is None:
        raw = os.getenv("CONNECTIONS_KEY", "")
        if not raw:
            if not KEY_FILE.exists():
                KEY_FILE.write_bytes(Fernet.generate_key())
            raw = KEY_FILE.read_text(encoding="utf-8")
        _keys = [k.strip().encode() for k in raw.split(",") if k.strip()]
        for k in _keys:
            Fernet(k)
    return _keys


def key_id(master: bytes) -> str:
    return hashlib.sha256(b"key-id" + master).hexdigest()[:8]


def tenant_cipher(master: bytes, t: Tenant) -> AESGCM:
    hkdf = HKDF(hashes.SHA256(), 32, salt=b"analyst-buddy/connections/v2", info=t.id.encode())
    return AESGCM(hkdf.derive(base64.urlsafe_b64decode(master)))


def seal(data: dict, t: Tenant, purpose: str) -> str:
    master, nonce = master_keys()[0], os.urandom(12)
    sealed = tenant_cipher(master, t).encrypt(nonce, json.dumps(data).encode(), f"{t.id}/{purpose}".encode())
    return f"v2:{key_id(master)}:" + base64.urlsafe_b64encode(nonce + sealed).decode()


def unseal(token: str, t: Tenant, purpose: str) -> dict:
    try:
        if token.startswith("v2:"):
            _, kid, body = token.split(":", 2)
            master = next(k for k in master_keys() if key_id(k) == kid)
            raw = base64.urlsafe_b64decode(body)
            return json.loads(tenant_cipher(master, t).decrypt(raw[:12], raw[12:], f"{t.id}/{purpose}".encode()))
        return json.loads(MultiFernet([Fernet(k) for k in master_keys()]).decrypt(token.encode()))
    except (StopIteration, InvalidTag, InvalidToken, ValueError):
        raise SourceError("The saved keys can no longer be read. Disconnect this source and connect it again.") from None


def rewrap(t: Tenant) -> int:
    current = f"v2:{key_id(master_keys()[0])}:"
    changed = 0
    with _lock:
        data = _load(t)
        holders = [(data["google"], "google")] if data.get("google") else []
        holders += [(i, i["id"]) for i in data["items"] if i.get("secret")]
        for holder, purpose in holders:
            if holder["secret"].startswith(current):
                continue
            try:
                holder["secret"] = seal(unseal(holder["secret"], t, purpose), t, purpose)
                changed += 1
            except SourceError:
                log.warning("unreadable secret tenant=%s purpose=%s", t.id, purpose)
        if changed:
            _save(t, data)
    return changed


def rewrap_all() -> int:
    return sum(rewrap(t) for t in all_tenants())


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file(t: Tenant) -> Path:
    return t.dir / "connections.json"


def _load(t: Tenant) -> dict:
    path = _file(t)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"google": None, "items": []}


def _save(t: Tenant, data: dict):
    _file(t).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _public(item: dict) -> dict:
    public = {k: v for k, v in item.items() if k != "secret"}
    if public["status"] == "syncing" and item["id"] not in _syncing:
        public.update(status="error", message="The last sync was interrupted. Click Refresh.")
    return {**public, "syncing": item["id"] in _syncing}


def overview(t: Tenant) -> dict:
    data = _load(t)
    google = data.get("google")
    return {"google": {"email": google["email"], "connected_by": google["connected_by"]} if google else None,
            "google_ready": bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")),
            "items": [_public(i) for i in data["items"]]}


def save_google(t: Tenant, email: str, refresh_token: str, user: str):
    with _lock:
        data = _load(t)
        data["google"] = {"email": email, "secret": seal({"refresh_token": refresh_token}, t, "google"), "connected_by": user,
                          "at": now()}
        _save(t, data)


def forget_google(t: Tenant):
    with _lock:
        data = _load(t)
        data["google"] = None
        data["items"] = [i for i in data["items"] if not CONNECTORS[i["kind"]].get("google")]
        _save(t, data)


def google_secret(t: Tenant) -> dict:
    google = _load(t).get("google")
    if not google:
        raise SourceError("Connect a Google account first.")
    return unseal(google["secret"], t, "google")


def clean_config(kind: str, config: dict) -> dict:
    if kind == "shopify":
        return {"shop": sources.shop_domain(config.get("shop", ""))}
    if kind == "sheets":
        return {"sheet_id": sources.sheet_id(config.get("sheet_url", ""))}
    if kind == "mcp":
        return {"url": sources.mcp_url(str(config.get("url", ""))), "tools": sources.clean_mcp_tools(config.get("tools"))}
    if kind == "ga4":
        pid = str(config.get("property_id", "")).strip()
        if not pid.isdigit():
            raise SourceError("Pick a Google Analytics property.")
        return {"property_id": pid}
    return {}


def create(t: Tenant, kind: str, config: dict, secret: dict, user: str, http=None, signed_in: dict | None = None) -> dict:
    spec = CONNECTORS[kind]
    secret = signed_in or {k: str(secret.get(k, "")).strip() for k in spec["secrets"]}
    missing = [k for k, v in secret.items() if not v and not spec.get("optional_secrets")]
    if missing:
        raise SourceError(f"Fill in: {', '.join(missing)}")
    config = clean_config(kind, config)
    label = spec["test"](config, google_secret(t) if spec.get("google") else secret, http or sources.new_http())
    conn_id = uuid.uuid4().hex[:12]
    item = {"id": conn_id, "kind": kind, "name": spec["name"], "label": label, "config": config,
            "secret": None if spec.get("google") else seal(secret, t, conn_id), "created_by": user, "created": now(),
            "last_sync": None, "status": "connected", "message": "", "tables": [], "rows": 0}
    with _lock:
        data = _load(t)
        data["items"].append(item)
        _save(t, data)
    return _public(item)


def remove(t: Tenant, conn_id: str) -> bool:
    with _lock:
        data = _load(t)
        kept = [i for i in data["items"] if i["id"] != conn_id]
        if len(kept) == len(data["items"]):
            return False
        data["items"] = kept
        _save(t, data)
    _shopify_tokens.pop(conn_id, None)
    return True


def _update(t: Tenant, conn_id: str, **fields):
    with _lock:
        data = _load(t)
        for item in data["items"]:
            if item["id"] == conn_id:
                item.update(fields)
        _save(t, data)


def describe(kind: str, frames: dict, files: dict) -> str:
    lines = [f"Synced from {CONNECTORS[kind]['name']} on {now()[:10]} (last {sources.LOOKBACK_DAYS} days)."]
    for name, df in frames.items():
        if name + ".csv" not in files:
            continue
        when = next((c for c in ("created", "date") if c in df.columns), None)
        span = ""
        if when is not None and len(df):
            dates = df[when].astype(str).str[:10]
            span = f", dates {dates.min()} to {dates.max()}"
        lines.append(f"- {name}.csv: {len(df):,} rows{span}; columns: {', '.join(map(str, df.columns[:25]))}")
    if kind == "shopify":
        lines.append("Money columns are in the store currency, as decimal amounts.")
    return "\n".join(lines)


def sync(t: Tenant, conn_id: str, on_tables=None, http=None) -> dict | None:
    with _lock:
        if conn_id in _syncing:
            return None
        _syncing.add(conn_id)
    try:
        item = next((i for i in _load(t)["items"] if i["id"] == conn_id), None)
        if item is None:
            return None
        spec = CONNECTORS[item["kind"]]
        _update(t, conn_id, status="syncing", message="")
        try:
            secret = google_secret(t) if spec.get("google") else unseal(item["secret"], t, conn_id)
            http = http or sources.new_http()
            if item["kind"] == "mcp" and mcp_auth.refresh_if_needed(secret):
                _update(t, conn_id, secret=seal(secret, t, conn_id))
            if item["kind"] == "shopify":
                frames = sources.shopify_fetch(item["config"], secret, http, _shopify_tokens.setdefault(conn_id, {}))
            else:
                frames = spec["fetch"](item["config"], secret, http)
            files = {}
            t.data_dir.mkdir(parents=True, exist_ok=True)
            for name, df in frames.items():
                data = df.to_csv(index=False).encode()
                if len(df) and len(data) <= MAX_TABLE_BYTES:
                    (t.data_dir / f"{name}.csv").write_bytes(data)
                    files[f"{name}.csv"] = len(df)
            if files:
                t.add_data_note(item["kind"], list(files), describe(item["kind"], frames, files))
            skipped = [n for n, df in frames.items() if f"{n}.csv" not in files]
            message = f"Empty or too big, not saved: {', '.join(skipped)}" if skipped else ""
            _update(t, conn_id, status="ok", last_sync=now(), tables=list(files), rows=sum(files.values()),
                    message=message)
            t.audit(item["created_by"], "data sync", source=item["kind"], tables=len(files))
            if files and on_tables:
                on_tables(t, list(files))
        except SourceError as exc:
            _update(t, conn_id, status="error", last_sync=now(), message=str(exc))
        except Exception:
            log.error("sync failed tenant=%s kind=%s", t.id, item["kind"], exc_info=True)
            _update(t, conn_id, status="error", last_sync=now(), message="The sync failed unexpectedly. Try again later.")
        return _public(next(i for i in _load(t)["items"] if i["id"] == conn_id))
    finally:
        _syncing.discard(conn_id)


def live_shopify(t: Tenant, query: str, variables: dict | None = None, http=None) -> tuple[str, dict]:
    stores = [i for i in _load(t)["items"] if i["kind"] == "shopify"]
    if not stores:
        raise SourceError("No Shopify store is connected.")
    item = stores[0]
    data = sources.shopify_live(item["config"], unseal(item["secret"], t, item["id"]), http or sources.new_http(),
                                _shopify_tokens.setdefault(item["id"], {}), query, variables)
    return item["config"]["shop"], data


def has_shopify(t: Tenant) -> bool:
    return any(i["kind"] == "shopify" for i in _load(t)["items"])


def due(item: dict, at: float) -> bool:
    if not item["last_sync"]:
        return True
    last = datetime.strptime(item["last_sync"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    return at - last >= SYNC_EVERY_SECONDS


def run_due(on_tables=None, at: float | None = None):
    at = at or time.time()
    for t in all_tenants():
        for item in _load(t)["items"]:
            if due(item, at):
                sync(t, item["id"], on_tables)


def start_scheduler(on_tables, every_seconds: int = 600) -> threading.Event:
    stop = threading.Event()

    def loop():
        while not stop.wait(every_seconds):
            try:
                run_due(on_tables)
            except Exception:
                log.error("connection sync tick failed", exc_info=True)

    threading.Thread(target=loop, name="data-sync", daemon=True).start()
    return stop


def _mac(raw: bytes) -> str:
    key = hashlib.sha256(b"oauth-state" + master_keys()[0]).digest()
    return hmac.new(key, raw, hashlib.sha256).hexdigest()[:40]


def sign_state(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps({**payload, "exp": int(time.time()) + STATE_MAX_AGE}).encode())
    return raw.decode() + "." + _mac(raw)


def read_state(state: str) -> dict | None:
    raw, _, mac = state.partition(".")
    if not raw or not hmac.compare_digest(_mac(raw.encode()), mac):
        return None
    payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    return payload if payload.get("exp", 0) > time.time() else None


def google_auth_url(state: str, redirect_uri: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": os.getenv("GOOGLE_CLIENT_ID"), "redirect_uri": redirect_uri, "response_type": "code",
        "scope": " ".join(sources.GOOGLE_SCOPES), "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true", "state": state})


def google_exchange(code: str, redirect_uri: str, http=None) -> tuple[str, str]:
    r = (http or sources.new_http()).post(sources.GOOGLE_TOKEN_URL, timeout=sources.TIMEOUT, data={
        "code": code, "client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise SourceError("Google did not accept the sign-in. Try connecting again.")
    tokens = r.json()
    if not tokens.get("refresh_token"):
        raise SourceError("Google gave no long-term access. Remove the app at myaccount.google.com/permissions and connect again.")
    claims = tokens["id_token"].split(".")[1]
    email = json.loads(base64.urlsafe_b64decode(claims + "=" * (-len(claims) % 4)))["email"].lower()
    return email, tokens["refresh_token"]
