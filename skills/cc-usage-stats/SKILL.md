---
name: cc-usage-stats
description: >
  Build a single-page HTML dashboard summarizing recent Claude Code usage:
  daily activity, time-of-day heatmap, token flow by model, USD cost rollup,
  and top tools / skills / agents. Reads ~/.claude/projects/**/*.jsonl and
  emits data.json + index.html into a chosen output directory.

  Use this skill whenever the user wants to: count or visualize CC usage,
  see how many tokens / sessions / messages over the last N days, get a USD
  cost estimate for CC activity, audit which tools / skills / agents get
  used most, or refresh a previously-generated CC usage report. Trigger
  phrases include "统计 CC 使用", "看看 token 用量", "CC 花了多少钱",
  "我最近 CC 都在做什么", "analyze claude code usage", "cc dashboard".
---

# Claude Code Usage Dashboard

Aggregates `~/.claude/projects/**/*.jsonl` into a self-contained HTML
dashboard. The dashboard works when double-clicked (data is inlined; no
local server required).

> **Note:** the dashboard UI is **Chinese-only** (KPI labels, chart titles,
> cost notes are all in 简体中文). The CLI / `data.json` / this SKILL.md
> remain English. PRs welcome for i18n.

## When to use

- User asks to summarize / visualize / count CC usage over a recent window
- User wants a USD cost estimate based on official Anthropic / OpenAI /
  DeepSeek pricing
- User wants to know which tools / skills / subagents they're using most

Do NOT use for: real-time monitoring, billing reconciliation against actual
invoices (this is an *estimate*), or analyzing other CLI tools.

## Quick reference

| Output file | Purpose |
|---|---|
| `<out>/data.json` | aggregated metrics; readable for ad-hoc queries |
| `<out>/index.html` | single-file dashboard; opens via file:// (data inlined) |

| Section in dashboard | What it shows |
|---|---|
| KPI strip | active days, sessions, msgs, tokens, **总费用 USD**, cache hit rate |
| 时间分布 | daily user/assistant bar + weekday × hour heatmap |
| Token 与费用 | hero stacked-area chart + model donut + USD cost table |
| 工具与技能 | top tools / skills (subagent_type) / agents bars |

## Run

```bash
# Default: window ends today, 30 days back, output under ./_cc-usage-report/
python3 ~/.claude/skills/cc-usage-stats/scripts/analyze.py \
  --out ./_cc-usage-report/$(date +%Y%m%d)/

# Custom window / explicit output
python3 ~/.claude/skills/cc-usage-stats/scripts/analyze.py \
  --out ./report/ --end 2026-05-13 --days 30
```

`--out` is required by the script (no default — caller must pass one). The
SKILL convention is `./_cc-usage-report/<END_YYYYMMDD>/`, where
`<END_YYYYMMDD>` is the **window's end date** (defaults to today, but if the
user passes `--end`, use that date — keeps the directory name aligned with
the data inside it). The directory is created if missing. Both `data.json`
and `index.html` are written into it. The HTML works offline via file://.

> **Python**: `python3` (3.9+). The script uses **only stdlib** — no `pip
> install` needed.

## Workflow checklist

When invoked, do these in order:

1. **Confirm window and output dir.** Default output:
   `./_cc-usage-report/<END_YYYYMMDD>/` (relative to the user's CWD), where
   `<END_YYYYMMDD>` is the window's *end* date (today if `--end` not
   specified). Default window: 30 days back from end. If the user
   specified either, honor that. State what you're about to do in one
   sentence; don't ask for permission unless ambiguous.

2. **Check pricing freshness.** Read `PRICING_DATE` from
   `scripts/analyze.py` and report it in one short line (e.g.
   "pricing date 2026-05-13, 2 days old — fresh"). Always say something —
   the user can't see the grep, and silently skipping looks like the step
   was forgotten. If `(today - PRICING_DATE) > 7 days`, refresh the
   `PRICING_USD_PER_MTOK` table from the official sources listed in the
   comment block above it (Anthropic / OpenAI / DeepSeek) by running web
   searches for current per-million-token rates (input / output / cached
   input / cache write), then bump `PRICING_DATE` to today.

