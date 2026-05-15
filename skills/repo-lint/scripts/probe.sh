#!/usr/bin/env bash
# Probe lint-tool availability for repo-lint skill.
# Output: aligned table to stdout. Two columns of intent:
#   STATUS = "ok <version>" | "MISSING"
#   HINT   = install command (only when missing). Skill never auto-installs.
#
# Tools checked map to file types in SKILL.md. Add a row here when adding a
# language, then update SKILL.md's decision table.
#
# Python tool discovery: probe checks PATH first, then any venv pointed to by
# the REPO_LINT_VENV env var, then $VIRTUAL_ENV (an active venv), then a list
# of common per-user venv paths. The skill instructs the model to set
# REPO_LINT_VENV when the user has a non-standard venv.

set -u

# Build PATH override that prepends candidate venv bin/ dirs.
# This lets `command -v ruff` find tools installed only inside a venv.
EXTRA_PATHS=()
[ -n "${REPO_LINT_VENV:-}" ] && EXTRA_PATHS+=("$REPO_LINT_VENV/bin")
[ -n "${VIRTUAL_ENV:-}" ]    && EXTRA_PATHS+=("$VIRTUAL_ENV/bin")
# Common per-user venv locations to probe. Add more as needed; missing dirs
# are silently skipped by PATH lookup.
EXTRA_PATHS+=(
  "$HOME/Desktop/Dev/local/.venv/bin"
  "$HOME/.venv/bin"
  "./venv/bin"
  "./.venv/bin"
)

# shellcheck disable=SC2155
export PATH="$(IFS=:; echo "${EXTRA_PATHS[*]}"):$PATH"

probe() {
  local name="$1"
  local bin="$2"
  local version_cmd="$3"
  local install_hint="$4"
  local ver loc
  if command -v "$bin" >/dev/null 2>&1; then
    ver=$(eval "$version_cmd" 2>&1 | head -1 | tr -d '\r')
    loc=$(command -v "$bin")
    printf "  %-14s  ok      %-30s  (%s)\n" "$name" "$ver" "$loc"
  else
    printf "  %-14s  MISSING                                  install: %s\n" "$name" "$install_hint"
  fi
}

echo "=== repo-lint tool probe ==="
echo
echo "Search path additions for venv-installed Python tools:"
for p in "${EXTRA_PATHS[@]}"; do
  if [ -d "$p" ]; then
    echo "  + $p"
  fi
done
echo
echo "Python:"
probe "ruff"      "ruff"      "ruff --version"      "pip install ruff  (or: brew install ruff)"
probe "black"     "black"     "black --version"     "pip install black"
probe "isort"     "isort"     "isort --version"     "pip install isort"
probe "codespell" "codespell" "codespell --version" "pip install codespell"
echo
echo "Shell:"
probe "shellcheck" "shellcheck" "shellcheck --version | sed -n 2p" "brew install shellcheck"
# bash -n is bash-builtin, no probe needed; SKILL.md notes it's always available.
echo
echo "JavaScript:"
probe "node"      "node"      "node --version"      "brew install node  (or: nvm install --lts)"
probe "prettier"  "prettier"  "prettier --version"  "npm install -g prettier"
echo
echo "Markdown:"
probe "markdownlint" "markdownlint" "markdownlint --version" "npm install -g markdownlint-cli"
echo
echo "Notes:"
echo "  - 'bash -n' is built into bash and always available; not probed."
echo "  - Markdown trailing-whitespace + relative-link checks ship inside this skill"
echo "    (scripts/md-check.py) and need only Python 3 stdlib."
echo "  - To probe a non-default Python venv: REPO_LINT_VENV=/path/to/venv ./probe.sh"
