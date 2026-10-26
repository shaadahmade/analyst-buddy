import ipaddress
import json
import os
import re
import socket
import time
from datetime import date, timedelta
from urllib.parse import quote, urlparse

import pandas as pd
import requests

LOOKBACK_DAYS = 365
MAX_ROWS = 500_000
TIMEOUT = 60
SHOPIFY_API_VERSION = "2025-10"
SHOP_DOMAIN = re.compile(r"[a-z0-9][a-z0-9-]*\.myshopify\.com")
SHEET_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})")
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
                 "https://www.googleapis.com/auth/analytics.readonly", "openid", "email"]


class SourceError(Exception):
    pass


def call(http, method, url, who, **kw):
    for attempt in range(5):
        r = http.request(method, url, timeout=TIMEOUT, **kw)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(30, float(r.headers.get("Retry-After") or 2 ** attempt)))
            continue
        if r.status_code in (401, 403):
            raise SourceError(f"{who} refused the request ({r.status_code}). Check the key and its read permissions.")
        if r.status_code == 404:
            raise SourceError(f"{who} could not find that (404). Check the store, sheet or property id.")
        if r.status_code >= 400:
            raise SourceError(f"{who} rejected the request ({r.status_code}): {r.text[:200]}")
        return r.json()
    raise SourceError(f"{who} is busy or rate limiting us. Try again in a few minutes.")


def table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows[:MAX_ROWS])


def shop_domain(raw: str) -> str:
    shop = raw.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    if shop and "." not in shop:
        shop += ".myshopify.com"
    if not SHOP_DOMAIN.fullmatch(shop):
        raise SourceError("Enter the store's myshopify.com domain, e.g. yourstore.myshopify.com")
    return shop


def shopify_token(cfg, secret, http, cache: dict) -> str:
    if cache.get("token") and cache.get("expires", 0) > time.time() + 120:
        return cache["token"]
    page = call(http, "POST", f"https://{cfg['shop']}/admin/oauth/access_token", "Shopify",
                data={"grant_type": "client_credentials", "client_id": secret["client_id"],
                      "client_secret": secret["client_secret"]})
    if not page.get("access_token"):
        raise SourceError("Shopify did not issue a token. Check the client ID, the secret and that the app is installed.")
    cache.update(token=page["access_token"], expires=time.time() + int(page.get("expires_in") or 86399))
    return cache["token"]


def shopify_query(http, cfg, token, query, variables=None):
    for _ in range(6):
        page = call(http, "POST", f"https://{cfg['shop']}/admin/api/{SHOPIFY_API_VERSION}/graphql.json", "Shopify",
                    headers={"X-Shopify-Access-Token": token}, json={"query": query, "variables": variables or {}})
        errors = page.get("errors") or []
        if any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors):
            time.sleep(2)
            continue
        if errors:
            raise SourceError("Shopify: " + "; ".join(e.get("message", "query failed") for e in errors)[:300]
                              + ". Give the app the read_orders and read_products scopes.")
        return page["data"]
    raise SourceError("Shopify kept rate limiting us. Try again in a few minutes.")


ORDERS = """query($after: String, $q: String) { orders(first: 250, after: $after, query: $q, sortKey: CREATED_AT) {
  pageInfo { hasNextPage endCursor }
  nodes { id name createdAt cancelledAt displayFinancialStatus displayFulfillmentStatus currencyCode
    totalPriceSet { shopMoney { amount } } subtotalPriceSet { shopMoney { amount } }
    totalDiscountsSet { shopMoney { amount } } totalRefundedSet { shopMoney { amount } }
    lineItems(first: 50) { nodes { sku title quantity variantTitle originalUnitPriceSet { shopMoney { amount } }
      product { id } } } } } }"""
PRODUCTS = """query($ids: [ID!]!) { nodes(ids: $ids) {
  ... on Product { id title productType vendor status createdAt totalInventory } } }"""


