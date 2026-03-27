# Scripts

Run from **repo root**.

## Build wheel (with latest console)

```bash
bash scripts/wheel_build.sh
```

- Builds the console frontend (`console/`), copies `console/dist` to `src/copaw/console/dist`, then builds the wheel. Output: `dist/*.whl`.

## Start local source checkout

```bash
bash scripts/start_copaw_local.sh
```

- Builds the console frontend when needed, syncs Python dependencies with `uv`, initializes a repo-local CoPaw working dir in `.copaw-dev/` on first run, starts `copaw app` with reload enabled, and opens `http://127.0.0.1:8088/` in your browser.
- Installs console dependencies only when `node_modules` is missing or stale, but rebuilds the frontend on every run so local source edits show up immediately.
- Syncs built-in skills into the repo-local default workspace before launch, so newly added built-in skills show up in the local CoPaw instance without a manual reset.

## Setup recruiting assistant locally

```bash
bash scripts/setup_recruiting_assistant_local.sh
```

- Syncs the built-in `recruiting_assistant` skill into `.copaw-dev/workspaces/default/active_skills/`.
- Seeds local env defaults such as `RECRUITING_ENABLED_SITES=liepin`.
- Adds repo-local `boss`, `zhaopin`, and `liepin` MCP clients to the default agent.
- Adds a repo-local `liepin` MCP client to the default agent, pointing at `copaw.agents.skills.recruiting_assistant.liepin_mcp.server`.
- Adds a repo-local `zhaopin` MCP client, pointing at `copaw.agents.skills.recruiting_assistant.zhaopin_mcp.server`.
- Uses a persistent Liepin browser profile under `.copaw-dev/recruiting/liepin-profile/`.
- Uses a persistent Zhaopin browser profile under `.copaw-dev/recruiting/zhaopin-profile/`.

## Build website

```bash
bash scripts/website_build.sh
```

- Installs dependencies (pnpm or npm) and runs the Vite build. Output: `website/dist/`.

## Build Docker image

```bash
bash scripts/docker_build.sh [IMAGE_TAG] [EXTRA_ARGS...]
```

- Default tag: `copaw:latest`. Uses `deploy/Dockerfile` (multi-stage: builds console then Python app).
- Example: `bash scripts/docker_build.sh myreg/copaw:v1 --no-cache`.

## Run Test

```bash
# Run all tests
python scripts/run_tests.py

# Run all unit tests
python scripts/run_tests.py -u

# Run unit tests for a specific module
python scripts/run_tests.py -u providers

# Run integration tests
python scripts/run_tests.py -i

# Run all tests and generate a coverage report
python scripts/run_tests.py -a -c

# Run tests in parallel (requires pytest-xdist)
python scripts/run_tests.py -p

# Show help
python scripts/run_tests.py -h
```
