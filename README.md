# mirope-cc-skills

My personal collection of [Claude Code Skills](https://docs.claude.com/en/docs/claude-code/skills).

## Skills

| Skill | Description |
|---|---|
| [cc-usage-stats](./skills/cc-usage-stats) | Self-contained HTML dashboard for Claude Code token usage, USD cost, and tool/skill/subagent attribution |

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
