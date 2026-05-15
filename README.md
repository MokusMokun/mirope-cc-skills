# mirope-cc-skills

My personal collection of [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills).

## Skills

| Skill | Description |
|---|---|
| [cc-usage-stats](./skills/cc-usage-stats) | Self-contained HTML dashboard for Claude Code token usage, USD cost, and tool/skill/subagent attribution |
| [web-access-headless](./skills/web-access-headless) | Fork of [eze-is/web-access](https://github.com/eze-is/web-access): runs a separate headless Chrome (port 9333, isolated profile) instead of reusing the user's daily Chrome — zero impact on the main browser |
| [repo-lint](./skills/repo-lint) | Whole-tree, multi-language lint with tool-availability probing. Report-only by default. Complementary to `lint-fix` (which is git-range scoped + auto-fix) |

## Install

Each skill is self-contained. Install one by cloning this repo and copying the skill folder into your CC skills directory:

```bash
git clone https://github.com/MokusMokun/mirope-cc-skills.git /tmp/mirope-cc-skills
cp -r /tmp/mirope-cc-skills/skills/cc-usage-stats ~/.claude/skills/
```

Or symlink the whole repo if you want updates via `git pull`:

```bash
git clone https://github.com/MokusMokun/mirope-cc-skills.git ~/code/mirope-cc-skills
ln -s ~/code/mirope-cc-skills/skills/cc-usage-stats ~/.claude/skills/cc-usage-stats
```

## License

[MIT](./LICENSE)
