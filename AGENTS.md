# AGENT GUIDELINES

This repository is worked on by local coding assistants such as Codex and
Claude Code. Keep changes small, readable, and biased toward the existing
Python/Tkinter implementation.

## Shared Principles

- **Simplicity first:** Prefer straightforward functions, clear names, and
  obvious control flow over clever abstractions.
- **Local-first privacy:** Lethe is a local recorder, transcriber, and minutes
  tool. Do not introduce network services, telemetry, or cloud processing unless
  the maintainer explicitly asks for it.
- **Small dependency surface:** Reuse the dependencies already declared in
  `pyproject.toml`. Add new packages only when they materially simplify the
  requested change.
- **Cross-platform behavior:** Preserve macOS and Windows support. Avoid
  platform-specific code unless it is isolated behind an explicit platform
  check.
- **No runtime artifacts in git:** Never commit recordings, generated audio,
  session zip files, model caches, virtual environments, or local user settings.
- **Secrets never in repo:** Do not write real credentials, tokens, API keys, or
  other secrets into tracked files, examples, comments, or commit messages.
- **Readable diffs:** Group related edits and keep commits focused. Leave
  unrelated local changes alone.
- **Tests by risk:** Run `pytest -q` after code changes when practical. For
  docs-only or agent-config-only changes, a syntax or diff review is sufficient.

## Agent Bootstrap

- At the start of a task, read this `AGENTS.md` and apply it as the default
  instruction set for repository work.
- Inspect nearby code and tests before editing.
- Prefer the existing package layout under `src/recorder`, `src/llm`, and
  `tests`.
- Use `rg` for searching files and text when available.
- Use the published `task` commands for common workflows. `task default` runs
  formatting, linting, type checks, and tests.
- Use `task test` or `uv run --no-sync pytest -q` for the default test run.
- Do not create a new virtual environment unless the maintainer asks for one.

## Git Policy

- When an assistant makes repository changes, create a git commit before ending
  the task unless the maintainer explicitly says not to commit.
- If other pending local changes already exist, stage and commit only the files
  or hunks changed by the assistant in the current task.
- Do not include unrelated user changes in assistant commits.
- Push only when the maintainer explicitly asks to push.
- Use concise imperative commit messages, for example `Add agent guidelines`.

## Codex CLI Agent

1. Start by inspecting the relevant files and existing conventions.
2. Share a brief plan for non-trivial work.
3. Implement the smallest change that satisfies the request.
4. Run practical verification, preferably through `task default` for code
   changes, and summarize the result.
5. Commit the files changed by Codex before ending the task unless told not to.

## Claude Code Agent

1. Follow this file and `CLAUDE.md`.
2. Implement focused changes using the existing project style.
3. Run practical verification, preferably through `task default` for code
   changes, before reporting completion.
4. Commit the files changed by Claude Code before ending the task unless told
   not to.
