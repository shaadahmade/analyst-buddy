import time
from urllib.parse import unquote

import sources
from sources import SourceError


class Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self.body, self.headers, self.text = status, body or {}, headers or {}, str(body)

    def json(self):
        return self.body


class FakeHTTP:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for (m, part), handler in self.routes.items():
            if m == method and part in url:
                out = handler(url, kw)
                return out if isinstance(out, Resp) else Resp(body=out)
        raise AssertionError(f"unexpected call {method} {url}")

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


sources.time.sleep = lambda s: None

tries = {"n": 0}


def flaky(url, kw):
    tries["n"] += 1
    return Resp(429, headers={"Retry-After": "0"}) if tries["n"] == 1 else {"ok": True}


assert sources.call(FakeHTTP({("GET", "/x"): flaky}), "GET", "https://api/x", "Shopify") == {"ok": True} and tries["n"] == 2
for status, words in [(401, "refused"), (404, "could not find"), (400, "rejected")]:
    try:
        sources.call(FakeHTTP({("GET", "/x"): lambda u, k, s=status: Resp(s)}), "GET", "https://api/x", "Shopify")
        raise AssertionError(f"{status} must fail")
    except SourceError as exc:
        assert words in str(exc), exc
try:
    sources.call(FakeHTTP({("GET", "/x"): lambda u, k: Resp(503)}), "GET", "https://api/x", "Shopify")
    raise AssertionError("a source that stays down must fail clearly")
except SourceError as exc:
    assert "busy" in str(exc)

assert sources.shop_domain("https://My-Store.myshopify.com/admin") == "my-store.myshopify.com"
assert sources.shop_domain("my-store") == "my-store.myshopify.com"
for bad in ["", "evil.com", "a.myshopify.com.evil.com"]:
    try:
        sources.shop_domain(bad)
        raise AssertionError(f"accepted shop {bad!r}")
    except SourceError:
        pass

tokens = []
pages = {"orders": 0}


def shopify_token(url, kw):
    assert kw["data"]["grant_type"] == "client_credentials" and kw["data"]["client_secret"] == "shpss_x"
    tokens.append(1)
    return {"access_token": f"tok{len(tokens)}", "expires_in": 86399}