3. **Run the script.** Single command. Treat any non-zero exit as a hard
   failure — investigate before proceeding. The script's stdout is itself
   the report (active days, sessions, tokens, cost) — keep it for step 5.

4. **Light verification (default).** Confirm `data.json` and `index.html`
   were written, and that the inlined JSON parses:
   ```bash
   python -c "import json,re; html=open('<out>/index.html').read(); \
     m=re.search(r'<script id=\"cc-data\"[^>]*>(.*?)</script>', html, re.S); \
     json.loads(m.group(1)); print('inlined data ok')"
   ```
   This catches the realistic failure modes (write failed, placeholder not
   substituted, JSON malformed) in <1s. **Do NOT spin up Playwright /
   webapp-testing by default** — installing/launching a browser takes
   minutes and the dashboard is a static single file. Only escalate to
   Playwright when (a) the user reports the page renders broken, or (b)
   you just edited `index.html.template` and want a real browser smoke
   test.

5. **Report.** Paste the script's stdout block verbatim plus the path to
   `index.html`. Don't re-format or reorganize the numbers — the stdout
   already has the right summary.

## Editing the template

`index.html.template` historically had hardcoded numbers tied to the
default window (e.g. "最近 60 天", "/ 61"). These now read from
`d.window` at render time. Before changing the default `--days` or
touching the template, grep for any remaining literal day-counts:

```bash
grep -nE '最近 [0-9]+ 天|/ [0-9]+' \
  ~/.claude/skills/cc-usage-stats/scripts/index.html.template
```

If anything matches, convert it to derive from `d.window` instead of
hardcoding.

## Refreshing the pricing table

Prices change. The `PRICING_USD_PER_MTOK` dict carries a comment with the
authoritative URL for each provider. To refresh:

1. Fetch the current pricing page for each provider.
2. Update the relevant entries (input / output / cache_create / cache_read).
3. Bump `PRICING_DATE` constant to today.
4. Re-run.

Notes on cache columns:
- **Anthropic**: `cache_create` = 5-minute write tier (1.25× input);
  `cache_read` = 0.10× input. Set the multipliers explicitly per-model;
  Sonnet & Haiku have lower base prices but the same multipliers.
- **OpenAI**: no separate "cache write" billing line — set
  `cache_create` = `input` price. `cache_read` = "cached input" price.
- **DeepSeek**: prefer the *list* price (not the active promo price), so
  totals stay stable when the promo expires.

## Troubleshooting

- **Charts blank, console shows CORS error**: you opened the HTML on a
  build that didn't inline data. Re-run the script — it always inlines.
- **`<synthetic>` model in the data**: these are CC's internal placeholder
  events; analyze.py already excludes them from the model donut and cost
  rollup but shows them in `data.json` for completeness.
- **Cost looks wrong by ~10×**: check whether you're double-counting
  `cache_create` as `input`. They are separate columns; `analyze.py`
  dedupes by `message.id` and reads each usage field once per logical
  assistant message.
- **Records skipped**: `analyze.py` reports `records scanned: N  in window: M`.
  Big delta = window too narrow or jsonl files outside `~/.claude/projects/`.

## Files

```
~/.claude/skills/cc-usage-stats/
├── SKILL.md
└── scripts/
    ├── analyze.py            # CLI; reads jsonl, writes data.json + index.html
    └── index.html.template   # ECharts dashboard with __DATA_PLACEHOLDER__
```

Both files are designed to be edited in place when you need to add a chart,
adjust pricing, or change the window default. Keep them in this directory —
`analyze.py` resolves the template via `Path(__file__).parent`.
