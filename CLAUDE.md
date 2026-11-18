# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Branch & PR workflow (Git Flow: develop → qa → 19.0)

| Branch | Git Flow role | Deployed to |
|--------|---------------|-------------|
| `develop` | Integration: every new change lands here first | — |
| `qa` | Release candidate under test | QA server |
| `19.0` | Production (Git Flow's `main`) | Production |

| Branch type | Created from | PR into | Use |
|-------------|--------------|---------|-----|
| `feature/<ticket>-<short-name>` | `develop` | `develop` | New functionality |
| `bugfix/<ticket>-<short-name>` | `develop` | `develop` | Non-urgent fixes, including issues found in QA |
| `hotfix/<ticket>-<short-name>` | `19.0` | `19.0` | Urgent production fix |

`<ticket>` is the task number (e.g. `feature/T004251-waiting-report`); lowercase, hyphens.

1. **Start:** `git switch develop && git pull && git switch -c feature/T00xxxx-short-name`.
2. **PR to `develop`:** `gh pr create --base develop`. Review, merge, delete the branch.
3. **Promote to QA:** PR `develop` → `qa`. Merge, deploy QA, test.
4. **Release:** when QA approves, PR `qa` → `19.0`. Merge, deploy production.
5. **Issue found in QA:** new `bugfix/` branch from `develop` → `develop`, then promote again
   (step 3). Never commit on `qa` directly.
6. **Hotfix:** `hotfix/` branch from `19.0` → PR to `19.0`. After the deploy, back-merge with PRs
   `19.0` → `qa` and `qa` → `develop` so the fix is not lost.
7. **Rules:** no direct pushes to `develop`, `qa` or `19.0`. Promotion PRs (`develop` → `qa`,
   `qa` → `19.0`, back-merges) use a **merge commit, never squash or rebase**; squashing them makes
   the branches diverge and every later promotion conflicts. Feature PRs may be squashed.

**For Claude Code:** new `feature/` and `bugfix/` PRs always use `--base develop`; `hotfix/` uses
`--base 19.0`. Open promotion PRs (`develop` → `qa`, `qa` → `19.0`) only when the user asks.
