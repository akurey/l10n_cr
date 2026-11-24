#!/usr/bin/env python3
"""Claude Code PreToolUse hook: keep Bash git/gh commands inside the Git Flow branch workflow.

Flow (see "Branch & PR workflow" in CLAUDE.md):
    feature/* | bugfix/*  -> develop -> qa -> 19.0
    hotfix/*  -> 19.0, then back-merges 19.0 -> qa -> develop

Blocks (exit 2, reason on stderr, which Claude reads):
- new branches without a feature/, bugfix/ or hotfix/ prefix;
- direct pushes to develop, qa or 19.0;
- `gh pr create` with a head/base pair outside the flow (no --base means the repo
  default, 19.0, so feature work must pass --base develop).
The same pairs are enforced on GitHub by .github/workflows/branch-flow.yml.
"""
import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = ("develop", "qa", "19.0")
WORK_BRANCH = re.compile(r"^(feature|bugfix|hotfix)/[A-Za-z0-9._-]+$")
SEPARATORS = {"&&", "||", ";", "|", "&", "\n"}
DOC = "See 'Branch & PR workflow' in CLAUDE.md."


def pair_error(head, base):
    """Return why head -> base breaks the flow, or None when it is allowed."""
    if base == "develop":
        if re.match(r"^(feature|bugfix)/", head) or head == "qa":
            return None
        return "into develop only feature/<ticket>-<name>, bugfix/<ticket>-<name> or the qa back-merge"
    if base == "qa":
        if head in ("develop", "19.0"):
            return None
        return "into qa only develop (promotion) or 19.0 (hotfix back-merge)"
    if base == "19.0":
        if head == "qa" or head.startswith("hotfix/"):
            return None
        return "into 19.0 only qa (release) or hotfix/<ticket>-<name>; feature work goes to --base develop"
    return None


def current_branch(cwd):
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607 (git from PATH, as the user runs it)
            cwd=cwd, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def segments(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out, seg = [], []
    for tok in tokens:
        if tok in SEPARATORS or set(tok) <= set("&|;"):
            out.append(seg)
            seg = []
        else:
            seg.append(tok)
    out.append(seg)
    return [s for s in out if s]


def option_value(args, *names):
    for i, arg in enumerate(args):
        for name in names:
            if arg == name and i + 1 < len(args):
                return args[i + 1]
            if name.startswith("--") and arg.startswith(name + "="):
                return arg.split("=", 1)[1]
    return None


def check_git(args, cwd):
    if len(args) > 2 and args[0] == "-C":
        cwd, args = os.path.join(cwd, args[1]), args[2:]
    if not args:
        return None
    sub, rest = args[0], args[1:]
    if sub in ("switch", "checkout") or (sub == "worktree" and rest[:1] == ["add"]):
        name = option_value(rest, "-c", "-C", "-b", "-B", "--create")
        if name and not WORK_BRANCH.match(name):
            return (f"Branch '{name}' must be feature/<ticket>-<name>, bugfix/<ticket>-<name> "
                    f"or hotfix/<ticket>-<name>. {DOC}")
    if sub == "push":
        positional = [a for a in rest if not a.startswith("-")]
        refspecs = positional[1:]
        if not refspecs:
            if "--tags" in rest or "--all" in rest or "--mirror" in rest:
                return None
            refspecs = [current_branch(cwd)]
        for spec in refspecs:
            spec = spec.lstrip("+")
            dst = spec.split(":", 1)[1] if ":" in spec else spec
            if dst == "HEAD":
                dst = current_branch(cwd)
            dst = dst.removeprefix("refs/heads/")
            if dst in PROTECTED:
                return (f"Direct push to '{dst}' is not allowed: {', '.join(PROTECTED)} only change "
                        f"through pull requests. {DOC}")
    return None


def check_gh(args, cwd):
    if args[:2] != ["pr", "create"]:
        return None
    rest = args[2:]
    base = option_value(rest, "--base", "-B") or "19.0"
    head = option_value(rest, "--head", "-H") or current_branch(cwd)
    head = head.split(":", 1)[-1]
    if base not in PROTECTED:
        return None
    reason = pair_error(head, base)
    if reason:
        return f"PR '{head}' -> '{base}' is not allowed: {reason}. {DOC}"
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or "."
    for seg in segments(command):
        if seg[0] == "cd" and len(seg) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(seg[1]))
            continue
        if seg[0] == "git":
            error = check_git(seg[1:], cwd)
        elif seg[0] == "gh":
            error = check_gh(seg[1:], cwd)
        else:
            error = None
        if error:
            sys.stderr.write(error + "\n")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
