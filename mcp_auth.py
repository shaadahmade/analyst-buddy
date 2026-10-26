import base64
import hashlib
import secrets
import threading
import time
from urllib.parse import urlencode, urlparse

import requests

import sources
from sources import SourceError

CALLBACK = "/oauth/mcp-callback"
CLIENT_DOC = "/oauth/mcp-client.json"
PENDING_TTL = 600
PENDING: dict[str, dict] = {}
_lock = threading.Lock()


def get_json(url: str, method: str = "GET", **kw) -> tuple[int, dict]:
    sources.mcp_url(url)
    try:
        r = requests.request(method, url, timeout=20, allow_redirects=False, headers={"Accept": "application/json"}, **kw)
    except requests.RequestException:
        raise SourceError("Could not reach the sign-in server.") from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body if isinstance(body, dict) else {}


def well_known(base: str, name: str) -> list[str]:
    u = urlparse(base)
    origin, path = f"{u.scheme}://{u.netloc}", u.path.rstrip("/")
    return [f"{origin}/.well-known/{name}{path}", f"{origin}/.well-known/{name}"] if path else [f"{origin}/.well-known/{name}"]


def resource_metadata(url: str) -> dict | None:
    for candidate in well_known(url, "oauth-protected-resource"):
        status, body = get_json(candidate)
        if status == 200 and body.get("authorization_servers"):
            return body
    return None


def discover(url: str) -> dict:
    url = sources.mcp_url(url)
    prm = resource_metadata(url)
    issuer = prm["authorization_servers"][0] if prm else f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    meta = None
    for candidate in well_known(issuer, "oauth-authorization-server") + well_known(issuer, "openid-configuration"):
        status, body = get_json(candidate)
        if status == 200 and body.get("authorization_endpoint") and body.get("token_endpoint"):
            meta = body
            break
    if meta is None:
        raise SourceError("This MCP server does not offer sign-in.")
    if "S256" not in meta.get("code_challenge_methods_supported", ["S256"]):
        raise SourceError("This MCP server's sign-in is not secure enough (no PKCE).")
    for key in ("authorization_endpoint", "token_endpoint"):
        sources.mcp_url(meta[key])
    return {"resource": (prm or {}).get("resource") or url, "authorization_endpoint": meta["authorization_endpoint"],
            "token_endpoint": meta["token_endpoint"], "registration_endpoint": meta.get("registration_endpoint"),
            "cimd": bool(meta.get("client_id_metadata_document_supported"))}


def client_document(base: str) -> dict:
    return {"client_id": base + CLIENT_DOC, "client_name": "Analyst Buddy", "client_uri": base,
            "redirect_uris": [base + CALLBACK], "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none"}


def client_for(meta: dict, base: str) -> tuple[str, str]:
    if meta["cimd"] and base.startswith("https://"):
        return base + CLIENT_DOC, ""
    if meta["registration_endpoint"]:
        doc = client_document(base)
        doc.pop("client_id")
        status, body = get_json(meta["registration_endpoint"], "POST", json=doc)
        if status in (200, 201) and body.get("client_id"):
            return body["client_id"], body.get("client_secret", "")
        raise SourceError("The MCP server refused to register Analyst Buddy for sign-in.")
    if meta["cimd"]:
        raise SourceError("Sign-in needs Analyst Buddy on a public https address. Open it through its public link and try again.")
    raise SourceError("This MCP server only allows sign-in for apps it already knows.")


def start(tenant_id: str, user: str, url: str, base: str) -> tuple[str, str]:
    meta = discover(url)
    client_id, client_secret = client_for(meta, base)
    grant, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    with _lock:
        for key in [k for k, v in PENDING.items() if v["created"] < time.time() - PENDING_TTL]:
            PENDING.pop(key)
        PENDING[grant] = {"tenant": tenant_id, "user": user, "url": sources.mcp_url(url), "verifier": verifier,
                          "client_id": client_id, "client_secret": client_secret, "token_endpoint": meta["token_endpoint"],
                          "resource": meta["resource"], "redirect_uri": base + CALLBACK, "created": time.time(),
                          "status": "waiting", "message": "", "secret": None}
    query = {"response_type": "code", "client_id": client_id, "redirect_uri": base + CALLBACK, "state": grant,
             "code_challenge": challenge, "code_challenge_method": "S256", "resource": meta["resource"]}
    sep = "&" if "?" in meta["authorization_endpoint"] else "?"
    return grant, meta["authorization_endpoint"] + sep + urlencode(query)


def token_request(secret: dict, form: dict) -> dict:
    form = {**form, "client_id": secret["client_id"], "resource": secret["resource"]}
    if secret.get("client_secret"):
        form["client_secret"] = secret["client_secret"]
    status, body = get_json(secret["token_endpoint"], "POST", data=form)
    if status != 200 or not body.get("access_token"):
        raise SourceError("The sign-in was refused or has expired. Disconnect this source and sign in again.")
    return {**secret, "token": body["access_token"], "refresh_token": body.get("refresh_token") or secret.get("refresh_token", ""),
            "expires_at": time.time() + int(body.get("expires_in") or 3600)}


def finish(state: str, code: str, error: str) -> dict | None:
    with _lock:
        pending = PENDING.get(state)
    if pending is None or pending["status"] != "waiting" or pending["created"] < time.time() - PENDING_TTL:
        return None
    try:
        if error or not code:
            raise SourceError("The sign-in was cancelled.")
        base = {k: pending[k] for k in ("client_id", "client_secret", "token_endpoint", "resource")}
        secret = token_request(base, {"grant_type": "authorization_code", "code": code,
                                      "redirect_uri": pending["redirect_uri"], "code_verifier": pending["verifier"]})
        pending.update(status="ready", secret=secret)
    except SourceError as exc:
        pending.update(status="error", message=str(exc))
    return pending


def lookup(grant: str, tenant_id: str, user: str) -> dict:
    with _lock:
        pending = PENDING.get(grant)
    if not pending or pending["tenant"] != tenant_id or pending["user"] != user or pending["created"] < time.time() - PENDING_TTL:
        raise SourceError("That sign-in expired. Sign in again.")
    return pending


def token_for(grant: str, tenant_id: str, user: str, url: str) -> str:
    pending = lookup(grant, tenant_id, user)
    if pending["status"] != "ready" or pending["url"] != sources.mcp_url(url):
        raise SourceError("Finish signing in first.")
    return pending["secret"]["token"]


def take(grant: str, tenant_id: str, user: str, url: str) -> dict:
    token_for(grant, tenant_id, user, url)
    with _lock:
        return PENDING.pop(grant)["secret"]


def refresh_if_needed(secret: dict) -> bool:
    if not secret.get("refresh_token") or secret.get("expires_at", 0) > time.time() + 120:
        return False
    secret.update(token_request(secret, {"grant_type": "refresh_token", "refresh_token": secret["refresh_token"]}))
    return True
