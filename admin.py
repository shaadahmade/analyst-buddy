import json
import logging
import os
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta

from tenants import all_tenants, load_accounts

DAYS = 14
LOG_LIMIT = 150
HIDDEN_DETAIL = {"question", "note", "answer"}
_metrics_lock = threading.Lock()
log = logging.getLogger("admin")


def is_admin(email: str) -> bool:
    admins = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}
    return bool(email) and email.strip().lower() in admins


def record(tenant, **entry):
    line = json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **entry}, ensure_ascii=False)
    try:
        with _metrics_lock, (tenant.dir / "metrics.jsonl").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        log.warning("could not record metrics tenant=%s", tenant.id, exc_info=True)


def read_jsonl(path, since: str = "") -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("at", "") >= since:
            rows.append(row)
    return rows


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1)


def rate(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def stats(rows: list[dict]) -> dict:
    answered = [r for r in rows if r.get("status") == "done"]
    grounded = [r["numbers_grounded"] for r in answered if r.get("numbers_grounded") is not None]
    tools = Counter()
    for r in rows:
        tools.update(r.get("tools", {}))
    return {"questions": len(rows), "answered": len(answered), "answer_rate": rate(len(answered), len(rows)),
            "stopped": sum(r.get("status") == "stopped" for r in rows),
            "timeouts": sum(r.get("status") == "timeout" for r in rows),
            "errors": sum(r.get("status") == "error" for r in rows),
            "p50_s": percentile([r["seconds"] for r in answered], 0.5),
            "p95_s": percentile([r["seconds"] for r in answered], 0.95),
            "avg_steps": round(sum(r.get("steps", 0) for r in answered) / len(answered), 1) if answered else None,
            "tool_error_rate": rate(sum(bool(r.get("tool_errors")) for r in rows), len(rows)),
            "numbers_grounded": round(sum(grounded) / len(grounded), 3) if grounded else None,
            "placeholder_leaks": sum(r.get("placeholder_leak", 0) for r in rows),
            "web_searches": tools.get("web_research", 0),
            "web_blocked": sum(r.get("web_blocked", 0) for r in rows),
            "web_learned": sum(r.get("web_learned", 0) for r in rows),
            "team_share": rate(sum(r.get("mode") == "auto" for r in rows), len(rows)),
            "tools": dict(tools.most_common())}


def overview(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    since = (now - timedelta(days=DAYS - 1)).strftime("%Y-%m-%dT00:00:00")
    week = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
    tenants = [t for t in all_tenants() if not t.id.startswith(("test-", "eval-"))]
    every, workspaces, events, failures = [], [], [], []
    up = down = 0
    for t in tenants:
        rows = read_jsonl(t.dir / "metrics.jsonl", since)
        every += rows
        votes = read_jsonl(t.dir / "feedback.jsonl", week)
        up += sum(v.get("rating") == "up" for v in votes)
        down += sum(v.get("rating") == "down" for v in votes)
        recent = [r for r in rows if r["at"] >= week]
        audit = read_jsonl(t.dir / "audit.jsonl", since)
        name = t.name()
        workspaces.append({"id": t.id, "name": name, "members": len(t.users()), **stats(recent),
                           "last_active": max([r["at"] for r in rows + audit], default=None)})
        events += [{"at": e["at"], "workspace": name, "user": e.get("user"), "action": e.get("action"),
                    "detail": {k: v for k, v in e.items() if k not in HIDDEN_DETAIL | {"at", "user", "action"}}}
                   for e in audit]
        failures += [{"at": r["at"], "workspace": name, "status": r["status"], "message": r.get("message", ""),
                      "seconds": r.get("seconds")} for r in rows if r.get("status") in ("error", "timeout")]
    days = [(now.date() - timedelta(days=n)).isoformat() for n in range(DAYS - 1, -1, -1)]
    daily = {d: {"day": d, "questions": 0, "answered": 0, "failed": 0} for d in days}
    for r in every:
        day = daily.get(r["at"][:10])
        if day:
            day["questions"] += 1
            day["answered"] += r.get("status") == "done"
            day["failed"] += r.get("status") in ("error", "timeout")
    week_rows = [r for r in every if r["at"] >= week]
    workspaces.sort(key=lambda w: w["last_active"] or "", reverse=True)
    return {"generated": now.isoformat(timespec="seconds"), "accounts": len(load_accounts()),
            "workspaces_total": len(tenants), "members_total": sum(w["members"] for w in workspaces),
            "active_workspaces": sum(w["questions"] > 0 for w in workspaces),
            "week": {**stats(week_rows), "feedback_up": up, "feedback_down": down, "satisfaction": rate(up, up + down)},
            "daily": list(daily.values()), "workspaces": workspaces,
            "events": sorted(events, key=lambda e: e["at"], reverse=True)[:LOG_LIMIT],
            "failures": sorted(failures, key=lambda e: e["at"], reverse=True)[:30],
            "today": date.today().isoformat()}
