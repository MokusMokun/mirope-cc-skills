#!/usr/bin/env python3
"""
Aggregate Claude Code usage from ~/.claude/projects/**/*.jsonl into a single-page
HTML dashboard. Designed to be invoked by the `cc-usage-stats` skill.

Usage:
  analyze.py --out DIR [--end YYYY-MM-DD] [--days N]

Defaults:
  --end     today (local time)
  --days    60
  --out     required

Outputs (into --out):
  data.json    aggregated metrics (also inlined into index.html)
  index.html   self-contained dashboard (works on file://, no server needed)

Schema notes (discovered by inspecting jsonl):
  Each line is one event record. Relevant types:
    - "user"      : user message (incl. tool_results wrapped as user)
    - "assistant" : assistant message; usage in message.usage; one tool_use per row
    - others (system / attachment / file-history-snapshot / agent-name / ...) ignored
  Same logical assistant message often appears as N consecutive rows, one per
  tool_use, all sharing the SAME message.id and SAME usage payload.
  -> Dedup usage by message.id; count tool_use per row.

Skill calls: tool_use name == "Skill", input.skill carries the skill id.
Agent calls: tool_use name == "Task"  / "Agent", input.subagent_type carries the type.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
TEMPLATE_PATH = Path(__file__).parent / "index.html.template"

# USD per 1M tokens. Prices last verified 2026-05-13.
# When refreshing, also bump the date above and the const below — the dashboard
# surfaces it in the cost-table footnote.
#
# Sources:
#   Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
#   OpenAI:    https://openai.com/api/pricing/
#   DeepSeek:  https://api-docs.deepseek.com/quick_start/pricing/
#
# Anthropic cache multipliers (standard 5m tier): cache_create = 1.25 * input,
#   cache_read = 0.10 * input. We assume CC's cache_creation tokens are 5m writes.
# OpenAI: cached_input is a single tier; we map it to "cache_read". OpenAI
#   does not bill a separate "cache write" line — writes are billed at the
#   normal input rate, so cache_create here uses the input price.
# DeepSeek V4 Pro is in a 75% promo until 2026-05-31; we use list price
#   ($1.74/$3.48 input/output) so totals don't drop after the promo ends.
#   Cache hit price = 0.10 * input per DeepSeek's 2026-04-26 adjustment.
PRICING_DATE = "2026-05-13"
PRICING_USD_PER_MTOK = {
    # --- Anthropic ---
    "claude-opus-4-7":          {"input": 5.00, "output": 25.00, "cache_create": 6.25, "cache_read": 0.50},
    "claude-opus-4-6":          {"input": 5.00, "output": 25.00, "cache_create": 6.25, "cache_read": 0.50},
    "claude-opus-4-6-thinking": {"input": 5.00, "output": 25.00, "cache_create": 6.25, "cache_read": 0.50},
    "claude-sonnet-4-6":        {"input": 3.00, "output": 15.00, "cache_create": 3.75, "cache_read": 0.30},
    "claude-haiku-4-5":         {"input": 1.00, "output":  5.00, "cache_create": 1.25, "cache_read": 0.10},
    # --- OpenAI (GPT-5.5 short context, <272K) ---
    "gpt-5.5-2026-04-24":       {"input": 5.00, "output": 30.00, "cache_create": 5.00, "cache_read": 0.50},
    "gpt-5.5":                  {"input": 5.00, "output": 30.00, "cache_create": 5.00, "cache_read": 0.50},
    # --- DeepSeek (V4 Pro list price; ignore active promo so cost stays stable) ---
    "deepseek-v4-pro":          {"input": 1.74, "output":  3.48, "cache_create": 1.74, "cache_read": 0.174},
}

# Window: inclusive both ends, in local time (CST = UTC+8).
LOCAL_TZ = timezone(timedelta(hours=8))


def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # ISO 8601 with trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(LOCAL_TZ)
    except Exception:
        return None


def iter_records():
    for path in PROJECTS_DIR.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path,
                    help="Output directory (created if missing); receives data.json + index.html")
    ap.add_argument("--end", default=None,
                    help="End date YYYY-MM-DD (inclusive). Default: today (local).")
    ap.add_argument("--days", type=int, default=30,
                    help="Window length in days (default 30). Window is [end-days+1, end].")
    args = ap.parse_args()

    if args.end:
        END_DATE = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    else:
        now = datetime.now(LOCAL_TZ)
        END_DATE = datetime(now.year, now.month, now.day, tzinfo=LOCAL_TZ)
    START_DATE = END_DATE - timedelta(days=args.days - 1)

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    OUT_PATH = out_dir / "data.json"
    HTML_OUT = out_dir / "index.html"

    # Daily counters
    day_user = Counter()         # user msg / day
    day_assistant_msgs = Counter()  # unique assistant message.id / day
    day_sessions = defaultdict(set)  # date -> set(sessionId)

    # Hour x weekday heatmap (weekday 0=Mon)
    heatmap = Counter()  # (weekday, hour) -> assistant_msgs

    # Tokens
    day_tokens = defaultdict(lambda: Counter())  # date -> Counter(input/output/cache_read/cache_create)
    model_tokens = defaultdict(lambda: Counter())  # model -> Counter(input/output/cache_read/cache_create)

    # Tools / skills / agents
    tools = Counter()
    skills = Counter()
    agents = Counter()

    seen_msg_ids: set[str] = set()
    total_records = 0
    in_window_records = 0

    for r in iter_records():
        total_records += 1
        ts = parse_ts(r.get("timestamp"))
        if ts is None:
            continue
        if not (START_DATE <= ts <= END_DATE + timedelta(days=1)):
            continue
        in_window_records += 1
        date_str = ts.strftime("%Y-%m-%d")
        rtype = r.get("type")
        sid = r.get("sessionId")
        if sid:
            day_sessions[date_str].add(sid)

        if rtype == "user":
            # Skip synthetic / meta-only entries: we still count them as user activity
            # (the real human inputs and tool_results both register as user; that's
            # ok for "activity" granularity).
            day_user[date_str] += 1
            continue

        if rtype != "assistant":
            continue

        m = r.get("message") or {}
        mid = m.get("id")
        usage = m.get("usage") or {}
        model = m.get("model") or "unknown"

        # Dedup usage by message.id
        new_msg = mid not in seen_msg_ids if mid else True
        if mid:
            seen_msg_ids.add(mid)
        if new_msg:
            day_assistant_msgs[date_str] += 1
            heatmap[(ts.weekday(), ts.hour)] += 1
            in_t = int(usage.get("input_tokens") or 0)
            out_t = int(usage.get("output_tokens") or 0)
            cc_t = int(usage.get("cache_creation_input_tokens") or 0)
            cr_t = int(usage.get("cache_read_input_tokens") or 0)
            day_tokens[date_str]["input"] += in_t
            day_tokens[date_str]["output"] += out_t
            day_tokens[date_str]["cache_create"] += cc_t
            day_tokens[date_str]["cache_read"] += cr_t
            model_tokens[model]["input"] += in_t
            model_tokens[model]["output"] += out_t
            model_tokens[model]["cache_create"] += cc_t
            model_tokens[model]["cache_read"] += cr_t
            model_tokens[model]["messages"] += 1

        # Tool use: every row is counted (each row holds at most one tool_use)
        content = m.get("content")
        if isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") != "tool_use":
                    continue
                name = c.get("name") or "?"
                inp = c.get("input") or {}
                tools[name] += 1
                if name == "Skill":
                    skill = inp.get("skill") or inp.get("name") or "?"
                    skills[skill] += 1
                elif name in ("Task", "Agent"):
                    sub = inp.get("subagent_type") or "general-purpose"
                    agents[sub] += 1

    # Build dense daily series across the window
    days = []
    d = START_DATE
    while d <= END_DATE:
        days.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    daily_series = []
    for ds in days:
        toks = day_tokens.get(ds, Counter())
        daily_series.append({
            "date": ds,
            "user_msgs": day_user.get(ds, 0),
            "assistant_msgs": day_assistant_msgs.get(ds, 0),
            "sessions": len(day_sessions.get(ds, ())),
            "tokens": {
                "input": toks.get("input", 0),
                "output": toks.get("output", 0),
                "cache_create": toks.get("cache_create", 0),
                "cache_read": toks.get("cache_read", 0),
            },
        })

    # Heatmap matrix [7 weekdays][24 hours]
    heatmap_matrix = [[heatmap.get((w, h), 0) for h in range(24)] for w in range(7)]

    # Models with per-component cost rollup
    model_summary = []
    for model, c in sorted(model_tokens.items(), key=lambda kv: -sum(kv[1].values())):
        p = PRICING_USD_PER_MTOK.get(model)
        cost = None
        if p:
            cost = {
                "input":        c.get("input", 0)        / 1e6 * p["input"],
                "output":       c.get("output", 0)       / 1e6 * p["output"],
                "cache_create": c.get("cache_create", 0) / 1e6 * p["cache_create"],
                "cache_read":   c.get("cache_read", 0)   / 1e6 * p["cache_read"],
            }
            cost["total"] = sum(cost.values())
        model_summary.append({
            "model": model,
            "messages": c.get("messages", 0),
            "input": c.get("input", 0),
            "output": c.get("output", 0),
            "cache_create": c.get("cache_create", 0),
            "cache_read": c.get("cache_read", 0),
            "total": c.get("input", 0) + c.get("output", 0) + c.get("cache_create", 0) + c.get("cache_read", 0),
            "price_per_mtok": p,            # null if unknown model
            "cost_usd": cost,                # null if unpriced
            "priced": p is not None,
        })

    # Totals
    totals = {
        "input": sum(c.get("input", 0) for c in day_tokens.values()),
        "output": sum(c.get("output", 0) for c in day_tokens.values()),
        "cache_create": sum(c.get("cache_create", 0) for c in day_tokens.values()),
        "cache_read": sum(c.get("cache_read", 0) for c in day_tokens.values()),
        "assistant_msgs": sum(day_assistant_msgs.values()),
        "user_msgs": sum(day_user.values()),
        "sessions": len({s for sset in day_sessions.values() for s in sset}),
        "active_days": sum(1 for ds in days if day_assistant_msgs.get(ds, 0) > 0),
        "tool_calls": sum(tools.values()),
        "skill_calls": sum(skills.values()),
        "agent_calls": sum(agents.values()),
        "total_records": total_records,
        "records_in_window": in_window_records,
    }
    cache_in = totals["cache_read"] + totals["input"]
    totals["cache_hit_rate"] = (totals["cache_read"] / cache_in) if cache_in else 0.0

    # Aggregate cost over all priced models
    cost_total = {"input": 0.0, "output": 0.0, "cache_create": 0.0, "cache_read": 0.0, "total": 0.0}
    cost_unpriced_tokens = 0
    for m in model_summary:
        if m["cost_usd"]:
            for k in ("input", "output", "cache_create", "cache_read", "total"):
                cost_total[k] += m["cost_usd"][k]
        else:
            cost_unpriced_tokens += m["total"]
    totals["cost_usd"] = cost_total
    totals["cost_unpriced_tokens"] = cost_unpriced_tokens

    out = {
        "window": {
            "start": START_DATE.strftime("%Y-%m-%d"),
            "end": END_DATE.strftime("%Y-%m-%d"),
            "tz": "Asia/Shanghai (UTC+8)",
        },
        "pricing_date": PRICING_DATE,
        "totals": totals,
        "daily": daily_series,
        "heatmap": heatmap_matrix,
        "models": model_summary,
        "tools": [{"name": k, "count": v} for k, v in tools.most_common()],
        "skills": [{"name": k, "count": v} for k, v in skills.most_common()],
        "agents": [{"name": k, "count": v} for k, v in agents.most_common()],
    }

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Render template -> out_dir/index.html with the data inlined as a
    # <script id="cc-data" type="application/json"> block. Inlining matters
    # because browsers block fetch() on file:// URLs, so a sibling data.json
    # alone wouldn't load when the user double-clicks the html.
    if not TEMPLATE_PATH.exists():
        sys.exit(f"template missing: {TEMPLATE_PATH}")
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    compact = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    compact = compact.replace("</script", "<\\/script")  # don't break host tag
    new_html, n = re.subn(
        r'(<script id="cc-data" type="application/json">)(.*?)(</script>)',
        lambda m: m.group(1) + compact + m.group(3),
        html,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        sys.exit("template missing <script id='cc-data'> placeholder")
    HTML_OUT.write_text(new_html, encoding="utf-8")

    print(f"wrote {OUT_PATH}")
    print(f"wrote {HTML_OUT}")
    print(f"  window: {START_DATE.date()} → {END_DATE.date()}")
    print(f"  records scanned: {total_records:,}  in window: {in_window_records:,}")
    print(f"  active days: {totals['active_days']}/{len(days)}")
    print(f"  assistant msgs: {totals['assistant_msgs']:,}  sessions: {totals['sessions']}")
    print(f"  tokens (B): in={totals['input']/1e9:.2f} out={totals['output']/1e9:.2f} "
          f"cc={totals['cache_create']/1e9:.2f} cr={totals['cache_read']/1e9:.2f}")
    print(f"  cache hit rate: {totals['cache_hit_rate']*100:.1f}%")
    print(f"  tools: {totals['tool_calls']:,}  skills: {totals['skill_calls']:,}  agents: {totals['agent_calls']:,}")
    print(f"  cost (USD): ${cost_total['total']:,.2f}  "
          f"(in=${cost_total['input']:.2f} out=${cost_total['output']:.2f} "
          f"cc=${cost_total['cache_create']:.2f} cr=${cost_total['cache_read']:.2f})")
    print(f"  pricing date: {PRICING_DATE}")


if __name__ == "__main__":
    main()
