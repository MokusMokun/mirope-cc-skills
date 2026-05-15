---
name: repo-lint
description: |
  Multi-language lint check across an entire directory tree. Probes which lint
  tools are available, runs the ones it can, reports problems, and prints
  install commands for missing tools (never auto-installs). Default mode is
  report-only — does not auto-fix code.

  Use when the user asks to "lint the repo / lint this project / check the
  whole thing / run all linters". Covers: Python (ruff/black/isort/codespell),
  Shell (shellcheck + bash -n), JavaScript (node --check, prettier), Markdown
  (whitespace + broken relative links), spelling (codespell), and SKILL.md
  frontmatter validity if any are present.

  Do NOT use this skill when the user wants to lint only changed Python files
  in a commit or working tree — use the `lint-fix` skill for that. The two
  skills are complementary: `lint-fix` is git-range scoped + auto-fix,
  `repo-lint` is whole-tree + report-only + multi-language.
metadata:
  author: yuhao (MokusMokun)
  version: "0.1.0"
---

# repo-lint

Whole-tree, multi-language lint with explicit tool-availability probing.

## When to invoke

- "lint the whole repo" / "check all the code in this project"
- "run every linter you can"
- "audit code quality on this directory"
- After a batch of mixed-language changes, before committing or PR-ing

**Do NOT** invoke for:
- "lint my Python changes" / "lint this commit" → use [`lint-fix`](../../README.md) instead
- Single-file format requests → just run the formatter directly

## Workflow

The skill has three phases. The model SHOULD follow the order, but is free to
skip a phase if the previous output makes it unnecessary (e.g., skip Python
phase entirely if the repo has no `.py` files).

### Phase 1 — Probe

Run the bundled probe to see which tools are available and learn install
commands for missing ones:

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/probe.sh
```

Probe finds Python tools inside the user's venv automatically (it scans
`REPO_LINT_VENV`, `VIRTUAL_ENV`, and a list of common venv paths). If the user
has a non-standard venv, set `REPO_LINT_VENV=/path/to/venv` before invoking.

### Phase 2 — Run available linters

Per file type. **Skip silently** any tool the probe marked MISSING; surface
the missing-tool list at the end of the report along with install commands.
**Never auto-install** — the user decides whether to install.

| File type | Tool | Command |
|---|---|---|
| `*.py` | ruff | `ruff check <files>` (no `--fix` by default) |
| `*.py` | isort | `isort --check-only --diff --profile=black <files>` |
| `*.py` | black | `black --check --diff <files>` |
| `*.sh` `*.bash` | shellcheck | `shellcheck <files>` |
| `*.sh` `*.bash` | bash -n | `bash -n <file>` (built-in, always available) |
| `*.mjs` `*.js` | node --check | `node --check <file>` (always available if node is) |
| `*.mjs` `*.js` | prettier | `prettier --check <files>` |
| `*.md` | repo-lint built-in | `python3 ${CLAUDE_SKILL_DIR}/scripts/md-check.py <ROOT>` |
| `*.md` | markdownlint | `markdownlint <files>` (optional, often noisy) |
| all text | codespell | `codespell --skip='.git,*.png,*.jpg,*.svg,*.pdf,LICENSE,node_modules' <ROOT>` |

If the repo has `skills/*/SKILL.md` files (a CC skills monorepo pattern),
also validate frontmatter:
- YAML parses
- `name:` field exists and matches the parent directory name
- `description:` field exists and is non-empty

### Phase 3 — Report

Produce ONE consolidated report with:

1. **Tool availability** — which tools ran, which were skipped, with install commands for the missing ones
2. **Per-tool results** — pass / N issues / file:line:problem
3. **Summary** — total issues, files affected, recommended next action

**Do NOT auto-fix.** Default behavior is report-only. Even when a tool offers
a safe `--fix` mode (ruff, isort), do not run it without explicit user
agreement — past experience shows automated fixes can quietly damage
hand-aligned data tables, comment formatting, etc. (See "Black and aligned
tables" below.)

## Tool nuances

### Black and aligned tables

Black expands every multi-key dict literal onto separate lines. This destroys
hand-aligned tables — e.g., a price table where each row holds the same
fields and the visual alignment carries semantic meaning. Before applying
black to such a file, **stop and confirm with the user**. The fix when the
user wants to keep the alignment:

```python
# fmt: off
PRICING = {
    "model-a":   {"input": 5.00, "output": 25.00, ...},
    "model-b":   {"input": 3.00, "output": 15.00, ...},
}
# fmt: on
```

`# fmt: off` and `# fmt: on` MUST be on their own lines — trailing comments
on the same line are silently ignored by black.

### shellcheck severity

shellcheck issues come in 4 levels: error / warning / info / style. Treat:
- error / warning → real bugs, surface prominently
- info → "best practice", often "wrap in quotes for safety"; useful but low-stakes
- style → cosmetic, usually ignore unless the user asked for cleanup

When reporting, group by severity so the user can triage.

### `node --check` vs prettier

`node --check` only catches syntax errors. It does NOT catch unused imports,
unreachable code, or formatting. If the repo has no eslint config and prettier
isn't installed, `node --check` is the floor — report it as "syntax-only
coverage" so the user knows it's not deep linting.

### codespell false positives

codespell occasionally flags valid identifiers — short abbreviations and
domain-specific tokens it mistakes for typos. When a flag looks suspicious,
check whether the word is a deliberate identifier before reporting it as an
issue. Add to a
`.codespell-ignore` list in the report if appropriate.

## Output style

Keep the final report tight. Lead with whether the repo is clean or has
issues. Then a small table per language. Avoid pasting full diffs unless the
user asks — show counts and file:line locations. Always finish with the
"missing tools + install commands" block so the user can decide what to add.