GQL_WRITE = re.compile(r"\b(mutation|subscription)\b", re.I)


def shopify_live(cfg, secret, http, cache, query: str, variables: dict | None = None) -> dict:
    text = re.sub(r"#[^\n]*", "", query or "").strip()
    if not text or len(text) > 6000:
        raise SourceError("Send one GraphQL query of at most 6000 characters.")
    if GQL_WRITE.search(text) or not (text.startswith("{") or text.lower().startswith("query")):
        raise SourceError("Only read queries are allowed. Mutations and subscriptions are refused.")
    return shopify_query(http, cfg, shopify_token(cfg, secret, http, cache), text, variables)


def shopify_test(cfg, secret, http):
    token = shopify_token(cfg, secret, http, {})
    shop = shopify_query(http, cfg, token, "{ shop { name currencyCode } }")["shop"]
    return f"{shop['name']} ({shop['currencyCode']})"


def shopify_all(http, cfg, secret, cache, query, key, variables):
    rows, after = [], None
    while len(rows) < MAX_ROWS:
        data = shopify_query(http, cfg, shopify_token(cfg, secret, http, cache), query, {**variables, "after": after})[key]
        rows += data["nodes"]
        if not data["pageInfo"]["hasNextPage"]:
            return rows
        after = data["pageInfo"]["endCursor"]
    return rows


def shopify_fetch(cfg, secret, http, cache=None):
    cache = {} if cache is None else cache
    amount = lambda m: float(((m or {}).get("shopMoney") or {}).get("amount") or 0)
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    orders, items, product_ids = [], [], set()
    for o in shopify_all(http, cfg, secret, cache, ORDERS, "orders", {"q": f"created_at:>={since}"}):
        oid = o["id"].rsplit("/", 1)[-1]
        orders.append({"id": oid, "name": o["name"], "created": o["createdAt"], "cancelled": o.get("cancelledAt"),
                       "financial_status": o.get("displayFinancialStatus"),
                       "fulfillment_status": o.get("displayFulfillmentStatus"), "currency": o.get("currencyCode"),
                       "total": amount(o.get("totalPriceSet")), "subtotal": amount(o.get("subtotalPriceSet")),
                       "discounts": amount(o.get("totalDiscountsSet")), "refunded": amount(o.get("totalRefundedSet"))})
        items += [{"order_id": oid, "created": o["createdAt"], "sku": li.get("sku"), "title": li.get("title"),
                   "variant": li.get("variantTitle"), "quantity": li.get("quantity"),
                   "unit_price": amount(li.get("originalUnitPriceSet")),
                   "product_id": ((li.get("product") or {}).get("id") or "").rsplit("/", 1)[-1] or None}
                  for li in o["lineItems"]["nodes"]]
        product_ids |= {li["product"]["id"] for li in o["lineItems"]["nodes"] if (li.get("product") or {}).get("id")}
    ids, products = sorted(product_ids), []
    for start in range(0, len(ids), 250):
        found = shopify_query(http, cfg, shopify_token(cfg, secret, http, cache), PRODUCTS, {"ids": ids[start:start + 250]})["nodes"]
        products += [{"id": p["id"].rsplit("/", 1)[-1], "title": p["title"], "type": p.get("productType"),
                      "vendor": p.get("vendor"), "status": p.get("status"), "created": p.get("createdAt"),
                      "inventory": p.get("totalInventory")} for p in found if p]
    return {"shopify_orders": table(orders), "shopify_order_items": table(items), "shopify_products": table(products)}