def shopify_graphql(url, kw):
    assert kw["headers"]["X-Shopify-Access-Token"].startswith("tok")
    q = kw["json"]["query"]
    if "shop {" in q:
        return {"data": {"shop": {"name": "Haad Store", "currencyCode": "INR"}}}
    if "orders(" in q:
        pages["orders"] += 1
        if pages["orders"] == 1:
            return {"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
        second = kw["json"]["variables"]["after"] == "c1"
        node = {"id": f"gid://shopify/Order/{2 if second else 1}", "name": "#1001", "createdAt": "2026-10-01T10:00:00Z",
                "currencyCode": "INR", "totalPriceSet": {"shopMoney": {"amount": "999.00"}},
                "lineItems": {"nodes": [{"sku": "TEE", "title": "Tee", "quantity": 2,
                                         "originalUnitPriceSet": {"shopMoney": {"amount": "499.50"}},
                                         "product": {"id": "gid://shopify/Product/7"}}]}}
        return {"data": {"orders": {"nodes": [node], "pageInfo": {"hasNextPage": not second, "endCursor": "c1"}}}}
    assert kw["json"]["variables"]["ids"] == ["gid://shopify/Product/7"], "only products that appear in orders are fetched"
    return {"data": {"nodes": [{"id": "gid://shopify/Product/7", "title": "Tee"}, None]}}


shop_http = FakeHTTP({("POST", "/admin/oauth/access_token"): shopify_token, ("POST", "/graphql.json"): shopify_graphql})
cfg, secret = {"shop": "haad.myshopify.com"}, {"client_id": "cid", "client_secret": "shpss_x"}
assert sources.shopify_test(cfg, secret, shop_http) == "Haad Store (INR)"
cache = {}
frames = sources.shopify_fetch(cfg, secret, shop_http, cache)
assert list(frames["shopify_orders"]["id"]) == ["1", "2"] and frames["shopify_orders"]["total"].iloc[0] == 999.0
assert frames["shopify_order_items"]["unit_price"].iloc[0] == 499.5 and frames["shopify_order_items"]["product_id"].iloc[0] == "7"
assert list(frames["shopify_products"]["id"]) == ["7"], "deleted products come back as null and are skipped"
assert len(tokens) == 2, "one token for the test and one reused for the whole sync"
sources.shopify_fetch(cfg, secret, shop_http, cache)
assert len(tokens) == 2, "a token that is still valid must be reused"
cache["expires"] = time.time() + 30
sources.shopify_fetch(cfg, secret, shop_http, cache)
assert len(tokens) == 3, "a token about to expire must be replaced before calling Shopify"

for bad in ["mutation { productDelete(input: {id: 1}) { deletedProductId } }", "query q { a } mutation m { b }",
            "subscription { x }", "", "# only a comment", "x" * 7000, "{ a }\nMUTATION { b }"]:
    try:
        sources.shopify_live(cfg, secret, shop_http, {}, bad)
        raise AssertionError(f"must refuse: {bad[:40]}")
    except SourceError:
        pass
assert sources.shopify_live(cfg, secret, shop_http, {}, "# today\n{ shop { name currencyCode } }") == {"shop": {"name": "Haad Store", "currencyCode": "INR"}}

assert sources.sheet_id("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit#gid=0") == "1AbCdEfGhIjKlMnOpQrStUvWxYz012345"
ranges = []


def sheet_values(url, kw):
    tab = unquote(url.rsplit("/values/", 1)[1])
    ranges.append(tab)
    if tab == "'Empty'":
        return {"values": [["only header"]]}
    return {"values": [["Region", "Revenue", ""], ["North", 3381], ["South", 1902, "note"]]}


google = FakeHTTP({("POST", "oauth2.googleapis.com/token"): lambda u, k: {"access_token": "ya29"} if k["data"]["refresh_token"] == "r1" else Resp(400),
                   ("GET", "/values/"): sheet_values,
                   ("GET", "sheets.googleapis.com/v4/spreadsheets/"): lambda u, k: {
                       "properties": {"title": "Sales 2026"},
                       "sheets": [{"properties": {"title": "Q3 bob's"}}, {"properties": {"title": "Empty"}}]}})
frames = sources.sheets_fetch({"sheet_id": "x" * 25}, {"refresh_token": "r1"}, google)
df = frames["sheet_sales_2026_q3_bob_s"]
assert list(df.columns) == ["Region", "Revenue", "column_3"] and df["Revenue"].tolist() == [3381, 1902] and len(frames) == 1
assert ranges[0] == "'Q3 bob''s'", ranges
assert sources.sheets_test({"sheet_id": "x" * 25}, {"refresh_token": "r1"}, google) == "Sales 2026 (2 tabs)"
try:
    sources.sheets_fetch({"sheet_id": "x" * 25}, {"refresh_token": "revoked"}, google)
    raise AssertionError("a revoked Google token must fail clearly")
except SourceError as exc:
    assert "Connect Google again" in str(exc)

offsets = []


def ga4_report(url, kw):
    offsets.append(kw["json"]["offset"])
    row = {"dimensionValues": [{"value": "20261001"}, {"value": "Organic Search"}, {"value": "mobile"}, {"value": "India"}],
           "metricValues": [{"value": "120"}, {"value": "100"}, {"value": "60"}, {"value": "3"}, {"value": "4500.5"}, {"value": "0.61"}]}
    return {"rows": [row, row], "rowCount": 3} if kw["json"]["offset"] == 0 else {"rows": [row], "rowCount": 3}


ga = FakeHTTP({("POST", "oauth2.googleapis.com/token"): lambda u, k: {"access_token": "ya29"},
               ("POST", ":runReport"): ga4_report,
               ("GET", "accountSummaries"): lambda u, k: {"accountSummaries": [
                   {"displayName": "Haad", "propertySummaries": [{"property": "properties/42", "displayName": "Shop site"}]}]}})
df = sources.ga4_fetch({"property_id": "42"}, {"refresh_token": "r"}, ga)["ga4_traffic"]
assert len(df) == 3 and offsets == [0, 2] and str(df["date"].iloc[0]) == "2026-10-01" and df["totalRevenue"].iloc[0] == 4500.5
assert sources.ga4_properties({"refresh_token": "r"}, ga) == [{"id": "42", "name": "Haad / Shop site"}]
assert sources.ga4_test({"property_id": "42"}, {"refresh_token": "r"}, ga) == "Haad / Shop site"
print("source checks passed")
