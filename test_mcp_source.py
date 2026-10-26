import json
import shutil
import socket
import threading
import time

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

import connections
import sources
from sources import SourceError
from tenants import TENANTS_DIR, Tenant

ORDERS = [{"id": 1, "region": "North", "total": 120.5, "customer": {"tier": "gold"}},
          {"id": 2, "region": "South", "total": 80.0, "customer": {"tier": "silver"}}]
TOOLS = [
    types.Tool(name="list_orders", description="List recent orders", input_schema={"type": "object", "properties": {}},
               annotations=types.ToolAnnotations(read_only_hint=True)),
    types.Tool(name="get_summary", description="Totals by region", input_schema={"type": "object", "properties": {}}),
    types.Tool(name="orders_by_region", description="Orders for one region",
               input_schema={"type": "object", "properties": {"region": {"type": "string"}}, "required": ["region"]}),
    types.Tool(name="delete_order", description="Delete an order", input_schema={"type": "object", "properties": {}}),
    types.Tool(name="wipe", description="Clean up", input_schema={"type": "object", "properties": {}},
               annotations=types.ToolAnnotations(destructive_hint=True)),
    types.Tool(name="broken", description="Always fails", input_schema={"type": "object", "properties": {}}),
]
called = []


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=TOOLS)


async def call_tool(ctx, params):
    called.append((params.name, params.arguments))
    text = lambda body: types.CallToolResult(content=[types.TextContent(type="text", text=body)])
    if params.name == "list_orders":
        return text(json.dumps(ORDERS))
    if params.name == "get_summary":
        return types.CallToolResult(content=[types.TextContent(type="text", text="summary")],
                                    structured_content={"generated": "today", "rows": [{"region": "North", "total": 120.5}, {"region": "South", "total": 80.0}]})
    if params.name == "orders_by_region":
        return text(json.dumps([o for o in ORDERS if o["region"] == params.arguments["region"]]))
    if params.name == "broken":
        return types.CallToolResult(content=[types.TextContent(type="text", text="database offline")], is_error=True)
    return text("should never be called")


srv = Server("Shop data", version="1", on_list_tools=list_tools, on_call_tool=call_tool)
inner = srv.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


async def app(scope, receive, send):
    if scope["type"] == "http":
        headers = dict(scope["headers"])
        if headers.get(b"authorization") != b"Bearer good-token":
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
    await inner(scope, receive, send)


sock = socket.socket()
sock.bind(("127.0.0.1", 0))
port = sock.getsockname()[1]
sock.close()
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    if server.started:
        break
    time.sleep(0.1)
URL = f"http://127.0.0.1:{port}/mcp"

tid = "test-mcpsrc"
connections.KEY_FILE = TENANTS_DIR / "test-mcpsrc.key"
connections._keys = None
(TENANTS_DIR / tid / "data").mkdir(parents=True, exist_ok=True)
(TENANTS_DIR / tid / "users.json").write_text(json.dumps({"boss@x.in": {"role": "owner", "scope": None}}))
t = Tenant(tid)
try:
    try:
        sources.mcp_inspect(URL, "good-token")
        raise AssertionError("a private address must be refused by default")
    except SourceError as exc:
        assert "https" in str(exc) or "private" in str(exc)
    sources.ALLOW_PRIVATE_MCP = True

    try:
        sources.mcp_inspect(URL, "")
        raise AssertionError("a missing token must fail")
    except sources.NeedsSignIn as exc:
        assert "sign in" in str(exc), exc
    try:
        sources.mcp_inspect(URL, "wrong-token")
        raise AssertionError("a wrong token must fail")
    except SourceError as exc:
        assert "refused access" in str(exc) and not isinstance(exc, sources.NeedsSignIn), exc

    found = sources.mcp_inspect(URL, "good-token")
    assert found["server"] == "Shop data"
    blocked = {x["name"]: x["blocked"] for x in found["tools"]}
    assert blocked["list_orders"] == "" and blocked["get_summary"] == "" and blocked["orders_by_region"] == ""
    assert "name" in blocked["delete_order"] and "server" in blocked["wipe"], blocked
    assert next(x for x in found["tools"] if x["name"] == "orders_by_region")["required"] == ["region"]
    assert called == [], "inspecting must not call any tool"

    for bad, why in [([{"name": "delete_order"}], "not allowed"), ([{"name": "wipe"}], "not allowed"),
                     ([{"name": "orders_by_region"}], "needs: region"), ([{"name": "nope"}], "no tool named")]:
        try:
            connections.create(t, "mcp", {"url": URL, "tools": bad}, {"token": "good-token"}, "boss@x.in")
            raise AssertionError(f"accepted {bad}")
        except SourceError as exc:
            assert why in str(exc), (why, exc)
    assert called == [], "a refused connection must not call tools"

    picks = [{"name": "list_orders"}, {"name": "get_summary"}, {"name": "orders_by_region", "args": {"region": "North"}}]
    item = connections.create(t, "mcp", {"url": URL, "tools": picks}, {"token": "good-token"}, "boss@x.in")
    assert item["label"] == "Shop data (3 tools)" and "good-token" not in (t.dir / "connections.json").read_text()
    out = connections.sync(t, item["id"])
    assert out["status"] == "ok", out
    host = "127_0_0_1"
    assert set(out["tables"]) == {f"mcp_{host}_list_orders.csv", f"mcp_{host}_get_summary.csv", f"mcp_{host}_orders_by_region.csv"}, out["tables"]
    orders = (t.data_dir / f"mcp_{host}_list_orders.csv").read_text()
    assert orders.splitlines()[0] == "id,region,total,customer.tier" and "gold" in orders, orders
    assert (t.data_dir / f"mcp_{host}_get_summary.csv").read_text().splitlines() == ["region,total", "North,120.5", "South,80.0"]
    assert "South" not in (t.data_dir / f"mcp_{host}_orders_by_region.csv").read_text()
    assert [c[0] for c in called] == ["list_orders", "get_summary", "orders_by_region"] and called[2][1] == {"region": "North"}
    assert "delete_order" not in [c[0] for c in called] and "wipe" not in [c[0] for c in called]
    assert t.knowledge()["data_notes"][-1]["source"] == "mcp"

    failing = connections.create(t, "mcp", {"url": URL, "tools": [{"name": "broken"}]}, {"token": "good-token"}, "boss@x.in")
    out = connections.sync(t, failing["id"])
    assert out["status"] == "error" and "database offline" in out["message"], out
finally:
    sources.ALLOW_PRIVATE_MCP = False
    server.should_exit = True
    shutil.rmtree(TENANTS_DIR / tid, ignore_errors=True)
    connections.KEY_FILE.unlink(missing_ok=True)

print("mcp source checks passed")
