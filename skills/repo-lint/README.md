# repo-lint

Whole-tree, multi-language lint skill for Claude Code. Probes which lint tools
you have installed, runs the ones it can, and reports issues without
auto-fixing. Designed to complement `lint-fix` (which scopes to git ranges and
auto-fixes Python).

## When to use

- "lint the whole repo"
- "check all the code in this project"
- "run every linter you have for me"

When you only want to lint Python changes in a specific commit / staged /
unstaged set, use [`lint-fix`](https://github.com/yuhao/lint-fix-or-wherever)
instead — it's git-range scoped and applies fixes.

## Coverage

| Language | Tools |
|---|---|
| Python | ruff · isort · black (check-only) · codespell |
| Shell | shellcheck · `bash -n` |
| JavaScript / `*.mjs` | `node --check` (syntax) · prettier (optional) |
| Markdown | trailing whitespace · broken relative links (built-in) · markdownlint (optional) |
| All text | codespell |
| CC skills repos | SKILL.md frontmatter validity (when applicable) |

Tools are probed at start. Missing tools are reported with their macOS install
commands; the skill never installs anything itself.

## Install

```bash
git clone https://github.com/MokusMokun/mirope-cc-skills.git ~/code/mirope-cc-skills
ln -s ~/code/mirope-cc-skills/skills/repo-lint ~/.claude/skills/repo-lint
```

## Environment variables

| Variable | Purpose |
|---|---|
| `REPO_LINT_VENV` | Path to a Python venv whose `bin/` should be added to `PATH` for tool discovery. Defaults: `$VIRTUAL_ENV`, `~/Desktop/Dev/local/.venv`, `~/.venv`, `./venv`, `./.venv` |

## Default policy: report, do not fix

The skill never auto-applies fixes. This is deliberate — past experience
shows tools like `black` will silently destroy hand-aligned data tables in
the name of style consistency. The skill reports what's wrong and lets you
decide what to apply.

For aligned tables you want to protect from `black`, wrap them in:

```python
# fmt: off
PRICING = { "model-a": {...}, "model-b": {...} }
# fmt: on
```

Both directives must be on their own lines (trailing comments on the same
line are silently ignored).

## License

MIT — see repo root.