def google_access(secret, http) -> str:
    r = http.post(GOOGLE_TOKEN_URL, timeout=TIMEOUT, data={
        "client_id": os.getenv("GOOGLE_CLIENT_ID"), "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "refresh_token": secret["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise SourceError("Google access was revoked or has expired. Connect Google again.")
    return r.json()["access_token"]


def sheet_id(raw: str) -> str:
    match = SHEET_ID.search(raw)
    if not match:
        raise SourceError("Paste the full Google Sheets link (https://docs.google.com/spreadsheets/d/...)")
    return match.group(1)


def sheets_test(cfg, secret, http):
    token = google_access(secret, http)
    meta = call(http, "GET", f"https://sheets.googleapis.com/v4/spreadsheets/{cfg['sheet_id']}", "Google Sheets",
                headers={"Authorization": f"Bearer {token}"}, params={"fields": "properties.title,sheets.properties.title"})
    return f"{meta['properties']['title']} ({len(meta['sheets'])} tab{'s' if len(meta['sheets']) != 1 else ''})"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:30] or "sheet"


def sheets_fetch(cfg, secret, http):
    auth = {"Authorization": f"Bearer {google_access(secret, http)}"}
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{cfg['sheet_id']}"
    meta = call(http, "GET", base, "Google Sheets", headers=auth,
                params={"fields": "properties.title,sheets.properties.title"})
    tables = {}
    for tab in [s["properties"]["title"] for s in meta["sheets"]][:20]:
        a1 = "'" + tab.replace("'", "''") + "'"
        values = call(http, "GET", f"{base}/values/{quote(a1, safe='')}", "Google Sheets",
                      headers=auth, params={"valueRenderOption": "UNFORMATTED_VALUE",
                                            "dateTimeRenderOption": "FORMATTED_STRING"}).get("values", [])
        if len(values) < 2:
            continue
        header = [str(h).strip() or f"column_{i + 1}" for i, h in enumerate(values[0])]
        width = len(header)
        rows = [(r + [None] * width)[:width] for r in values[1:MAX_ROWS + 1]]
        tables[f"sheet_{slug(meta['properties']['title'])}_{slug(tab)}"] = pd.DataFrame(rows, columns=header)
    if not tables:
        raise SourceError("The sheet has no tab with a header row and data.")
    return tables


def ga4_properties(secret, http) -> list[dict]:
    token = google_access(secret, http)
    page = call(http, "GET", "https://analyticsadmin.googleapis.com/v1beta/accountSummaries", "Google Analytics",
                headers={"Authorization": f"Bearer {token}"}, params={"pageSize": 200})
    return [{"id": p["property"].split("/")[-1], "name": f"{a.get('displayName', '')} / {p.get('displayName', '')}"}
            for a in page.get("accountSummaries", []) for p in a.get("propertySummaries", [])]


def ga4_test(cfg, secret, http):
    names = {p["id"]: p["name"] for p in ga4_properties(secret, http)}
    if cfg["property_id"] not in names:
        raise SourceError("This Google account cannot see that Analytics property.")
    return names[cfg["property_id"]]


GA4_DIMENSIONS = ["date", "sessionDefaultChannelGroup", "deviceCategory", "country"]
GA4_METRICS = ["sessions", "totalUsers", "newUsers", "keyEvents", "totalRevenue", "engagementRate"]


def ga4_fetch(cfg, secret, http):
    auth = {"Authorization": f"Bearer {google_access(secret, http)}"}
    rows, offset = [], 0
    while len(rows) < MAX_ROWS:
        page = call(http, "POST", f"https://analyticsdata.googleapis.com/v1beta/properties/{cfg['property_id']}:runReport",
                    "Google Analytics", headers=auth, json={
                        "dateRanges": [{"startDate": f"{LOOKBACK_DAYS}daysAgo", "endDate": "today"}],
                        "dimensions": [{"name": d} for d in GA4_DIMENSIONS],
                        "metrics": [{"name": m} for m in GA4_METRICS], "limit": 100000, "offset": offset})
        batch = page.get("rows", [])
        rows += [dict(zip(GA4_DIMENSIONS + GA4_METRICS, [v["value"] for v in r["dimensionValues"]]
                          + [float(v["value"]) for v in r["metricValues"]])) for r in batch]
        offset += len(batch)
        if not batch or offset >= page.get("rowCount", 0):
            break
    df = table(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
    return {"ga4_traffic": df}


WRITE_WORDS = re.compile(r"(^|[_\-.\s])(create|update|delete|remove|send|post|write|insert|upsert|set|add|archive|cancel|"
                         r"pay|refund|transfer|invite|upload|publish|move|rename|merge|close|reopen|assign|run|execute|"
                         r"edit|patch|put|drop|reset|approve|reject|submit|charge|import|sync)([_\-.\s]|$)", re.I)
MAX_MCP_TOOLS = 10
ALLOW_PRIVATE_MCP = False


class NeedsSignIn(SourceError):
    pass


def mcp_url(raw: str) -> str:
    url = raw.strip()
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password:
        raise SourceError("Enter the MCP server's full https:// URL.")
    if not ALLOW_PRIVATE_MCP:
        if u.scheme != "https":
            raise SourceError("The MCP server must use https.")
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(u.hostname, u.port or 443)}
        except socket.gaierror:
            raise SourceError("That MCP server address could not be found.") from None
        for addr in addresses:
            ip = ipaddress.ip_address(addr.split("%")[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise SourceError("That address points to a private network, which is not allowed.")
    return url


def tool_safety(tool) -> str:
    hints = tool.annotations
    if hints is not None and (hints.read_only_hint is False or hints.destructive_hint):
        return "marked by the server as changing data"
    if hints is not None and hints.read_only_hint is True:
        return ""
    if WRITE_WORDS.search(tool.name):
        return "its name suggests it changes data"
    return ""


async def _mcp(url: str, token: str, work):
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                init = await session.initialize()
                return await work(session, init)


def mcp_preflight(url: str, token: str):
    hello = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "analyst-buddy", "version": "1"}}}
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
               **({"Authorization": f"Bearer {token}"} if token else {})}
    try:
        r = requests.post(url, json=hello, headers=headers, timeout=20, allow_redirects=False, stream=True)
        r.close()
    except requests.RequestException:
        raise SourceError("Could not reach the MCP server. Check the URL.") from None
    if 300 <= r.status_code < 400:
        raise SourceError("The MCP server redirected to another address. Paste its final URL.")
    if r.status_code == 401 and not token:
        raise NeedsSignIn("This MCP server needs you to sign in.")
    if r.status_code in (401, 403):
        raise SourceError("The MCP server refused access. Check the token, or sign in again.")
    if r.status_code in (404, 405):
        raise SourceError("There is no MCP endpoint at that URL.")
    if r.status_code >= 500:
        raise SourceError(f"The MCP server had an error ({r.status_code}). Try again later.")


