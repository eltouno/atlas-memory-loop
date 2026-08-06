# Agent-assisted installation protocol

This document is an execution contract for an AI agent installing Atlas Memory
Loop for a user. The user should be able to provide the repository URL and ask
the agent to install it without translating this guide into shell commands.

The currently supported guided host is Codex. For another host, stop after package
installation and explain that its integration is manual.

## Desired user experience

The agent owns discovery, command execution, configuration, and automated
verification. The user owns only decisions that affect trust or persistent state.

The normal conversation should require at most:

1. A vault choice, only when it cannot be discovered unambiguously.
2. Approval of the package installation and the displayed configuration plan.
3. Trusting the generated hooks in Codex after restart.

Do not ask the user to copy commands that the agent can safely run itself.

## Trust boundaries

Never:

- use `sudo` or install into the system Python;
- overwrite an existing Codex configuration;
- choose between multiple vaults without asking;
- pass `--yes` before the user has reviewed the exact dry-run plan;
- use `--dangerously-bypass-hook-trust` as part of onboarding;
- claim that hook trust was verified programmatically;
- delete Markdown memory or unrelated host configuration during removal.

Request approval before downloading or installing executable code, writing host
configuration, or writing to a vault outside the current workspace. Explain the
target and purpose in plain language.

## Phase 1: read-only discovery

Before asking the user anything, inspect:

- operating system and shell;
- target project root;
- Git status of the target project, if it is a Git repository;
- Python version, which must be 3.10 or newer;
- availability of `codex` and `pipx`;
- `ATLAS_MEMORY_VAULT`, if set;
- vault candidates explicitly mentioned by the user or located inside the current
  workspace. A directory is recognized as a vault when it contains `.obsidian/`
  or `00_System/`.

Do not scan the user's entire home directory without permission. If no vault is
found, ask for its location. If several are found, show their names and paths and
ask the user to choose one.

Derive the default project scope from the project directory name. Ask for a
different name only when an existing Memory Loop scope must be preserved or two projects
would otherwise share the same scope.

Use **Atlas Memory Loop** or **Memory Loop** in every user-facing explanation.
Never use **Atlas** alone as the product name.

## Phase 2: package installation

Inspect `pyproject.toml`, `SECURITY.md`, and this repository's `AGENTS.md` before
installing. Confirm that the source is the expected repository:

```text
https://github.com/eltouno/atlas-memory-loop
```

Prefer an isolated `pipx` installation because the `atlas-memory` command remains
available across projects without modifying their Python dependencies:

```bash
pipx install "git+https://github.com/eltouno/atlas-memory-loop.git"
```

On Windows, use the active Python launcher equivalent:

```powershell
pipx install "git+https://github.com/eltouno/atlas-memory-loop.git"
```

If `pipx` is not installed, ask approval before installing it. If the environment
cannot use `pipx`, create a dedicated virtual environment for Atlas Memory Loop;
do not add the package to the target project's application environment unless the
user explicitly requests that coupling.

After installation, resolve and retain the actual executable or Python interpreter
path. Verify:

```bash
atlas-memory --help
```

When working from a development checkout, use its virtual environment and invoke
`<venv-python> -m atlas_memory` consistently.

## Phase 3: configuration preview and approval

From the target project root, generate a non-mutating preview:

```bash
atlas-memory setup codex \
  --vault "/absolute/path/to/vault" \
  --project-root "/absolute/path/to/project" \
  --project-name "project-scope" \
  --dry-run
```

Summarize the preview in the user's language:

- project being configured;
- vault receiving durable memory;
- project scope;
- MCP server name;
- hooks being added;
- backup location;
- existing configuration being merged rather than replaced.

Ask for approval of that exact plan. If any path or scope changes after approval,
generate a new preview and ask again.

After approval, apply the same plan:

```bash
atlas-memory setup codex \
  --vault "/absolute/path/to/vault" \
  --project-root "/absolute/path/to/project" \
  --project-name "project-scope" \
  --yes
```

Do not edit the generated `.codex/config.toml` or `.codex/hooks.json` manually
unless setup reports a collision that cannot be resolved through the supported
command. Preserve unrelated configuration and user changes.

## Phase 4: automated verification

Run both checks after configuration:

```bash
atlas-memory setup verify codex --project-root "/absolute/path/to/project"
atlas-memory --vault "/absolute/path/to/vault" doctor
```

The first command verifies managed files, the pinned Python environment, the
Codex executable, and hook feature availability. `doctor` verifies the vault,
runtime, index, and session state.

If a check fails, diagnose and repair within the approved scope, then rerun the
whole verification. Do not hide warnings. Do not continue to host activation
while an automated check is failing.

## Phase 5: user activation in Codex

Project-local Codex configuration and non-managed command hooks have explicit
trust boundaries. These UI decisions are intentionally not automated.

Tell the user, in simple terms:

1. Restart Codex in the configured project.
2. Open `/hooks`.
3. Review and trust the `UserPromptSubmit` and `Stop` commands whose paths match
   the approved plan.
4. Return to the installation conversation and confirm that both are trusted.

The agent must describe what the hooks do before asking for trust:

- `UserPromptSubmit` sends the prompt to the local memory process and can return
  bounded relevant Markdown context.
- `Stop` sends the latest assistant response to the local memory process and
  refreshes the durable session snapshot.

Both commands run locally with the configured Python environment and vault. Hook
trust is bound to the exact command definition; a later command change may require
review again.

## Phase 6: fresh-host smoke test

After the user confirms trust, use a fresh Codex task in the configured project.
Do not use the pre-installation task as proof because project instructions and
hooks are loaded at host/session start.

Perform this test:

1. Submit a harmless prompt containing a unique marker.
2. Let one assistant turn complete.
3. Run `atlas-memory --vault <vault> doctor` again.
4. Confirm that the runtime has a Codex session for the configured project.
5. Confirm that a durable Markdown session snapshot exists under
   `70_State/agent_sessions/` and contains the expected project scope. Avoid
   printing private memory content unless needed for diagnosis.

If the host exposes hook diagnostics, confirm that both hooks ran without errors.
If the agent cannot inspect the fresh task, tell the user exactly what was verified
and leave end-to-end activation marked as pending.

## Completion report

Report these states separately:

```text
Package       installed | failed
Configuration configured | failed
Checks        passed | failed
Hook trust    confirmed | pending user action
End-to-end    passed | pending fresh-host test | failed
```

Include the project, vault, project scope, backup location, and any remaining user
action. A successful automated verification with hook trust still pending is
"configured", not "fully operational".

## Upgrade and removal

For an upgrade, update the isolated package, rerun the configuration preview, ask
approval, apply it, and repeat every verification phase. Setup is idempotent and
may migrate older managed hook definitions.

For removal, preview first and obtain approval:

```bash
atlas-memory setup remove codex \
  --project-root "/absolute/path/to/project" \
  --dry-run
```

Then apply:

```bash
atlas-memory setup remove codex \
  --project-root "/absolute/path/to/project" \
  --yes
```

Confirm that unrelated Codex configuration and durable Markdown memory remain.
