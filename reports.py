import html
import json
import logging
import re
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent import ask, build_agent, start_sandbox
from tenants import TENANTS_DIR, Memory, Tenant

log = logging.getLogger("reports")

DEFAULT_SETTINGS = {"enabled": False, "weekday": 0, "hour": 8, "timezone": "Asia/Kolkata", "recipients": []}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TONES = {"red", "green", "ink"}
GOAL_STATUS = {"on_track": "On track", "at_risk": "At risk", "off_track": "Off track", "unknown": "Not enough data"}
REPORT_NAME = re.compile(r"\d{4}-\d{2}-\d{2}")
_running: set[str] = set()
_running_lock = threading.Lock()

REPORT_PROMPT = """Prepare this company's weekly review.
Take the most recent complete week (Monday to Sunday) in the data as "this week" and compare it with the
previous 4 weeks. Find what changed, why, and what to do. Check every company goal you can measure.
Work in few, large code runs. When done, reply with ONLY one JSON object in a ```json block, no other text:
{
  "period": "this week's dates, e.g. 13 to 19 Oct 2026",
  "headline": "one sentence: the most important thing that happened",
  "figure": "the single most important number, short, e.g. -12%",
  "figure_tone": "red if bad, green if good, ink if neutral",
  "figure_note": "what the figure measures",
  "figure_source": "where it came from, e.g. orders.csv, 11,238 rows",
  "findings": [{"tone": "red|green|ink", "text": "one finding, plain words", "source": "file and rows/columns used"}],
  "goals": [{"goal": "the goal as written", "status": "on_track|at_risk|off_track|unknown", "note": "short reason with the number"}],
  "actions": ["a concrete action for this week"]
}
Rank findings most urgent first, at most 5. At most 3 actions. Every number must come from code you ran."""



