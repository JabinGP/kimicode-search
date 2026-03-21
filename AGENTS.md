# AGENTS.md

Repository guidance for coding agents working in `kimicode-search`.

## Overview

- Language: Python.
- Dependency management: `pip` via `requirements.txt`.
- Runtime dependency in repo: `mcp==1.26.0`.
- App shape: one main application file, `server.py`.
- Deployment files: `Dockerfile`, `compose.yaml`, `Caddyfile`.
- Env templates: `.env.example`, `.env.production.example`.
- Purpose: expose Kimi Coding Search / Fetch APIs as MCP tools.

## Repository map

- `server.py` — main app logic, helper functions, Kimi client, MCP tools, CLI.
- `requirements.txt` — dependency list.
- `README.md` — setup, deployment, env variable documentation.
- `Dockerfile` — container build and default HTTP startup command.
- `compose.yaml` — app + Caddy deployment.
- `Caddyfile` — reverse proxy config.

## Rules file status

Checked repository contents:

- No `AGENTS.md` existed before this file was added.
- No `.cursor/rules/` directory found.
- No `.cursorrules` file found.
- No `.github/copilot-instructions.md` file found.

Do not reference Cursor/Copilot repository rules unless they are added later.

## Core agent behavior

- Keep changes small and local.
- Prefer editing `server.py` directly over introducing new modules.
- Match the current standard-library-first approach.
- Do not add dependencies without a strong reason.
- Do not fabricate project tooling that is not present.
- If behavior changes, update docs and env templates in the same change.

## Setup commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional virtualenv setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run commands

Local stdio mode:

```bash
python server.py --transport stdio
```

Local streamable HTTP mode:

```bash
python server.py --transport streamable-http --host 0.0.0.0 --port 8000
```

Build Docker image:

```bash
docker build -t kimi-coding-mcp .
```

Run container locally:

```bash
docker run --rm -p 8000:8000 -e KIMI_API_KEY=sk-kimi-your-key kimi-coding-mcp
```

Run compose deployment:

```bash
docker compose up -d --build
```

## Build / lint / test reality

This repository does **not** currently define dedicated build, lint, or test scripts.

Repo-confirmed absences:

- No `pyproject.toml`
- No `pytest.ini`, `tox.ini`, or `noxfile.py`
- No `tests/` directory
- No `ruff`, `black`, `flake8`, `isort`, `mypy`, or `pyright` config files
- No package script runner like npm, pnpm, yarn, or make

Because of that:

- Do not claim `pytest`, `ruff`, or `mypy` are official repo commands.
- Do not invent CI workflows.
- Be explicit that verification is mostly smoke-test based right now.

## Practical verification commands

Syntax-only validation:

```bash
python -m py_compile server.py
```

CLI/help smoke check:

```bash
python server.py --help
```

Deployment smoke check:

```bash
docker build -t kimi-coding-mcp .
```

## Single-test guidance

There is no test suite in the repository, so there is no repository-defined single-test command.

Until tests exist:

- Do not write “run a single test with `pytest path::test_name`” as if it already applies here.
- Do not say unit tests are available.
- Prefer focused smoke validation and manual checks.

If tests are added later, update this file with the exact command for:

- full test run
- single file run
- single test case run

## Code style guidelines

These rules are inferred from `server.py` and should be treated as the current local convention.

### Imports

- Standard library imports first.
- Third-party imports after a blank line.
- Avoid unused imports.
- Current third-party import pattern: `from mcp.server.fastmcp import Context, FastMCP`.

### Formatting

- Use 4-space indentation.
- Follow PEP 8 style and readable line breaks.
- Use trailing commas in multiline calls where they improve diffs.
- Prefer clarity over compression.

### Types

- Use modern Python typing syntax already present in the repo, such as `str | None`.
- Add parameter and return annotations for helpers when practical.
- Do not weaken types unnecessarily.

### Naming

- Constants: `UPPER_SNAKE_CASE`.
- Functions and local variables: `snake_case`.
- Classes: `PascalCase`.
- Use domain-specific, descriptive names.

### Function design

- Keep helpers small and focused.
- Extract reusable protocol logic into helpers.
- Preserve the current file flow:
  - constants
  - helper functions
  - `KimiCodingClient`
  - `create_server()`
  - `parse_args()`
  - `main()`

### Error handling

- Raise explicit exceptions with useful messages.
- Use `ValueError` for invalid tool input.
- Use `ToolCallError` for downstream API/request failures.
- Catch expected exceptions only.
- Preserve exception chaining with `raise ... from exc`.
- Avoid broad `except Exception` unless absolutely necessary.

### Config and environment handling

- Keep defaults centralized as module-level constants.
- Read env vars through clear, explicit helpers/patterns.
- Normalize external input before use.
- Keep env names aligned with README and env template files.

### Networking and API behavior

- Keep request construction explicit.
- Prefer standard library HTTP utilities unless a new dependency is justified.
- Preserve current header semantics and response formatting behavior.
- Keep JSON pretty-printing behavior for JSON responses.

### MCP tool conventions

- Validate input early with trimming/non-empty checks.
- Keep tool descriptions concise and user-facing.
- Resolve request-scoped auth from `Context` rather than global mutable state.

## Documentation sync requirements

When changing flags, ports, env vars, startup behavior, or deployment assumptions, update the relevant docs:

- `README.md`
- `.env.example`
- `.env.production.example`
- `Dockerfile`
- `compose.yaml`

## Final reminders

- This is a small repo; avoid over-engineering.
- State clearly when something does not exist.
- Prefer repository facts over generic Python best-practice assumptions.