def run_mcp(url: str, token: str, work):
    import anyio

    mcp_preflight(url, token)
    try:
        return anyio.run(_mcp, url, token, work)
    except SourceError:
        raise
    except BaseException as exc:
        stack, inner = [exc], None
        while stack and inner is None:
            e = stack.pop()
            inner = e if isinstance(e, SourceError) else None
            stack.extend(getattr(e, "exceptions", []))
        if inner is not None:
            raise inner from None
        text = " ".join(str(e) for e in getattr(exc, "exceptions", [exc]))
        if "401" in text or "403" in text:
            raise SourceError("The MCP server refused access. Check the token, or sign in again.") from None
        raise SourceError(f"Could not talk to the MCP server ({type(exc).__name__}). Check the URL; it must speak MCP over Streamable HTTP.") from None


def mcp_inspect(url: str, token: str = "") -> dict:
    async def work(session, init):
        listed = await session.list_tools()
        tools = []
        for t in listed.tools[:100]:
            schema = t.input_schema or {}
            tools.append({"name": t.name, "description": (t.description or "")[:300], "blocked": tool_safety(t),
                          "required": list(schema.get("required", [])), "properties": list((schema.get("properties") or {}).keys())[:20]})
        return {"server": init.server_info.name or "MCP server", "tools": tools}

    return run_mcp(mcp_url(url), token, work)