def load_settings(tenant: Tenant) -> dict:
    path = tenant.dir / "settings.json"
    stored = json.loads(path.read_text(encoding="utf-8")).get("report", {}) if path.exists() else {}
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(tenant: Tenant, report: dict) -> dict:
    clean = {
        "enabled": bool(report.get("enabled")),
        "weekday": int(report.get("weekday", 0)),
        "hour": int(report.get("hour", 8)),
        "timezone": str(report.get("timezone", "Asia/Kolkata")).strip(),
        "recipients": [str(e).strip() for e in report.get("recipients", []) if str(e).strip()],
    }
    if not 0 <= clean["weekday"] <= 6 or not 0 <= clean["hour"] <= 23:
        raise ValueError("Pick a valid day and hour")
    try:
        ZoneInfo(clean["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"Unknown timezone: {clean['timezone']}") from None
    bad = [e for e in clean["recipients"] if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) or len(e) > 254]
    if bad or len(clean["recipients"]) > 20:
        raise ValueError("Enter up to 20 valid email addresses" + (f": {bad[0]} is not valid" if bad else ""))
    path = tenant.dir / "settings.json"
    all_settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    all_settings["report"] = clean
    path.write_text(json.dumps(all_settings, indent=2), encoding="utf-8")
    return clean


def is_due(settings: dict, now_utc: datetime, last_week: str | None) -> tuple[bool, str]:
    local = now_utc.astimezone(ZoneInfo(settings["timezone"]))
    iso = local.isocalendar()
    week = f"{iso.year}-W{iso.week:02d}"
    reached = (local.weekday(), local.hour) >= (settings["weekday"], settings["hour"])
    return settings["enabled"] and reached and last_week != week, week



def parse_report(answer: str) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", answer, re.S) or re.search(r"(\{.*\})", answer, re.S)
    try:
        data = json.loads(match.group(1)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return {"headline": "This week's review", "findings": [{"tone": "ink", "text": answer.strip()[:2000], "source": ""}],
                "goals": [], "actions": [], "parsed": False}

    def text(v, limit=400):
        return str(v or "").strip()[:limit]

    return {
        "period": text(data.get("period"), 80),
        "headline": text(data.get("headline"), 300) or "This week's review",
        "figure": text(data.get("figure"), 16),
        "figure_tone": data.get("figure_tone") if data.get("figure_tone") in TONES else "ink",
        "figure_note": text(data.get("figure_note"), 120),
        "figure_source": text(data.get("figure_source"), 120),
        "findings": [{"tone": f.get("tone") if f.get("tone") in TONES else "ink", "text": text(f.get("text")),
                      "source": text(f.get("source"), 120)}
                     for f in data.get("findings", [])[:5] if isinstance(f, dict) and f.get("text")],
        "goals": [{"goal": text(g.get("goal"), 200), "status": g.get("status") if g.get("status") in GOAL_STATUS else "unknown",
                   "note": text(g.get("note"), 200)}
                  for g in data.get("goals", [])[:8] if isinstance(g, dict) and g.get("goal")],
        "actions": [text(a, 300) for a in data.get("actions", [])[:3] if text(a)],
        "parsed": True,
    }


INK = {"red": "#d7262e", "green": "#128a4b", "ink": "#1b1e23"}
STATUS_COLOR = {"on_track": "#128a4b", "at_risk": "#b26a00", "off_track": "#d7262e", "unknown": "#646a74"}


def render_email(report: dict, company: str) -> str:
    e = html.escape
    font = "font-family:Arial,Helvetica,sans-serif;"
    rows = []
    if report.get("figure"):
        rows.append(f"""<tr><td style="padding:8px 28px 4px;">
  <span style="display:inline-block;padding:8px 22px;border:3px solid {INK[report['figure_tone']]};border-radius:50%;
    {font}font-size:44px;font-weight:bold;color:{INK[report['figure_tone']]};">{e(report['figure'])}</span>
  <div style="{font}font-size:15px;font-weight:bold;color:#1b1e23;margin-top:10px;">{e(report.get('figure_note', ''))}</div>
  <div style="{font}font-size:12px;color:#474d57;margin-top:4px;">{e(report.get('figure_source', ''))}</div></td></tr>""")
    if report["findings"]:
        items = "".join(f"""<tr><td valign="top" style="padding:6px 12px 6px 0;{font}font-size:15px;font-weight:bold;color:{INK[f['tone']]};">{i}</td>
  <td style="padding:6px 0;{font}font-size:15px;line-height:1.45;color:#1b1e23;">{e(f['text'])}
  {f'<div style="font-size:12px;color:#646a74;margin-top:2px;">{e(f["source"])}</div>' if f['source'] else ''}</td></tr>"""
                        for i, f in enumerate(report["findings"], 1))
        rows.append(f"""<tr><td style="padding:18px 28px 0;"><div style="{font}font-size:17px;font-weight:bold;color:#1b1e23;margin-bottom:6px;">What changed</div>
  <table role="presentation" cellpadding="0" cellspacing="0">{items}</table></td></tr>""")
    if report["goals"]:
        items = "".join(f"""<tr><td style="padding:6px 0;{font}font-size:14px;color:#1b1e23;">{e(g['goal'])}
  <div style="font-size:12px;color:#474d57;">{e(g['note'])}</div></td>
  <td valign="top" align="right" style="padding:6px 0 6px 12px;{font}font-size:13px;font-weight:bold;color:{STATUS_COLOR[g['status']]};white-space:nowrap;">{GOAL_STATUS[g['status']]}</td></tr>"""
                        for g in report["goals"])
        rows.append(f"""<tr><td style="padding:18px 28px 0;"><div style="{font}font-size:17px;font-weight:bold;color:#1b1e23;margin-bottom:6px;">Your goals</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{items}</table></td></tr>""")
    if report["actions"]:
        items = "".join(f'<li style="margin:4px 0;">{e(a)}</li>' for a in report["actions"])
        rows.append(f"""<tr><td style="padding:18px 28px 0;"><div style="{font}font-size:17px;font-weight:bold;color:#1b1e23;">Do this week</div>
  <ol style="{font}font-size:15px;line-height:1.5;color:#1b1e23;padding-left:20px;margin:6px 0 0;">{items}</ol></td></tr>""")

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{e(company)} weekly review</title></head>
<body style="margin:0;padding:0;background:#e4e8eb;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#e4e8eb;"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#c9ced3;border-radius:14px;">
<tr><td style="padding:10px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fcfdfd;border-radius:8px;">
<tr><td style="padding:26px 28px 8px;{font}">
  <div style="font-size:13px;font-weight:bold;color:#474d57;">Analyst Buddy weekly review for {e(company)}{f' &middot; {e(report["period"])}' if report.get('period') else ''}</div>
  <div style="font-size:24px;line-height:1.25;font-weight:bold;color:#1b1e23;margin-top:8px;">{e(report['headline'])}</div></td></tr>
{''.join(rows)}
<tr><td style="padding:22px 28px 24px;{font}font-size:12px;color:#646a74;">Every number above was computed by running code on your company's data. Reply in Analyst Buddy to ask why.</td></tr>
</table></td></tr></table></td></tr></table></body></html>"""



def generate(tenant: Tenant, index) -> dict:
    with _running_lock:
        if tenant.id in _running:
            raise RuntimeError("A report for this company is already being created")
        _running.add(tenant.id)
    sandbox = None
    try:
        memory = Memory(tenant, index)
        sandbox, _, overview = start_sandbox(tenant)
        agent = build_agent(sandbox, tenant, memory, {"overview": overview})
        _, answer, calls = ask(agent, sandbox, memory, [], REPORT_PROMPT)
        report = parse_report(answer or "The analyst could not finish this week's review.")
        report.update(calls=calls, created=datetime.now().astimezone().isoformat(timespec="minutes"))
        name = time.strftime("%Y-%m-%d")
        folder = tenant.dir / "reports"
        folder.mkdir(exist_ok=True)
        (folder / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        (folder / f"{name}.html").write_text(render_email(report, tenant.knowledge().get("company") or tenant.id), encoding="utf-8")
        deliver(tenant, folder / f"{name}.html")
        return {"name": name, **report}
    finally:
        if sandbox is not None:
            try:
                sandbox.kill()
            except Exception:
                pass
        with _running_lock:
            _running.discard(tenant.id)


def deliver(tenant: Tenant, html_path) -> None:
    log.info("weekly report saved for %s: %s", tenant.id, html_path)


def list_reports(tenant: Tenant) -> list[dict]:
    folder = tenant.dir / "reports"
    out = []
    for f in sorted(folder.glob("*.json"), reverse=True) if folder.exists() else []:
        if REPORT_NAME.fullmatch(f.stem):
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({"name": f.stem, "headline": data.get("headline", ""), "period": data.get("period", ""),
                        "figure": data.get("figure", ""), "figure_tone": data.get("figure_tone", "ink")})
    return out


def report_html(tenant: Tenant, name: str) -> str:
    if not REPORT_NAME.fullmatch(name):
        raise FileNotFoundError(name)
    return (tenant.dir / "reports" / f"{name}.html").read_text(encoding="utf-8")



def run_due(index_fn, now_utc: datetime | None = None) -> list[str]:
    now_utc = now_utc or datetime.now().astimezone()
    done = []
    for folder in sorted(p for p in TENANTS_DIR.iterdir() if p.is_dir()) if TENANTS_DIR.exists() else []:
        try:
            tenant = Tenant(folder.name)
        except ValueError:
            continue
        settings = load_settings(tenant)
        state_file = tenant.dir / "reports" / "state.json"
        last = json.loads(state_file.read_text(encoding="utf-8")).get("last_week") if state_file.exists() else None
        due, week = is_due(settings, now_utc, last)
        if not due:
            continue
        try:
            generate(tenant, index_fn())
            done.append(tenant.id)
        except Exception:
            log.error("scheduled report failed for %s", tenant.id, exc_info=True)
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text(json.dumps({"last_week": week}), encoding="utf-8")
    return done


def start_scheduler(index_fn, every_seconds: int = 300) -> threading.Event:
    stop = threading.Event()

    def loop():
        while not stop.wait(every_seconds):
            try:
                run_due(index_fn)
            except Exception:
                log.error("report scheduler tick failed", exc_info=True)

    threading.Thread(target=loop, name="weekly-reports", daemon=True).start()
    return stop
