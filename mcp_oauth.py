import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import mcp_server

CLIENTS_FILE = Path(__file__).parent / "oauth_clients.json"
REQUEST_TTL = 600
CODE_TTL = 120
SCOPES = {"mcp:read": "read", "mcp:full": "full"}
_lock = threading.Lock()
REQUESTS: dict[str, dict] = {}
CODES: dict[str, dict] = {}


class OAuthError(Exception):
    def __init__(self, error: str, description: str):
        super().__init__(description)
        self.error, self.description = error, description


def _clients() -> dict:
    return json.loads(CLIENTS_FILE.read_text(encoding="utf-8")) if CLIENTS_FILE.exists() else {}


def valid_redirect(uri: str) -> bool:
    u = urlparse(uri)
    local = u.hostname in ("localhost", "127.0.0.1")
    return bool(u.hostname) and not u.fragment and (u.scheme == "https" or (u.scheme == "http" and local))


def register(body: dict) -> dict:
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not 1 <= len(uris) <= 10 or not all(isinstance(u, str) and valid_redirect(u) for u in uris):
        raise OAuthError("invalid_redirect_uri", "Give 1 to 10 https redirect URIs (http only for localhost).")
    client = {"client_id": "abc_" + secrets.token_urlsafe(18), "client_name": str(body.get("client_name") or "MCP client")[:100],
              "redirect_uris": uris, "client_id_issued_at": int(time.time()), "token_endpoint_auth_method": "none",
              "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}
    with _lock:
        clients = _clients()
        if len(clients) >= 1000:
            raise OAuthError("invalid_client_metadata", "Too many registered clients.")
        clients[client["client_id"]] = client
        CLIENTS_FILE.write_text(json.dumps(clients, indent=2), encoding="utf-8")
    return client


def with_query(uri: str, **params) -> str:
    return uri + ("&" if "?" in uri else "?") + urlencode({k: v for k, v in params.items() if v is not None})


def start(params: dict) -> str:
    client = _clients().get(params.get("client_id", ""))
    if not client:
        raise OAuthError("invalid_client", "Unknown client. Register first.")
    redirect = params.get("redirect_uri") or (client["redirect_uris"][0] if len(client["redirect_uris"]) == 1 else "")
    if redirect not in client["redirect_uris"]:
        raise OAuthError("invalid_request", "redirect_uri does not match the registered ones.")
    if params.get("response_type") != "code" or params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
        raise OAuthError("invalid_request", "Use response_type=code with a PKCE S256 code_challenge.")
    asked = (params.get("scope") or "").split()
    access = "full" if "mcp:full" in asked else "read"
    rid = secrets.token_urlsafe(18)
    with _lock:
        now = time.time()
        for k in [k for k, r in REQUESTS.items() if r["exp"] < now]:
            del REQUESTS[k]
        REQUESTS[rid] = {"client_id": client["client_id"], "client_name": client["client_name"], "redirect_uri": redirect,
                         "state": params.get("state"), "challenge": params["code_challenge"], "access": access, "exp": now + REQUEST_TTL}
    return rid


def describe(rid: str) -> dict | None:
    r = REQUESTS.get(rid)
    if not r or r["exp"] < time.time():
        return None
    return {"client_name": r["client_name"], "redirect_host": urlparse(r["redirect_uri"]).hostname, "access": r["access"]}


def decide(rid: str, allow: bool, tenant_id: str = "", user: str = "", access: str = "read") -> str | None:
    with _lock:
        r = REQUESTS.pop(rid, None)
    if not r or r["exp"] < time.time():
        return None
    if not allow:
        return with_query(r["redirect_uri"], error="access_denied", state=r["state"])
    code = secrets.token_urlsafe(32)
    with _lock:
        CODES[hashlib.sha256(code.encode()).hexdigest()] = {
            "client_id": r["client_id"], "client_name": r["client_name"], "redirect_uri": r["redirect_uri"],
            "challenge": r["challenge"], "t": tenant_id, "u": user, "access": "full" if access == "full" else "read",
            "exp": time.time() + CODE_TTL}
    return with_query(r["redirect_uri"], code=code, state=r["state"])


def pkce_ok(verifier: str, challenge: str) -> bool:
    if not 43 <= len(verifier) <= 128:
        return False
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return hmac.compare_digest(digest, challenge)


def token(form: dict) -> dict:
    grant = form.get("grant_type")
    if grant == "authorization_code":
        with _lock:
            c = CODES.pop(hashlib.sha256(form.get("code", "").encode()).hexdigest(), None)
        if not c or c["exp"] < time.time():
            raise OAuthError("invalid_grant", "The code is unknown, used or expired.")
        if form.get("client_id") != c["client_id"] or form.get("redirect_uri", c["redirect_uri"]) != c["redirect_uri"]:
            raise OAuthError("invalid_grant", "The code was issued to a different client or redirect URI.")
        if not pkce_ok(form.get("code_verifier", ""), c["challenge"]):
            raise OAuthError("invalid_grant", "PKCE verification failed.")
        return mcp_server.issue_grant(c["t"], c["u"], c["access"], c["client_name"])
    if grant == "refresh_token":
        issued = mcp_server.use_refresh_token(form.get("refresh_token", ""))
        if not issued:
            raise OAuthError("invalid_grant", "The refresh token is unknown, revoked or expired.")
        return issued
    raise OAuthError("unsupported_grant_type", "Use authorization_code or refresh_token.")


def metadata(base: str) -> dict:
    return {"issuer": base, "authorization_endpoint": f"{base}/oauth/authorize", "token_endpoint": f"{base}/oauth/token",
            "registration_endpoint": f"{base}/oauth/register", "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"], "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"], "scopes_supported": list(SCOPES)}


def resource_metadata(base: str) -> dict:
    return {"resource": f"{base}/mcp", "authorization_servers": [base], "bearer_methods_supported": ["header"],
            "scopes_supported": list(SCOPES), "resource_name": "Analyst Buddy"}