def to_frame(payload) -> pd.DataFrame:
    if isinstance(payload, dict):
        lists = [v for v in payload.values() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if lists:
            payload = max(lists, key=len)
        else:
            return pd.json_normalize(payload, max_level=2)
    if isinstance(payload, list):
        if payload and all(isinstance(x, dict) for x in payload):
            return pd.json_normalize(payload[:MAX_ROWS], max_level=2)
        return pd.DataFrame({"value": [json.dumps(x) if isinstance(x, (dict, list)) else x for x in payload[:MAX_ROWS]]})
    return pd.DataFrame({"value": [payload]})


def tool_payload(result):
    if result.structured_content:
        return result.structured_content
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except ValueError:
        return [{"text": line} for line in joined.splitlines() if line.strip()]


def clean_mcp_tools(raw) -> list[dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_MCP_TOOLS:
        raise SourceError(f"Pick 1 to {MAX_MCP_TOOLS} tools.")
    tools = []
    for item in raw:
        name = str(item.get("name", "")) if isinstance(item, dict) else ""
        args = item.get("args") or {} if isinstance(item, dict) else {}
        if not name or not isinstance(args, dict) or len(json.dumps(args)) > 4000:
            raise SourceError("Each tool needs a name and its inputs as a JSON object.")
        tools.append({"name": name, "args": args})
    return tools


def mcp_test(cfg, secret, http):
    found = mcp_inspect(cfg["url"], secret.get("token", ""))
    by_name = {t["name"]: t for t in found["tools"]}
    for pick in cfg["tools"]:
        tool = by_name.get(pick["name"])
        if not tool:
            raise SourceError(f"The server has no tool named {pick['name']!r}.")
        if tool["blocked"]:
            raise SourceError(f"{pick['name']} is not allowed: {tool['blocked']}. Only read-only tools can be imported.")
        missing = [r for r in tool["required"] if r not in pick["args"]]
        if missing:
            raise SourceError(f"{pick['name']} needs: {', '.join(missing)}.")
    return f"{found['server']} ({len(cfg['tools'])} tool{'s' if len(cfg['tools']) != 1 else ''})"


def mcp_fetch(cfg, secret, http):
    mcp_test(cfg, secret, http)
    host = slug(urlparse(cfg["url"]).hostname or "server")

    async def work(session, init):
        frames, failed = {}, []
        for pick in cfg["tools"]:
            name = f"mcp_{host}_{slug(pick['name'])}"
            result = await session.call_tool(pick["name"], pick["args"])
            if result.is_error:
                failed.append(f"{pick['name']}: " + " ".join(getattr(c, "text", "") for c in result.content)[:200])
                frames[name] = pd.DataFrame()
            else:
                frames[name] = to_frame(tool_payload(result))
        if len(failed) == len(cfg["tools"]):
            raise SourceError("The MCP tool failed. " + " | ".join(failed))
        return frames

    return run_mcp(mcp_url(cfg["url"]), secret.get("token", ""), work)


CONNECTORS = {
    "shopify": {"name": "Shopify", "secrets": ["client_id", "client_secret"], "config": ["shop"], "test": shopify_test,
                "fetch": shopify_fetch},
    "sheets": {"name": "Google Sheets", "secrets": [], "config": ["sheet_id"], "google": True, "test": sheets_test,
               "fetch": sheets_fetch},
    "ga4": {"name": "Google Analytics 4", "secrets": [], "config": ["property_id"], "google": True, "test": ga4_test,
            "fetch": ga4_fetch},
    "mcp": {"name": "MCP server", "secrets": ["token"], "optional_secrets": True, "config": ["url", "tools"],
            "test": mcp_test, "fetch": mcp_fetch},
}


def new_http() -> requests.Session:
    http = requests.Session()
    http.headers["User-Agent"] = "AnalystBuddy/1.0"
    return http
