@AGENTS.md

## Claude Code Agent

1. When Claude Code makes repository changes, create a git commit before ending
   the task unless the maintainer explicitly says not to commit.
2. If other pending local changes already exist, stage and commit only the files
   or hunks Claude Code changed.
3. Do not include unrelated user changes in Claude Code commits.
4. Push only when the maintainer explicitly asks to push.
5. For normal verification, use `task default` when code changes make it
   practical. For docs-only or agent-config-only changes, review the diff
   instead.
