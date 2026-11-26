# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branch & PR workflow (Git Flow: develop → 19.0, no QA stage)

| Branch | Git Flow role | Deployed to |
|--------|---------------|-------------|
| `develop` | Integration: every new change lands here first | — |
| `19.0` | Production (Git Flow's `main`) | Production |

There is **no QA stage** in this repo: `develop` is released straight to `19.0`. The old `qa` branch
is retired; PRs into it fail.

| Branch type | Created from | PR into | Use |
|-------------|--------------|---------|-----|
| `feature/<ticket>-<short-name>` | `develop` | `develop` | New functionality |
| `bugfix/<ticket>-<short-name>` | `develop` | `develop` | Non-urgent fixes |
| `hotfix/<ticket>-<short-name>` | `19.0` | `19.0` | Urgent production fix |

`<ticket>` is the task number (e.g. `feature/T004251-waiting-report`); lowercase, hyphens.

1. **Start:** `git switch develop && git pull && git switch -c feature/T00xxxx-short-name`.
2. **PR to `develop`:** `gh pr create --base develop`. Review, merge, delete the branch.
3. **Release:** PR `develop` → `19.0`. Merge, deploy production. Everything merged in `develop`
   ships together, so check `git log origin/19.0..origin/develop` first.
4. **Hotfix:** `hotfix/` branch from `19.0` → PR to `19.0`. After the deploy, back-merge with a PR
   `19.0` → `develop` so the fix is not lost.
5. **Rules:** no direct pushes to `develop` or `19.0`. Release and back-merge PRs (`develop` → `19.0`,
   `19.0` → `develop`) use a **merge commit, never squash or rebase**; squashing them makes the
   branches diverge and every later release conflicts. Feature PRs may be squashed.

**Enforced by:** `.github/workflows/branch-flow.yml` (fails PRs outside the flow) and the Claude Code
hook `.claude/hooks/branch_flow.py` (blocks bad branch names, direct pushes to `develop`/`19.0`,
PRs into `qa` and wrong `gh pr create` pairs).

**For Claude Code:** new `feature/` and `bugfix/` PRs always use `--base develop`; `hotfix/` uses
`--base 19.0`. Open release PRs (`develop` → `19.0`) only when the user asks.
