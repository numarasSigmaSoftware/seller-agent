# Console Foundation Implementation Plan (separate service)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person can start the console container next to the seller agent, create an account with one CLI command, log in from a browser, and see the agent's health, their session, inventory sync, and the event bus on a landing page that refreshes itself.

**Architecture:** The console is its own repository, `seller-console`, and its own container: a small FastAPI app with Jinja2 pages and HTMX partials. It talks to the agent only over the agent's REST API through one long-lived client, using one server-held operator key and an `X-Console-User` header. Accounts, sessions, CSRF tokens, and rate-limit records live in the console's own versioned SQLite store, and every read-modify-write is a compare-and-set. The runtime never imports the agent; tests install the agent package at a pinned version and run the console against the real API in-process.

**Tech Stack:** Python 3.12, FastAPI, Starlette, Jinja2, HTMX 2 (vendored), httpx, aiosqlite, pydantic-settings, pytest with pytest-asyncio, uv, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-15-console-foundation-design.md` (revised 2026-09-16).

---

## Working rules for every task

Two repositories are involved.

- **Agent tasks (1 and 2)** run in the agent worktree on the fork's `ui/dev` branch. There the sibling worktrees share one virtual environment, so every `pytest`, `ruff`, and `python` call is prefixed: `PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync <command>`. Before any test run and any commit there: `rm -f ad_seller.db data/audit_fallback.jsonl`.
- **Console tasks (0 and 3 onward)** run in the console repository, which has its own virtual environment. Commands are plain `uv run <command>` from the repository root.
- Commit author everywhere: `git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit ...`. No co-author trailers.
- Format and lint the files a commit touches before committing: `uv run ruff format <paths> && uv run ruff check <paths>`.
- Never `git add -A`. Stage explicit paths.
- Pinned agent version: the fork's `ui/dev` at `701ce06bff7b7fa607d0156383a757a32992b3e4` today, because the agent enablers land there first (Task 1). After Task 2 merges, the pin moves to that merge commit; after the upstream merge, to the upstream commit. `contract/AGENT_VERSION`, the dev dependency in `pyproject.toml`, and the build context in `compose.yml` always carry the same value, always the full 40-character SHA (Docker's git build context requires it, and a test checks all three agree).

## File structure (console repository)

| Path | Responsibility |
|---|---|
| `pyproject.toml` | package `seller_console`, runtime and dev dependencies, the `seller-console` script, ruff and pytest config |
| `contract/AGENT_VERSION` | the agent commit the console is built and tested against |
| `contract/openapi.json` | the agent's OpenAPI document at that commit, vendored |
| `src/seller_console/__init__.py` | version string |
| `src/seller_console/config.py` | `ConsoleConfig` from environment variables |
| `src/seller_console/store.py` | `Store`: SQLite key-value store with TTL, versions, and compare-and-set |
| `src/seller_console/accounts.py` | password hashing, account records, credential check |
| `src/seller_console/auth.py` | sessions with credential versions, server-stored CSRF tokens, reserve-then-count rate limit, `Operator`, `ConsoleState`, `current_operator` |
| `src/seller_console/client.py` | `ConsoleApi`, typed responses, `ApiRejected`, `ApiUnavailable` |
| `src/seller_console/routes.py` | login, logout, landing page, health partial, `/healthz`, rendering, exception handler |
| `src/seller_console/main.py` | `create_app`, lifespan, `verify_console_key` |
| `src/seller_console/cli.py` | `seller-console create-user` |
| `src/seller_console/templates/*.html`, `partials/health_cards.html` | pages |
| `src/seller_console/static/htmx.min.js`, `console.css` | vendored assets |
| `tests/conftest.py` | agent app at the pinned version, console store, config, app, client, HTML helper |
| `tests/test_*.py` | one file per module plus contract, startup, home, login |
| `Dockerfile`, `compose.yml`, `compose.proxy.yml`, `Caddyfile`, `scripts/smoke.sh`, `.github/workflows/ci.yml`, `README.md`, `agent.env.example`, `console.env.example` | build, run, proxy, checked smoke, CI, docs |

Delivery: Task 0 is console PR 0 (scaffold). Tasks 1 and 2 are agent PR 1 (`me` route, response models, newest-first events; on the fork's `ui/dev`, with the fork CI trigger first). Tasks 3 to 11 are console PR 2 (store, accounts, CLI, sessions, login, shell, startup). Task 12 is console PR 3 (container, compose, proxy overlay, README, checked smoke in CI). Tasks 13 and 14 are console PR 4 (landing page, with the manual browser check on the stack from PR 3).

---

## Task 0: Console repository scaffold, contract, CI

**Files:** all new, in a new repository `seller-console`.

- [ ] **Step 1: Create the repository and the package skeleton**

```bash
mkdir seller-console && cd seller-console && git init -q
mkdir -p src/seller_console/templates/partials src/seller_console/static tests contract .github/workflows
touch tests/__init__.py
printf '__version__ = "0.1.0"\n' > src/seller_console/__init__.py
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "seller-console"
version = "0.1.0"
description = "Browser control room for the IAB Tech Lab seller agent"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.20",
    "httpx>=0.27.0",
    "aiosqlite>=0.20.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "typer>=0.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-timeout>=2.3.0",
    "ruff>=0.15,<0.16",
    # The agent, test-only, at the exact version in contract/AGENT_VERSION.
    # Tests run the console against the real agent app in-process; the runtime never imports it.
    "ad_seller_system @ git+https://github.com/numarasSigmaSoftware/seller-agent.git@701ce06bff7b7fa607d0156383a757a32992b3e4",
]

[project.scripts]
seller-console = "seller_console.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/seller_console"]

[tool.hatch.metadata]
allow-direct-references = true  # the dev dependency on the agent is a git URL

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
ignore = ["E501"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
timeout = 120
```

```bash
printf '701ce06bff7b7fa607d0156383a757a32992b3e4\n' > contract/AGENT_VERSION
uv sync --extra dev
uv run python -c "import ad_seller, seller_console; print('ok')"
```
Expected: `ok`. The agent install pulls its own dependencies, which takes a few minutes the first time.

- [ ] **Step 3: Vendor the agent's OpenAPI document and write the contract tests**

```bash
uv run python - <<'EOF'
import json
from ad_seller.interfaces.api.main import app
open("contract/openapi.json", "w").write(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(len(app.openapi()["paths"]), "paths")
EOF
```
Expected: `75 paths` (76 once Task 1 lands and the pin moves; the response models change the document too, which is the point).

```python
# tests/test_contract.py
"""The vendored OpenAPI document equals what the pinned agent generates; the runtime never imports the agent."""

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "src" / "seller_console"


def test_vendored_openapi_matches_pinned_agent():
    from ad_seller.interfaces.api.main import app

    committed = json.loads((REPO / "contract" / "openapi.json").read_text())
    assert committed == app.openapi(), (
        "contract/openapi.json is out of date with the pinned agent; regenerate it and, if the "
        "pin moved, update contract/AGENT_VERSION and the dev dependency in pyproject.toml together"
    )


def test_agent_version_and_dev_pin_agree():
    version = (REPO / "contract" / "AGENT_VERSION").read_text().strip()
    pyproject = (REPO / "pyproject.toml").read_text()
    assert f"seller-agent.git@{version}" in pyproject


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_runtime_never_imports_the_agent():
    offenders = [
        f"{p.relative_to(REPO)}: {name}"
        for p in PACKAGE.rglob("*.py")
        for name in _imports(p)
        if name == "ad_seller" or name.startswith("ad_seller.")
    ]
    assert offenders == []
```

Relative imports need no resolution here: the package is the whole repository, so a relative import can only reach `seller_console` itself.

- [ ] **Step 4: Run the contract tests**

```bash
uv run pytest tests/test_contract.py -q
```
Expected: `3 passed`.

- [ ] **Step 5: CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv python install 3.12
      - run: uv sync --extra dev
      - run: uv run ruff format --check . && uv run ruff check .
      - run: uv run pytest -q
      - run: docker build -t seller-console:ci .
        if: hashFiles('Dockerfile') != ''
```

- [ ] **Step 6: Commit and push**

```bash
printf '.venv/\n__pycache__/\n*.pyc\ndata/\n.env\nagent.env\nconsole.env\n' > .gitignore
git add .gitignore pyproject.toml uv.lock contract src/seller_console/__init__.py tests/__init__.py tests/test_contract.py .github/workflows/ci.yml
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "chore: scaffold the console package, pin the agent contract, add CI"
```
Create the GitHub repository under `numarasSigmaSoftware`, push `main`, and confirm the workflow runs green. This is console PR 0 (or the initial commit on `main`, if the repository starts empty).

---

## Task 1: Agent enablers: `GET /auth/api-keys/me`, response models, newest-first events

Runs in the agent worktree on `ui/dev`. One agent PR carries everything the console reads.

**Files:**
- Modify: `.github/workflows/ci.yml` (fork only, first commit)
- Modify: `src/ad_seller/interfaces/api/deps.py` (after `_require_operator_api_key_record`)
- Modify: `src/ad_seller/interfaces/api/schemas.py` (four response models)
- Modify: `src/ad_seller/interfaces/api/routers/admin.py` (`me` route before `get_api_key_details`; `response_model` on `/`, `/health`, `/events`, sync status)
- Modify: `src/ad_seller/events/bus.py` (`list_events` newest first in both buses)
- Test: `tests/unit/test_api_key_me_route.py`, `tests/unit/test_console_read_contract.py`

Route order matters: `/auth/api-keys/{key_id}` already exists, so `/auth/api-keys/me` must be registered before it or `me` is captured as a key id.

- [ ] **Step 0: Make the fork run full CI on pull requests into `ui/dev`**

Both agent workflows trigger on `pull_request` only for `main`, so PRs into `ui/dev` would merge with no CI. In `.github/workflows/ci.yml` change `branches: [main]` under `pull_request` to `branches: [main, ui/dev]` (`hygiene.yml` already runs on every pull request). Commit it on its own, fork-only, and never include it in an upstream branch:

```bash
git add .github/workflows/ci.yml
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "ci: run CI for pull requests targeting ui/dev (fork only)"
```
Open and merge that one-line PR into `ui/dev` before the enabler PR, and confirm the CI workflow appears on the enabler PR itself.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_api_key_me_route.py
"""GET /auth/api-keys/me returns the calling key's own metadata.

Any valid key may call it (buyer or operator). Anonymous callers get 401.
The response is ApiKeyInfo: never the hash, never the raw key.
"""

from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from ad_seller.auth.api_key_service import ApiKeyService
from ad_seller.interfaces.api.main import app
from ad_seller.models.api_key import ApiKeyCreateRequest, OperatorApiKeyCreateRequest
from ad_seller.storage.sqlite_backend import SQLiteBackend


@pytest.fixture
async def storage(tmp_path):
    backend = SQLiteBackend(f"sqlite:///{tmp_path}/keys.db")
    await backend.connect()
    yield backend
    await backend.disconnect()


@pytest.fixture
def client():
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(raw_key: str) -> dict:
    return {"Authorization": f"Bearer {raw_key}"}


async def test_me_route_is_registered_before_key_id_route():
    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/auth/api-keys/me" in paths
    assert paths.index("/auth/api-keys/me") < paths.index("/auth/api-keys/{key_id}")


async def test_anonymous_is_401(client, storage):
    with patch("ad_seller.storage.factory.get_storage", return_value=storage):
        response = await client.get("/auth/api-keys/me")
    assert response.status_code == 401


async def test_operator_key_sees_itself(client, storage):
    created = await ApiKeyService(storage).create_operator_key(
        OperatorApiKeyCreateRequest(label="console")
    )
    with patch("ad_seller.storage.factory.get_storage", return_value=storage):
        response = await client.get("/auth/api-keys/me", headers=_auth(created.api_key))
    assert response.status_code == 200
    body = response.json()
    assert body["key_id"] == created.key_id
    assert body["role"] == "operator"
    assert body["label"] == "console"
    assert body["is_active"] is True
    assert "key_hash" not in body
    assert created.api_key not in response.text


async def test_buyer_key_sees_itself_with_buyer_role(client, storage):
    created = await ApiKeyService(storage).create_key(
        ApiKeyCreateRequest(agency_id="agy-1", agency_name="Acme", label="acme")
    )
    with patch("ad_seller.storage.factory.get_storage", return_value=storage):
        response = await client.get("/auth/api-keys/me", headers=_auth(created.api_key))
    assert response.status_code == 200
    assert response.json()["role"] == "buyer"
    assert response.json()["key_id"] == created.key_id


async def test_revoked_key_is_401(client, storage):
    service = ApiKeyService(storage)
    created = await service.create_operator_key(OperatorApiKeyCreateRequest(label="gone"))
    await service.revoke_key(created.key_id)
    with patch("ad_seller.storage.factory.get_storage", return_value=storage):
        response = await client.get("/auth/api-keys/me", headers=_auth(created.api_key))
    assert response.status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/test_api_key_me_route.py -q -p no:warnings
```
Expected: the registration test fails with `'/auth/api-keys/me' is not in list`; the keyed tests fail with 404.

- [ ] **Step 3: Add the required-key dependency wrapper**

Append to `src/ad_seller/interfaces/api/deps.py` after `_require_operator_api_key_record`:

```python
async def _require_api_key_record(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
):
    """FastAPI dependency: require any valid API key (buyer or operator).

    Anonymous → 401. Invalid/revoked/expired key → 401. Same Header-binding
    rationale as ``_get_optional_api_key_record``; tests override this
    function object via ``app.dependency_overrides``.
    """
    from ...auth.dependencies import require_api_key_record

    return await require_api_key_record(authorization, x_api_key)
```

- [ ] **Step 4: Add the route**

In `src/ad_seller/interfaces/api/routers/admin.py`, immediately before `@router.get("/auth/api-keys/{key_id}", tags=["Authentication"])`:

```python
@router.get("/auth/api-keys/me", tags=["Authentication"])
async def get_own_api_key(
    record=Depends(deps._require_api_key_record),
):
    """Return the calling key's own metadata (no secret).

    Registered before ``/auth/api-keys/{key_id}`` so ``me`` is not captured
    as a key id. Any valid key may call this; it is how a client learns
    which key it holds without listing every key.
    """
    from ....auth.api_key_service import ApiKeyService
    from ....storage.factory import get_storage

    storage = await get_storage()
    info = await ApiKeyService(storage).get_key_info(record.key_id)
    if not info:
        raise HTTPException(status_code=404, detail="API key not found")
    return info.model_dump(mode="json")
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/test_api_key_me_route.py -q -p no:warnings
```
Expected: `5 passed`.

- [ ] **Step 6: Revert check**

Move the new route below `get_api_key_details`, rerun: the registration test and the two keyed tests must fail. Restore.

- [ ] **Step 7: Format, lint, commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/api/deps.py src/ad_seller/interfaces/api/routers/admin.py tests/unit/test_api_key_me_route.py
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/api/deps.py src/ad_seller/interfaces/api/routers/admin.py tests/unit/test_api_key_me_route.py
git add src/ad_seller/interfaces/api/deps.py src/ad_seller/interfaces/api/routers/admin.py tests/unit/test_api_key_me_route.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: add GET /auth/api-keys/me so a caller can read its own key metadata"
```

- [ ] **Step 8: Write the failing contract tests for the routes the console reads**

```python
# tests/unit/test_console_read_contract.py
"""The routes a client reads for status declare their shapes, and events come newest first.

Without response models the OpenAPI document says ``{}`` for these bodies, so a client
cannot generate a typed contract from it. Without ordering, "the last event" is whichever
key the storage returned last.
"""

from datetime import datetime, timedelta, timezone

import pytest

from ad_seller.events.bus import InMemoryEventBus, StorageEventBus
from ad_seller.events.models import Event, EventType
from ad_seller.interfaces.api.main import app
from ad_seller.storage.sqlite_backend import SQLiteBackend


def _schema_for(path: str) -> dict:
    return app.openapi()["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


@pytest.mark.parametrize("path,fields", [
    ("/", {"name", "version", "docs"}),
    ("/health", {"status"}),
    ("/api/v1/inventory-sync/status", {"enabled", "last_sync", "sync_count", "task_running"}),
    ("/events", {"events"}),
    ("/auth/api-keys/me", {"key_id", "label", "role", "is_active"}),
])
def test_read_routes_declare_response_models(path, fields):
    schema = _schema_for(path)
    ref = schema.get("$ref")
    assert ref, f"{path} has no response model (schema {schema})"
    component = app.openapi()["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert fields <= set(component["properties"])


def _events(n: int) -> list[Event]:
    base = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    return [
        Event(event_type=EventType.DEAL_CREATED, timestamp=base + timedelta(minutes=i), deal_id=f"d{i}")
        for i in range(n)
    ]


async def test_in_memory_bus_lists_newest_first():
    bus = InMemoryEventBus()
    for event in _events(5):
        await bus.publish(event)
    listed = await bus.list_events(limit=3)
    assert [e.deal_id for e in listed] == ["d4", "d3", "d2"]


async def test_storage_bus_lists_newest_first_before_the_limit(tmp_path):
    storage = SQLiteBackend(f"sqlite:///{tmp_path}/events.db")
    await storage.connect()
    try:
        bus = StorageEventBus(storage)
        events = _events(8)
        for event in reversed(events):  # write oldest last so key order is not timestamp order
            await bus.publish(event)
        listed = await bus.list_events(limit=3)
        assert [e.deal_id for e in listed] == ["d7", "d6", "d5"]
    finally:
        await storage.disconnect()
```

Run: `PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/test_console_read_contract.py -q -p no:warnings`. Expected: every parametrised case fails on "has no response model"; the storage ordering test fails.

- [ ] **Step 9: Add the response models and the ordering**

In `src/ad_seller/interfaces/api/schemas.py`, append:

```python
class RootInfo(BaseModel):
    name: str
    version: str
    docs: str


class HealthStatus(BaseModel):
    status: str


class InventorySyncStatus(BaseModel):
    enabled: bool
    last_sync: Optional[str] = None
    sync_count: int = 0
    task_running: bool = False


class EventListResponse(BaseModel):
    events: list[Event]
```

with `from ...events.models import Event` added to the module's imports (the module already imports `BaseModel` and `Optional`). In `routers/admin.py`, add `response_model=RootInfo` to `GET /`, `response_model=HealthStatus` to `GET /health`, `response_model=EventListResponse` to `GET /events`, `response_model=InventorySyncStatus` to `GET /api/v1/inventory-sync/status`, and `response_model=ApiKeyInfo` to the `me` route (import `ApiKeyInfo` from `....models.api_key`); the handler bodies do not change, since each already returns a dict of that shape.

In `src/ad_seller/events/bus.py`, make both `list_events` implementations return newest first: in `InMemoryEventBus`, build the filtered list as today and return `sorted(events, key=lambda e: e.timestamp, reverse=True)[:limit]`; in `StorageEventBus`, load every candidate event (drop the `ids[-limit:]` slice), sort the loaded events by timestamp descending, then apply the limit. Each method's docstring gains the sentence "Newest first, then the limit."

- [ ] **Step 10: Run the new tests, the existing event and route tests, and commit**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/test_console_read_contract.py tests/unit/test_api_key_me_route.py tests/unit -q -p no:warnings --timeout=600 -k "event or route or api_structure or shadow or contract"
```
Expected: all passed. Revert check: remove the sort in `StorageEventBus.list_events`: the storage ordering test must fail. Restore.

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/api/schemas.py src/ad_seller/interfaces/api/routers/admin.py src/ad_seller/events/bus.py tests/unit/test_console_read_contract.py
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/api/schemas.py src/ad_seller/interfaces/api/routers/admin.py src/ad_seller/events/bus.py tests/unit/test_console_read_contract.py
git add src/ad_seller/interfaces/api/schemas.py src/ad_seller/interfaces/api/routers/admin.py src/ad_seller/events/bus.py tests/unit/test_console_read_contract.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: declare response models on the status routes and list events newest first"
```

---

## Task 2: Regenerate the agent's API documents

Runs in the agent worktree. Unchanged from the first plan.

**Files:**
- Regenerate: `docs/api/openapi.json`, `docs/reference/endpoints.md`
- Modify: `docs/api/overview.md`, `docs/index.md`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: See the drift tests fail**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/test_openapi_drift.py tests/unit/test_docs_inventory_drift.py -q -p no:warnings
```
Expected: `test_openapi_json_matches_app` and `test_inventory_matches_committed_doc[endpoints.md]` fail.

- [ ] **Step 2: Regenerate**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync python scripts/generate_openapi.py
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync python scripts/generate_inventories.py
```

- [ ] **Step 3: Update the hand-written counts and the Authentication table**

```bash
grep -rn "88 endpoints\|88 REST endpoints\|all 88 endpoints" docs/api/overview.md docs/index.md README.md
```
Change every `88` in those hits to `89` (`docs/api/overview.md:3`, `docs/index.md:15`, `docs/index.md:20`, `docs/index.md:57`, `README.md:34`, `README.md:218`). In `docs/api/overview.md`, after the row for `POST /auth/api-keys/operator`, add:

```markdown
| GET | `/auth/api-keys/me` | The calling key's own metadata, no secret (any valid key) |
```

and change the sentence above the table to: "All `/auth/api-keys*` routes require an **operator** credential, except `GET /auth/api-keys/me`, which any valid key may call."

- [ ] **Step 4: CHANGELOG**

Under `## [Unreleased]` → `### Added`, first bullet:

```markdown
- `GET /auth/api-keys/me` returns the calling key's own metadata, so a
  client can learn which key it holds without listing every key.
```

- [ ] **Step 5: Run the full unit suite and commit**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit -q -p no:warnings --timeout=600
rm -f ad_seller.db data/audit_fallback.jsonl
git add docs/api/openapi.json docs/reference/endpoints.md docs/api/overview.md docs/index.md README.md CHANGELOG.md
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "docs: document GET /auth/api-keys/me and regenerate the API inventories"
```
Expected: all passed. Open agent PR 1 against `ui/dev` on the fork. Opening it upstream is the repository owner's decision, reaffirmed on 2026-09-15. **After it merges into `ui/dev`, move the console's pin**: set `contract/AGENT_VERSION`, the dev dependency, and the compose build context to the merge commit, `uv lock`, regenerate `contract/openapi.json` with the Task 0 snippet, run `tests/test_contract.py`, and commit `chore: pin the agent at <sha> (me route)`.

---

## Task 3: Configuration

**Files:**
- Create: `src/seller_console/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
"""ConsoleConfig reads the container's environment; every optional value has a documented default."""

import pytest
from pydantic import ValidationError

from seller_console.config import ConsoleConfig

REQUIRED = {"SELLER_AGENT_URL": "http://agent.test", "CONSOLE_OPERATOR_API_KEY": "ask_live_x"}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "SELLER_AGENT_URL", "CONSOLE_OPERATOR_API_KEY", "CONSOLE_DB_URL", "CONSOLE_SESSION_TTL_HOURS",
        "CONSOLE_TRUSTED_IDENTITY_HEADER", "CONSOLE_TRUSTED_PROXY_CIDRS", "CONSOLE_STARTUP_TIMEOUT_SECONDS",
        "CONSOLE_ROOT_PATH", "CONSOLE_OPERATOR_API_KEY_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    config = ConsoleConfig(_env_file=None)
    assert config.seller_agent_url == "http://agent.test"
    assert config.console_db_url == "sqlite:///data/console.db"
    assert config.console_session_ttl_hours == 12
    assert config.console_trusted_identity_header == ""
    assert config.proxy_cidrs == []
    assert config.sso is False
    assert config.console_startup_timeout_seconds == 60
    assert config.console_root_path == ""
    assert config.console_operator_api_key_file == ""


def test_required_values():
    with pytest.raises(ValidationError):
        ConsoleConfig(_env_file=None)  # SELLER_AGENT_URL is required
    config = ConsoleConfig(_env_file=None, seller_agent_url="http://agent.test")
    with pytest.raises(RuntimeError, match="CONSOLE_OPERATOR_API_KEY"):
        config.resolved_operator_key()  # neither the variable nor the file


def test_key_file_wins_over_variable(monkeypatch, tmp_path):
    secret = tmp_path / "key"
    secret.write_text("ask_live_from_file\n")
    config = ConsoleConfig(
        _env_file=None, seller_agent_url="http://agent.test",
        console_operator_api_key="ask_live_from_env", console_operator_api_key_file=str(secret),
    )
    assert config.resolved_operator_key() == "ask_live_from_file"
    assert ConsoleConfig(_env_file=None, seller_agent_url="http://agent.test", console_operator_api_key="ask_live_x").resolved_operator_key() == "ask_live_x"


def test_env_and_cidr_parsing(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CONSOLE_TRUSTED_IDENTITY_HEADER", "X-Forwarded-Email")
    monkeypatch.setenv("CONSOLE_TRUSTED_PROXY_CIDRS", "10.0.0.0/8, 127.0.0.1/32")
    monkeypatch.setenv("CONSOLE_SESSION_TTL_HOURS", "2")
    config = ConsoleConfig(_env_file=None)
    assert config.sso is True
    assert config.proxy_cidrs == ["10.0.0.0/8", "127.0.0.1/32"]
    assert config.console_session_ttl_hours == 2


def test_explicit_values_win_over_env(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    config = ConsoleConfig(_env_file=None, console_session_ttl_hours=1, failure_delay_seconds=0)
    assert config.console_session_ttl_hours == 1
    assert config.failure_delay_seconds == 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_config.py -q
```
Expected: `ModuleNotFoundError: No module named 'seller_console.config'`.

- [ ] **Step 3: Implement**

```python
# src/seller_console/config.py
"""Console configuration from environment variables (see README, Settings)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConsoleConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    seller_agent_url: str
    console_operator_api_key: str = ""
    console_db_url: str = "sqlite:///data/console.db"  # development default; the image sets the /data volume path
    console_session_ttl_hours: int = 12
    # SSO mode: this header names the user, required on every request, trusted only from the CIDRs.
    console_trusted_identity_header: str = ""
    console_trusted_proxy_cidrs: str = ""
    console_startup_timeout_seconds: int = 60
    # Behind a proxy prefix (e.g. /console): passed to FastAPI as root_path.
    console_root_path: str = ""
    # A mounted secret file holding the operator key; wins over CONSOLE_OPERATOR_API_KEY.
    console_operator_api_key_file: str = ""
    # Tuning knobs with no documented environment variable; tests set them explicitly.
    failure_delay_seconds: float = 0.3
    api_timeout_seconds: float = 2.0

    @property
    def sso(self) -> bool:
        return bool(self.console_trusted_identity_header)

    @property
    def proxy_cidrs(self) -> list[str]:
        return [c.strip() for c in self.console_trusted_proxy_cidrs.split(",") if c.strip()]

    def resolved_operator_key(self) -> str:
        """The key from the secret file when configured, else the variable; empty is an error."""
        if self.console_operator_api_key_file:
            key = Path(self.console_operator_api_key_file).read_text().strip()
        else:
            key = self.console_operator_api_key.strip()
        if not key:
            raise RuntimeError("CONSOLE_OPERATOR_API_KEY (or CONSOLE_OPERATOR_API_KEY_FILE) is required")
        return key
```

- [ ] **Step 4: Run to verify they pass, then commit**

```bash
uv run pytest tests/test_config.py -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/config.py tests/test_config.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console configuration from the environment"
```
Expected: `5 passed`.

---

## Task 4: The store

**Files:**
- Create: `src/seller_console/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_store.py
"""The console's own key-value store: JSON values, TTL, prefix listing, on SQLite."""

import asyncio

import pytest

from seller_console.store import Store, parse_sqlite_url


def test_url_parsing():
    assert parse_sqlite_url("sqlite:///data/console.db") == "data/console.db"
    assert parse_sqlite_url("sqlite:////data/console.db") == "/data/console.db"
    with pytest.raises(ValueError):
        parse_sqlite_url("postgres://x")


@pytest.fixture
async def store(tmp_path):
    s = Store(f"sqlite:///{tmp_path}/t.db")
    await s.connect()
    yield s
    await s.close()


async def test_round_trip_json(store):
    await store.set("a", {"n": 1, "s": "x"})
    assert await store.get("a") == {"n": 1, "s": "x"}
    assert await store.get("missing") is None
    assert await store.delete("a") is True
    assert await store.delete("a") is False


async def test_ttl_expires(store, monkeypatch):
    await store.set("t", 1, ttl=1)
    assert await store.get("t") == 1
    now = store._now()
    monkeypatch.setattr(store, "_now", lambda: now + 2)
    assert await store.get("t") is None
    assert await store.keys("t*") == []


async def test_keys_by_prefix(store):
    await store.set("rate_limit:user:nicolas:1", 1)
    await store.set("rate_limit:user:nicolas:2", 1)
    await store.set("rate_limit:addr:1.2.3.4:1", 1)
    assert sorted(await store.keys("rate_limit:user:nicolas:*")) == [
        "rate_limit:user:nicolas:1",
        "rate_limit:user:nicolas:2",
    ]


async def test_concurrent_sets_are_all_kept(store):
    await asyncio.gather(*(store.set(f"k:{i}", i, ttl=60) for i in range(20)))
    assert len(await store.keys("k:*")) == 20


async def test_versions_and_compare_and_set(store):
    assert await store.set("a", {"n": 1}) == 1
    assert await store.set("a", {"n": 2}) == 2
    assert await store.get_versioned("a") == ({"n": 2}, 2)
    assert await store.set_if_version("a", {"n": 3}, expected=2) is True
    assert await store.set_if_version("a", {"n": 4}, expected=2) is False  # stale writer loses
    assert await store.get_versioned("a") == ({"n": 3}, 3)
    assert await store.get_versioned("missing") is None
    assert await store.set_if_version("missing", {"n": 1}, expected=1) is False


async def test_compare_and_set_across_two_connections(tmp_path):
    """The CLI and the server open their own connections; a stale write from one must lose."""
    url = f"sqlite:///{tmp_path}/two.db"
    a, b = Store(url), Store(url)
    await a.connect()
    await b.connect()
    try:
        version = await a.set("acct", {"disabled": False})
        assert await b.set_if_version("acct", {"disabled": True}, expected=version) is True
        assert await a.set_if_version("acct", {"disabled": False, "stale": True}, expected=version) is False
        assert (await a.get("acct")) == {"disabled": True}
    finally:
        await a.close()
        await b.close()


async def test_purge_expired_removes_rows(store, monkeypatch):
    await store.set("gone", 1, ttl=1)
    await store.set("kept", 1)
    now = store._now()
    monkeypatch.setattr(store, "_now", lambda: now + 2)
    assert await store.purge_expired() == 1
    assert await store.keys("*") == ["kept"]


async def test_survives_reopen(tmp_path):
    url = f"sqlite:///{tmp_path}/p.db"
    s = Store(url)
    await s.connect()
    await s.set("keep", "me")
    await s.close()
    s2 = Store(url)
    await s2.connect()
    assert await s2.get("keep") == "me"
    await s2.close()
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_store.py -q
```
Expected: `ModuleNotFoundError: No module named 'seller_console.store'`.

- [ ] **Step 3: Implement**

```python
# src/seller_console/store.py
"""The console's key-value store: accounts, sessions, CSRF tokens, and rate-limit records.

The agent's generic shape (get, set with TTL, delete, keys by pattern) plus a
version on every row and a compare-and-set write, so the CLI and the server, on
separate connections, cannot overwrite each other's changes. A Redis implementation
of the same interface (WATCH/MULTI for the compare-and-set) can replace it for
multi-instance deployments.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite


def parse_sqlite_url(url: str) -> str:
    if not url.startswith("sqlite:///"):
        raise ValueError(f"CONSOLE_DB_URL must be a sqlite:/// URL, got {url!r}")
    return url[len("sqlite:///") :]


class Store:
    def __init__(self, url: str) -> None:
        self._path = parse_sqlite_url(url)
        self._db: Optional[aiosqlite.Connection] = None

    @staticmethod
    def _now() -> float:
        return time.time()

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._path, timeout=5)  # wait for a concurrent writer, never fail fast
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(
            "CREATE TABLE IF NOT EXISTS kv ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL,"
            " version INTEGER NOT NULL DEFAULT 1, expires_at REAL)"
        )
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_kv_expires ON kv(expires_at)")
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("store not connected")
        return self._db

    async def get(self, key: str) -> Optional[Any]:
        async with self._conn().execute(
            "SELECT value, expires_at FROM kv WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at is not None and expires_at <= self._now():
            return None
        return json.loads(value)

    async def get_versioned(self, key: str) -> Optional[tuple[Any, int]]:
        """The value and the store version to hand back to ``set_if_version``."""
        async with self._conn().execute(
            "SELECT value, version, expires_at FROM kv WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        value, version, expires_at = row
        if expires_at is not None and expires_at <= self._now():
            return None
        return json.loads(value), version

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> int:
        """Unconditional write. Every write increments the version; the new version is returned."""
        expires_at = self._now() + ttl if ttl else None
        async with self._conn().execute(
            "INSERT INTO kv (key, value, version, expires_at) VALUES (?, ?, 1, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " version = kv.version + 1, expires_at = excluded.expires_at"
            " RETURNING version",
            (key, json.dumps(value), expires_at),
        ) as cursor:
            (version,) = await cursor.fetchone()
        await self._conn().commit()
        return version

    async def set_if_version(self, key: str, value: Any, expected: int, ttl: Optional[int] = None) -> bool:
        """Compare-and-set: write only if the stored version is ``expected``. One statement, so atomic."""
        expires_at = self._now() + ttl if ttl else None
        cursor = await self._conn().execute(
            "UPDATE kv SET value = ?, version = version + 1, expires_at = ?"
            " WHERE key = ? AND version = ? AND (expires_at IS NULL OR expires_at > ?)",
            (json.dumps(value), expires_at, key, expected, self._now()),
        )
        await self._conn().commit()
        return cursor.rowcount == 1

    async def purge_expired(self) -> int:
        cursor = await self._conn().execute(
            "DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at <= ?", (self._now(),)
        )
        await self._conn().commit()
        return cursor.rowcount

    async def delete(self, key: str) -> bool:
        cursor = await self._conn().execute("DELETE FROM kv WHERE key = ?", (key,))
        await self._conn().commit()
        return cursor.rowcount > 0

    async def keys(self, pattern: str = "*") -> list[str]:
        like = pattern.replace("%", "\\%").replace("_", "\\_").replace("*", "%").replace("?", "_")
        async with self._conn().execute(
            "SELECT key FROM kv WHERE key LIKE ? ESCAPE '\\' AND (expires_at IS NULL OR expires_at > ?)",
            (like, self._now()),
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]
```

- [ ] **Step 4: Run to verify they pass, then commit**

```bash
uv run pytest tests/test_store.py -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/store.py tests/test_store.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: SQLite key-value store with TTL for the console"
```
Expected: `9 passed`. Revert checks: drop the `expires_at` comparison in `get`: `test_ttl_expires` must fail; drop `AND version = ?` from `set_if_version`: the two compare-and-set tests must fail. Restore.

---

## Task 5: Accounts and password hashing

**Files:**
- Create: `src/seller_console/accounts.py`
- Create: `tests/conftest.py` (first fixtures)
- Test: `tests/test_accounts.py`

- [ ] **Step 1: Write the first fixtures**

```python
# tests/conftest.py
"""Fixtures: the console's own store, and the pinned agent app with a real operator key.

The agent is a test-only dependency. Its key service mints the console key into a
SQLite backend of its own, and ``get_storage`` is patched so the agent's routes read
that backend. The console's store is separate, as in production.
"""

from unittest.mock import patch

import pytest

from seller_console.store import Store


@pytest.fixture
async def store(tmp_path):
    s = Store(f"sqlite:///{tmp_path}/console.db")
    await s.connect()
    yield s
    await s.close()


@pytest.fixture
async def agent_storage(tmp_path):
    from ad_seller.storage.sqlite_backend import SQLiteBackend

    backend = SQLiteBackend(f"sqlite:///{tmp_path}/agent.db")
    await backend.connect()
    with patch("ad_seller.storage.factory.get_storage", return_value=backend):
        yield backend
    await backend.disconnect()


@pytest.fixture
async def console_key(agent_storage):
    """Raw operator key labelled 'console' plus its key_id, as (key, key_id)."""
    from ad_seller.auth.api_key_service import ApiKeyService
    from ad_seller.models.api_key import OperatorApiKeyCreateRequest

    created = await ApiKeyService(agent_storage).create_operator_key(
        OperatorApiKeyCreateRequest(label="console")
    )
    return created.api_key, created.key_id
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_accounts.py
"""Console accounts: self-describing scrypt hashes, constant-shape credential checks, CLI-only lifecycle."""

import pytest

from seller_console import accounts
from seller_console.store import Store


def test_hash_is_self_describing_scrypt_at_owasp_parameters():
    stored = accounts.hash_password("correct horse battery")
    algo, log_n, r, p, salt_hex, hash_hex = stored.split("$")
    assert (algo, log_n, r, p) == ("scrypt", "17", "8", "1")
    assert len(bytes.fromhex(salt_hex)) == 16
    assert len(bytes.fromhex(hash_hex)) == 32
    assert accounts.verify_password("correct horse battery", stored) == (True, False)
    assert accounts.verify_password("wrong horse battery", stored) == (False, False)


def test_weaker_parameters_verify_but_ask_for_rehash():
    legacy = accounts.hash_password("correct horse battery", log_n=14)
    assert legacy.startswith("scrypt$14$8$1$")
    assert accounts.verify_password("correct horse battery", legacy) == (True, True)


def test_garbage_hash_never_verifies():
    assert accounts.verify_password("anything at all", "not$a$hash") == (False, False)


async def test_create_and_get_account(store):
    account = await accounts.create_account(store, "nicolas", "correct horse battery")
    assert account.username == "nicolas"
    assert account.role == "operator"
    assert account.disabled is False
    stored = await store.get("console_user:nicolas")
    assert "correct horse battery" not in str(stored)
    assert set(stored) == {
        "username", "password_hash", "role", "disabled", "credential_version",
        "created_at", "last_login_at", "credentials_changed_at",
    }
    assert stored["password_hash"].startswith("scrypt$17$8$1$")
    assert account.credential_version == 1
    assert (await accounts.get_account(store, "nicolas")).username == "nicolas"
    assert await accounts.get_account(store, "nobody") is None


async def test_short_password_rejected(store):
    with pytest.raises(ValueError, match="12 characters"):
        await accounts.create_account(store, "nicolas", "short")


async def test_bad_username_rejected(store):
    with pytest.raises(ValueError, match="username"):
        await accounts.create_account(store, "nic olas", "correct horse battery")


async def test_duplicate_username_rejected(store):
    await accounts.create_account(store, "nicolas", "correct horse battery")
    with pytest.raises(ValueError, match="exists"):
        await accounts.create_account(store, "nicolas", "another long password")


async def test_login_rehashes_a_weaker_stored_hash(store):
    created = await accounts.create_account(store, "nicolas", "correct horse battery")
    record = await store.get("console_user:nicolas")
    record["password_hash"] = accounts.hash_password("correct horse battery", log_n=14)
    await store.set("console_user:nicolas", record)
    assert await accounts.check_credentials(store, "nicolas", "correct horse battery") is not None
    upgraded = await store.get("console_user:nicolas")
    assert upgraded["password_hash"].startswith("scrypt$17$8$1$")
    assert upgraded["credential_version"] == created.credential_version  # a rehash is not a credential change


async def test_check_credentials(store):
    await accounts.create_account(store, "nicolas", "correct horse battery")
    assert await accounts.check_credentials(store, "nicolas", "wrong horse battery") is None
    assert await accounts.check_credentials(store, "nobody", "correct horse battery") is None
    ok = await accounts.check_credentials(store, "nicolas", "correct horse battery")
    assert ok is not None and ok.username == "nicolas"
    assert (await store.get("console_user:nicolas"))["last_login_at"] is not None


async def test_disabled_account_cannot_log_in(store):
    created = await accounts.create_account(store, "nicolas", "correct horse battery")
    assert await accounts.set_disabled(store, "nicolas", True) is True
    bumped = await accounts.get_account(store, "nicolas")
    assert bumped.credential_version == created.credential_version + 1
    assert await accounts.check_credentials(store, "nicolas", "correct horse battery") is None
    assert await accounts.set_disabled(store, "nobody", True) is False


async def test_disable_during_login_is_not_undone(store, tmp_path, monkeypatch):
    """The CLI disables the account while the server is still hashing: the login must refuse
    and must not write the pre-disable record back."""
    import asyncio

    await accounts.create_account(store, "nicolas", "correct horse battery")
    hashing = asyncio.Event()
    release = asyncio.Event()
    real_verify = accounts._verify

    async def paused_verify(password, stored):
        hashing.set()
        await release.wait()
        return await real_verify(password, stored)

    monkeypatch.setattr(accounts, "_verify", paused_verify)
    login = asyncio.create_task(accounts.check_credentials(store, "nicolas", "correct horse battery"))
    await hashing.wait()
    cli = Store(f"sqlite:///{tmp_path}/console.db")  # the CLI's own connection
    await cli.connect()
    try:
        assert await accounts.set_disabled(cli, "nicolas", True) is True
    finally:
        await cli.close()
    release.set()
    assert await login is None
    assert (await accounts.get_account(store, "nicolas")).disabled is True


async def test_reset_during_login_issues_no_stale_success(store, tmp_path, monkeypatch):
    import asyncio

    created = await accounts.create_account(store, "nicolas", "correct horse battery")
    hashing, release = asyncio.Event(), asyncio.Event()
    real_verify = accounts._verify

    async def paused_verify(password, stored):
        hashing.set()
        await release.wait()
        return await real_verify(password, stored)

    monkeypatch.setattr(accounts, "_verify", paused_verify)
    login = asyncio.create_task(accounts.check_credentials(store, "nicolas", "correct horse battery"))
    await hashing.wait()
    cli = Store(f"sqlite:///{tmp_path}/console.db")
    await cli.connect()
    try:
        assert await accounts.reset_password(cli, "nicolas", "new horse battery staple") is True
    finally:
        await cli.close()
    release.set()
    assert await login is None  # the old password no longer opens the account
    assert (await accounts.get_account(store, "nicolas")).credential_version == created.credential_version + 1


async def test_two_logins_at_once_both_succeed(store):
    """A benign concurrent change (the other login's last_login_at) is retried, not refused."""
    import asyncio

    await accounts.create_account(store, "nicolas", "correct horse battery")
    results = await asyncio.gather(
        accounts.check_credentials(store, "nicolas", "correct horse battery"),
        accounts.check_credentials(store, "nicolas", "correct horse battery"),
    )
    assert all(r is not None for r in results)


async def test_reset_password(store):
    created = await accounts.create_account(store, "nicolas", "correct horse battery")
    assert await accounts.reset_password(store, "nicolas", "new horse battery staple") is True
    assert (await accounts.get_account(store, "nicolas")).credential_version == created.credential_version + 1
    assert await accounts.check_credentials(store, "nicolas", "correct horse battery") is None
    assert await accounts.check_credentials(store, "nicolas", "new horse battery staple") is not None
    assert await accounts.reset_password(store, "nobody", "new horse battery staple") is False
```

- [ ] **Step 3: Run to verify they fail**

```bash
uv run pytest tests/test_accounts.py -q
```
Expected: `ModuleNotFoundError: No module named 'seller_console.accounts'`.

- [ ] **Step 4: Implement**

```python
# src/seller_console/accounts.py
"""Console accounts: username plus a self-describing scrypt hash in the console's store.

Accounts are created, reset, and disabled only through the CLI. There are no
account routes. ``credential_version`` is incremented by every disable, enable,
password reset, or role change; a session is valid only while it carries the
account's current version (see auth.py). Every write is a compare-and-set.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Awaitable, Callable, Optional

from .store import Store

ACCOUNT_PREFIX = "console_user:"
_CAS_RETRIES = 3
# scrypt at N=2^17 needs 128 MiB and ~0.3 s; run it off the event loop and at most four at once.
_HASHING = asyncio.Semaphore(4)
MIN_PASSWORD_LENGTH = 12
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
# OWASP password storage minimum for scrypt: N=2^17, r=8, p=1 (128 MiB, ~0.3 s).
# The stored string carries its parameters, so raising them later only needs a
# rehash on the next successful login, never a migration.
_LOG_N, _R, _P = 17, 8, 1
_DKLEN = 32
_MAXMEM = 256 * 2**20  # hashlib's default 32 MiB cap is below what N=2^17 needs


@dataclass
class Account:
    username: str
    role: str
    disabled: bool
    credential_version: int
    created_at: str
    last_login_at: Optional[str]
    credentials_changed_at: str


def _scrypt(password: str, salt: bytes, log_n: int, r: int, p: int) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**log_n, r=r, p=p, dklen=_DKLEN, maxmem=_MAXMEM
    ).hex()


def hash_password(password: str, *, log_n: int = _LOG_N, r: int = _R, p: int = _P) -> str:
    """Self-describing hash: ``scrypt$<log2 N>$<r>$<p>$<salt hex>$<hash hex>``."""
    salt = secrets.token_bytes(16)
    return "$".join(["scrypt", str(log_n), str(r), str(p), salt.hex(), _scrypt(password, salt, log_n, r, p)])


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (matches, needs_rehash). Unparseable input never matches."""
    try:
        algo, log_n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False, False
        log_n, r, p = int(log_n), int(r), int(p)
        candidate = _scrypt(password, bytes.fromhex(salt_hex), log_n, r, p)
    except (ValueError, TypeError):
        return False, False
    matches = hmac.compare_digest(candidate, hash_hex)
    weaker = (log_n, r, p) < (_LOG_N, _R, _P)
    return matches, matches and weaker


@lru_cache(maxsize=1)
def _dummy_record() -> dict[str, Any]:
    """Hashed against when the username does not exist, so the failure path always costs one scrypt."""
    return {"password_hash": hash_password("no such account"), "disabled": True}


async def _verify(password: str, stored: str) -> tuple[bool, bool]:
    async with _HASHING:
        return await asyncio.to_thread(verify_password, password, stored)


async def _hash(password: str) -> str:
    async with _HASHING:
        return await asyncio.to_thread(hash_password, password)


async def _update(store: Store, username: str, change: Callable[[dict[str, Any]], Awaitable[Optional[dict[str, Any]]]]) -> Optional[dict[str, Any]]:
    """Compare-and-set loop: read the record with its version, let ``change`` produce the new
    record (or None to give up), write it only if nobody wrote in between, else retry."""
    key = ACCOUNT_PREFIX + username
    for _ in range(_CAS_RETRIES):
        found = await store.get_versioned(key)
        if found is None:
            return None
        record, version = found
        updated = await change(dict(record))
        if updated is None:
            return None
        if await store.set_if_version(key, updated, expected=version):
            return updated
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_account(record: dict[str, Any]) -> Account:
    return Account(
        username=record["username"],
        role=record["role"],
        disabled=bool(record["disabled"]),
        credential_version=int(record["credential_version"]),
        created_at=record["created_at"],
        last_login_at=record.get("last_login_at"),
        credentials_changed_at=record["credentials_changed_at"],
    )


def _validate(username: str, password: str) -> None:
    if not _USERNAME_RE.match(username or ""):
        raise ValueError("username must be 1-64 characters of letters, digits, '.', '_', '@' or '-'")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


async def create_account(store: Store, username: str, password: str) -> Account:
    _validate(username, password)
    if await store.get(ACCOUNT_PREFIX + username) is not None:
        raise ValueError(f"account {username!r} already exists")
    record = {
        "username": username,
        "password_hash": hash_password(password),
        "role": "operator",
        "disabled": False,
        "credential_version": 1,
        "created_at": _now(),
        "last_login_at": None,
        "credentials_changed_at": _now(),
    }
    await store.set(ACCOUNT_PREFIX + username, record)
    return _to_account(record)


async def get_account(store: Store, username: str) -> Optional[Account]:
    record = await store.get(ACCOUNT_PREFIX + username)
    return _to_account(record) if record else None


async def check_credentials(store: Store, username: str, password: str) -> Optional[Account]:
    """Return the account when username and password match and it is enabled.

    The expensive hash runs outside the compare-and-set; if the account changed while
    hashing (disable, reset, role change), the write is refused and the change is
    re-evaluated against the fresh record. A benign concurrent change (another login's
    last_login_at) is retried; a real one (the hash or version differs) refuses.
    """
    if not username:
        await _verify(password, _dummy_record()["password_hash"])
        return None
    found = await store.get_versioned(ACCOUNT_PREFIX + username)
    record = found[0] if found else _dummy_record()
    ok, needs_rehash = await _verify(password, record["password_hash"])
    if found is None or not ok or record["disabled"]:
        return None
    seen_hash, seen_version = record["password_hash"], record["credential_version"]
    new_hash = await _hash(password) if needs_rehash else None

    async def change(current: dict[str, Any]) -> Optional[dict[str, Any]]:
        if current["disabled"] or current["password_hash"] != seen_hash or current["credential_version"] != seen_version:
            return None  # the account changed under us: refuse, never write the stale record back
        if new_hash is not None:
            current["password_hash"] = new_hash  # not a credential change
        current["last_login_at"] = _now()
        return current

    updated = await _update(store, username, change)
    return _to_account(updated) if updated else None


async def _bump(store: Store, username: str, mutate: Callable[[dict[str, Any]], None]) -> bool:
    async def change(current: dict[str, Any]) -> dict[str, Any]:
        mutate(current)
        current["credential_version"] = int(current["credential_version"]) + 1
        current["credentials_changed_at"] = _now()
        return current

    return await _update(store, username, change) is not None


async def set_disabled(store: Store, username: str, disabled: bool) -> bool:
    return await _bump(store, username, lambda r: r.__setitem__("disabled", disabled))


async def reset_password(store: Store, username: str, password: str) -> bool:
    _validate(username, password)
    new_hash = await _hash(password)
    return await _bump(store, username, lambda r: r.__setitem__("password_hash", new_hash))
```

- [ ] **Step 5: Run to verify they pass, then commit**

```bash
uv run pytest tests/test_accounts.py -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/accounts.py tests/conftest.py tests/test_accounts.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console accounts with self-describing scrypt hashes"
```
Expected: `14 passed` in about 20 seconds (scrypt at N=2^17 costs about a third of a second per call, which is the point). Revert checks: `hmac.compare_digest(...)` → `True`: the first and `test_check_credentials` must fail; `_LOG_N = 14`: the first and the rehash test must fail; replace `set_if_version` with `set` in `check_credentials`: `test_disable_during_login_is_not_undone` must fail. Restore.

---

## Task 6: CLI `seller-console create-user`

**Files:**
- Create: `src/seller_console/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
"""seller-console create-user: the only way to manage console accounts."""

import asyncio

from typer.testing import CliRunner

from seller_console import accounts
from seller_console.cli import app as cli
from seller_console.store import Store

runner = CliRunner()


def _env(tmp_path):
    return {"CONSOLE_DB_URL": f"sqlite:///{tmp_path}/cli.db"}


async def _account(tmp_path, name):
    s = Store(f"sqlite:///{tmp_path}/cli.db")
    await s.connect()
    try:
        return await accounts.get_account(s, name)
    finally:
        await s.close()


async def _check(tmp_path, name, password):
    s = Store(f"sqlite:///{tmp_path}/cli.db")
    await s.connect()
    try:
        return await accounts.check_credentials(s, name, password)
    finally:
        await s.close()


def test_create_user_prompts_for_password(tmp_path):
    result = runner.invoke(
        cli, ["create-user", "--username", "nicolas"],
        input="correct horse battery\ncorrect horse battery\n", env=_env(tmp_path),
    )
    assert result.exit_code == 0, result.output
    assert "nicolas" in result.output
    assert "correct horse battery" not in result.output
    assert asyncio.run(_account(tmp_path, "nicolas")) is not None


def test_create_user_rejects_short_password(tmp_path):
    result = runner.invoke(cli, ["create-user", "--username", "nicolas"], input="short\nshort\n", env=_env(tmp_path))
    assert result.exit_code == 1
    assert "12 characters" in result.output


def test_reset_password_flag(tmp_path):
    runner.invoke(cli, ["create-user", "--username", "nicolas"], input="correct horse battery\ncorrect horse battery\n", env=_env(tmp_path))
    result = runner.invoke(
        cli, ["create-user", "--username", "nicolas", "--reset-password"],
        input="new horse battery staple\nnew horse battery staple\n", env=_env(tmp_path),
    )
    assert result.exit_code == 0, result.output
    assert asyncio.run(_check(tmp_path, "nicolas", "new horse battery staple")) is not None


def test_disable_flag(tmp_path):
    runner.invoke(cli, ["create-user", "--username", "nicolas"], input="correct horse battery\ncorrect horse battery\n", env=_env(tmp_path))
    result = runner.invoke(cli, ["create-user", "--username", "nicolas", "--disable"], env=_env(tmp_path))
    assert result.exit_code == 0, result.output
    assert asyncio.run(_account(tmp_path, "nicolas")).disabled is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_cli.py -q
```
Expected: `ModuleNotFoundError: No module named 'seller_console.cli'`.

- [ ] **Step 3: Implement**

```python
# src/seller_console/cli.py
"""Host-side account management. The store URL comes from CONSOLE_DB_URL, as for the server."""

from __future__ import annotations

import asyncio
import os

import typer

from . import accounts
from .store import Store

app = typer.Typer(name="seller-console", help="Seller Agent Console administration")
DEFAULT_DB_URL = "sqlite:///data/console.db"


async def _with_store(action):
    store = Store(os.environ.get("CONSOLE_DB_URL", DEFAULT_DB_URL))
    await store.connect()
    try:
        return await action(store)
    finally:
        await store.close()


@app.command("create-user")
def create_user(
    username: str = typer.Option(..., "--username", "-u", help="Console login name"),
    reset_password: bool = typer.Option(False, "--reset-password", help="Set a new password for an existing account"),
    disable: bool = typer.Option(False, "--disable", help="Disable an existing account"),
) -> None:
    """Create a console account, or reset its password, or disable it.

    Passwords are prompted, never passed as arguments, and stored as scrypt hashes.
    """
    try:
        if disable:
            found = asyncio.run(_with_store(lambda s: accounts.set_disabled(s, username, True)))
            if not found:
                typer.echo(f"No console account named {username!r}", err=True)
                raise typer.Exit(1)
            typer.echo(f"Console account {username} disabled")
            return
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
        if reset_password:
            found = asyncio.run(_with_store(lambda s: accounts.reset_password(s, username, password)))
            if not found:
                typer.echo(f"No console account named {username!r}", err=True)
                raise typer.Exit(1)
            typer.echo(f"Password reset for {username}")
            return
        account = asyncio.run(_with_store(lambda s: accounts.create_account(s, username, password)))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Console account created: {account.username} ({account.role}). Sign in at /login.")


def main() -> None:
    app()
```

- [ ] **Step 4: Run to verify they pass, then commit**

```bash
uv run pytest tests/test_cli.py -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/cli.py tests/test_cli.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: seller-console create-user"
```
Expected: `4 passed`. Typer's `CliRunner` mixes stderr into `output` by default, which the short-password test relies on.

---

## Task 7: Sessions, rate limit, and `current_operator`

**Files:**
- Create: `src/seller_console/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_auth.py
"""Sessions are opaque tokens in the store; current_operator is the only cookie and header reader."""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import Depends, FastAPI
from httpx import ASGITransport

from seller_console import accounts, auth
from seller_console.config import ConsoleConfig


def _config(**kw) -> ConsoleConfig:
    base = dict(seller_agent_url="http://agent.test", console_operator_api_key="k", failure_delay_seconds=0)
    return ConsoleConfig(_env_file=None, **{**base, **kw})


async def test_session_round_trip(store):
    token, expires_at = await auth.create_session(store, "nicolas", "operator", 1, ttl_hours=1)
    assert len(token) >= 40
    assert expires_at > datetime.now(timezone.utc) + timedelta(minutes=59)
    record = await store.get(auth.SESSION_PREFIX + token)
    assert set(record) == {"username", "role", "credential_version", "created_at", "expires_at"}
    assert record["credential_version"] == 1
    assert (await auth.load_session(store, token))["username"] == "nicolas"
    await auth.delete_session(store, token)
    assert await auth.load_session(store, token) is None
    assert await auth.load_session(store, "nonsense") is None


async def test_attempts_are_reserved_before_they_are_counted(store):
    counts = [(await auth.reserve_attempt(store, "nicolas", "10.0.0.1"))[0] for _ in range(3)]
    assert counts == [1, 2, 3]  # the attempt itself is included: recording precedes admission
    assert await auth.failures(store, "nicolas", "10.0.0.2") == 3  # per username
    assert await auth.failures(store, "other", "10.0.0.1") == 3  # per address


async def test_concurrent_attempts_cannot_all_pass_the_boundary(store):
    """Ten attempts at once: at most five see a count within the limit."""
    results = await asyncio.gather(*(auth.reserve_attempt(store, "nicolas", "10.0.0.1") for _ in range(10)))
    admitted = [count for count, _ in results if count <= auth.RATE_LIMIT_MAX]
    assert len(admitted) <= auth.RATE_LIMIT_MAX
    assert await auth.failures(store, "nicolas", "10.0.0.1") == 10


async def test_success_releases_its_own_attempt_and_the_user_budget_only(store):
    for _ in range(3):
        await auth.reserve_attempt(store, "other", "10.0.0.1")  # someone else failing from the same address
    count, stamp = await auth.reserve_attempt(store, "nicolas", "10.0.0.1")
    assert count == 4  # the address scope already had three
    await auth.release_attempt(store, "nicolas", "10.0.0.1", stamp)
    await auth.clear_user_failures(store, "nicolas")
    assert await auth.failures(store, "nicolas", "10.0.0.9") == 0  # the user's budget is clean
    assert await auth.failures(store, "other", "10.0.0.1") == 3  # the address budget is untouched


def _app_with_operator_route(config: ConsoleConfig, store) -> FastAPI:
    """A sub-application mounted at /console so root_path is set, as behind a proxy prefix."""
    sub = FastAPI()
    sub.state.console = auth.ConsoleState(config=config, api=None, store=store)

    @sub.get("/whoami")
    async def whoami(operator: auth.Operator = Depends(auth.current_operator)):
        return {"username": operator.username, "role": operator.role}

    app = FastAPI()
    app.mount("/console", sub)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_no_cookie_redirects_page_requests(store):
    app = _app_with_operator_route(_config(), store)
    response = await _client(app).get("/console/whoami")
    assert response.status_code == 303
    assert response.headers["location"] == "/console/login?next=%2Fconsole%2Fwhoami"


async def test_no_cookie_tells_htmx_to_redirect(store):
    app = _app_with_operator_route(_config(), store)
    response = await _client(app).get("/console/whoami", headers={"HX-Request": "true"})
    assert response.status_code == 401
    assert response.headers["hx-redirect"] == "/console/login?next=%2Fconsole%2Fwhoami"


async def test_valid_cookie_resolves_operator(store):
    await accounts.create_account(store, "nicolas", "correct horse battery")
    app = _app_with_operator_route(_config(), store)
    token, _ = await auth.create_session(store, "nicolas", "operator", 1, ttl_hours=1)
    response = await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})
    assert response.status_code == 200
    assert response.json() == {"username": "nicolas", "role": "operator"}


async def test_disabling_the_account_kills_an_issued_session(store):
    await accounts.create_account(store, "nicolas", "correct horse battery")
    app = _app_with_operator_route(_config(), store)
    token, _ = await auth.create_session(store, "nicolas", "operator", 1, ttl_hours=1)
    client = _client(app)
    assert (await client.get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 200
    await accounts.set_disabled(store, "nicolas", True)
    assert (await client.get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 303
    assert await auth.load_session(store, token) is None


async def test_password_reset_kills_an_issued_session(store):
    await accounts.create_account(store, "nicolas", "correct horse battery")
    app = _app_with_operator_route(_config(), store)
    token, _ = await auth.create_session(store, "nicolas", "operator", 1, ttl_hours=1)
    await accounts.reset_password(store, "nicolas", "new horse battery staple")
    assert (await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 303


async def test_session_with_a_stale_version_is_dead_even_if_newer(store):
    """Equality on the exact version: a session issued under version 1 dies at version 2,
    whatever the timestamps say."""
    await accounts.create_account(store, "nicolas", "correct horse battery")
    await accounts.reset_password(store, "nicolas", "new horse battery staple")  # now version 2
    app = _app_with_operator_route(_config(), store)
    token, _ = await auth.create_session(store, "nicolas", "operator", 1, ttl_hours=1)
    assert (await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 303


async def test_deleted_account_kills_an_issued_session(store):
    app = _app_with_operator_route(_config(), store)
    token, _ = await auth.create_session(store, "ghost", "operator", 1, ttl_hours=1)
    assert (await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 303


def _sso_app(store, cidrs):
    return _app_with_operator_route(
        _config(console_trusted_identity_header="X-Forwarded-Email", console_trusted_proxy_cidrs=",".join(cidrs)),
        store,
    )


async def test_sso_accepts_header_from_trusted_proxy(store):
    await accounts.create_account(store, "nicolas@example.com", "correct horse battery")
    app = _sso_app(store, ["127.0.0.1/32"])  # httpx's ASGI transport reports client 127.0.0.1
    ok = await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "nicolas@example.com"})
    assert ok.status_code == 200
    assert ok.json()["username"] == "nicolas@example.com"


async def test_sso_rejects_header_from_untrusted_address(store):
    await accounts.create_account(store, "nicolas@example.com", "correct horse battery")
    app = _sso_app(store, ["10.0.0.0/8"])
    assert (await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "nicolas@example.com"})).status_code == 403


async def test_sso_requires_header_and_ignores_cookies(store):
    await accounts.create_account(store, "nicolas@example.com", "correct horse battery")
    app = _sso_app(store, ["127.0.0.1/32"])
    token, _ = await auth.create_session(store, "nicolas@example.com", "operator", 1, ttl_hours=1)
    assert (await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 403
    assert (await _client(app).get("/console/whoami")).status_code == 403


async def test_sso_rejects_unknown_and_disabled_identities(store):
    await accounts.create_account(store, "gone@example.com", "correct horse battery")
    await accounts.set_disabled(store, "gone@example.com", True)
    app = _sso_app(store, ["127.0.0.1/32"])
    assert (await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "stranger@example.com"})).status_code == 403
    assert (await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "gone@example.com"})).status_code == 403


def test_safe_next_only_allows_paths_under_the_mount():
    assert auth.safe_next("/deals", "") == "/deals"
    assert auth.safe_next("//evil", "") == "/"
    assert auth.safe_next("https://evil.example/", "") == "/"
    assert auth.safe_next(None, "") == "/"
    assert auth.safe_next("/console/deals", "/console") == "/console/deals"
    assert auth.safe_next("/api/v1/deals", "/console") == "/console/"


async def test_paths_follow_the_mount_prefix(store):
    await accounts.create_account(store, "nicolas", "correct horse battery")
    outer = FastAPI()
    outer.mount("/agent", _app_with_operator_route(_config(), store))
    response = await _client(outer).get("/agent/console/whoami")
    assert response.status_code == 303
    assert response.headers["location"] == "/agent/console/login?next=%2Fagent%2Fconsole%2Fwhoami"
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_auth.py -q
```
Expected: `ModuleNotFoundError: No module named 'seller_console.auth'`.

- [ ] **Step 3: Implement**

```python
# src/seller_console/auth.py
"""Sessions, CSRF cookie name, login rate limit, and the ``current_operator`` dependency.

``current_operator`` is the only code that reads the session cookie or the trusted
identity header. Screens depend on it and never learn how the person logged in.
A session record never holds a key or a password.
"""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException, Request, Response

from .accounts import get_account
from .config import ConsoleConfig
from .store import Store

SESSION_COOKIE = "console_session"
SESSION_PREFIX = "session:"
CSRF_PREFIX = "csrf:"
CSRF_TTL_SECONDS = 3600
ANONYMOUS = "anonymous"
RATE_PREFIX = "rate_limit:"
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 600


@dataclass
class ConsoleState:
    """What the app carries on ``app.state.console``."""

    config: ConsoleConfig
    api: Any  # ConsoleApi; typed loosely so auth.py does not import client.py
    store: Store


@dataclass
class Operator:
    username: str
    role: str
    session_expires_at: Optional[datetime] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def root(request: Request) -> str:
    """The mount prefix ("" at the origin root, "/console" behind a prefix); never hardcode it."""
    return request.scope.get("root_path", "").rstrip("/")


def login_path(request: Request) -> str:
    return root(request) + "/login"


async def create_session(store: Store, username: str, role: str, credential_version: int, *, ttl_hours: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    created = _now()
    expires_at = created + timedelta(hours=ttl_hours)
    await store.set(
        SESSION_PREFIX + token,
        {
            "username": username,
            "role": role,
            "credential_version": credential_version,
            "created_at": created.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        ttl=ttl_hours * 3600,
    )
    return token, expires_at


async def load_session(store: Store, token: str) -> Optional[dict[str, Any]]:
    record = await store.get(SESSION_PREFIX + token)
    if not record or datetime.fromisoformat(record["expires_at"]) <= _now():
        return None
    return record


async def delete_session(store: Store, token: str) -> None:
    await store.delete(SESSION_PREFIX + token)


async def issue_csrf_token(store: Store, owner: str) -> str:
    """A fresh one-hour token, server-stored and bound to its owner (a username or ANONYMOUS)."""
    token = secrets.token_urlsafe(32)
    await store.set(CSRF_PREFIX + token, {"owner": owner}, ttl=CSRF_TTL_SECONDS)
    return token


async def consume_csrf_token(store: Store, token: str, owner: str) -> bool:
    """Single use: the token must exist, belong to ``owner``, and is deleted on success."""
    if not token:
        return False
    record = await store.get(CSRF_PREFIX + token)
    if not record or record.get("owner") != owner:
        return False
    return await store.delete(CSRF_PREFIX + token)


def _rate_scopes(username: str, address: str) -> tuple[str, str]:
    return f"{RATE_PREFIX}user:{username}:", f"{RATE_PREFIX}addr:{address}:"


async def failures(store: Store, username: str, address: str) -> int:
    """Live attempts in the window, the larger of the username and address scopes."""
    return max(len(await store.keys(scope + "*")) for scope in _rate_scopes(username, address))


async def reserve_attempt(store: Store, username: str, address: str) -> tuple[int, str]:
    """Record this attempt first, then count. Returns (count including this attempt, stamp).

    Recording before admission is what stops N concurrent attempts from all seeing
    N-1 and passing; each attempt is its own TTL row, so there is no read-modify-write.
    """
    await store.purge_expired()
    stamp = secrets.token_hex(8)
    for scope in _rate_scopes(username, address):
        await store.set(scope + stamp, 1, ttl=RATE_LIMIT_WINDOW_SECONDS)
    return await failures(store, username, address), stamp


async def release_attempt(store: Store, username: str, address: str, stamp: str) -> None:
    """A successful attempt does not count against anyone: remove its own two rows only."""
    for scope in _rate_scopes(username, address):
        await store.delete(scope + stamp)


async def clear_user_failures(store: Store, username: str) -> None:
    """After a successful login the username's budget resets; the address's never does here."""
    for key in await store.keys(_rate_scopes(username, "")[0] + "*"):
        await store.delete(key)


def safe_next(value: Optional[str], root_path: str) -> str:
    """Only relative paths under the mount may be redirect targets."""
    home = root_path + "/"
    if value and value.startswith(home) and "//" not in value:
        return value
    return home


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def is_secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "") == "https"


def login_url(request: Request) -> str:
    return f"{login_path(request)}?next={quote(safe_next(request.url.path, root(request)), safe='')}"


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def cookie_path(request: Request) -> str:
    return root(request) or "/"


def set_session_cookie(response: Response, request: Request, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="lax",
        secure=is_secure(request), path=cookie_path(request),
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path=cookie_path(request))


def from_trusted_proxy(request: Request, cidrs: list[str]) -> bool:
    try:
        ip = ipaddress.ip_address(client_address(request))
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


async def _sso_operator(request: Request, state: ConsoleState) -> Operator:
    """SSO mode: the header is required on every request; cookies are never consulted."""
    if not from_trusted_proxy(request, state.config.proxy_cidrs):
        raise HTTPException(status_code=403, detail="Console requests must come through the identity proxy")
    identity = request.headers.get(state.config.console_trusted_identity_header)
    if not identity:
        raise HTTPException(status_code=403, detail="Identity header missing")
    account = await get_account(state.store, identity)
    if account is None or account.disabled:
        raise HTTPException(status_code=403, detail="No console account for this identity")
    return Operator(username=account.username, role=account.role)


async def current_operator(request: Request) -> Operator:
    state: ConsoleState = request.app.state.console
    if state.config.sso:
        return await _sso_operator(request, state)

    token = request.cookies.get(SESSION_COOKIE)
    session = await load_session(state.store, token) if token else None
    account = await get_account(state.store, session["username"]) if session else None
    if session is not None and (
        account is None
        or account.disabled
        or int(session["credential_version"]) != account.credential_version
    ):
        # The account changed under the session (disabled, reset, role change): the session is dead.
        # Exact equality, not "issued before the change": a session issued in the same instant as a
        # reset cannot survive it.
        await delete_session(state.store, token)
        session = None
    if session is None:
        url = login_url(request)
        if is_htmx(request):
            raise HTTPException(status_code=401, headers={"HX-Redirect": url})
        raise HTTPException(status_code=303, headers={"Location": url})
    return Operator(
        username=account.username,
        role=account.role,
        session_expires_at=datetime.fromisoformat(session["expires_at"]),
    )
```

FastAPI's default `HTTPException` handler returns the status and headers as given, so a 303 with `Location` redirects a browser without a custom handler.

- [ ] **Step 4: Run to verify they pass, then commit**

```bash
uv run pytest tests/test_auth.py -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/auth.py tests/test_auth.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: sessions, login rate limit, and the current_operator dependency"
```
Expected: `19 passed`. Revert checks: `safe_next` → `return value or home`: the safe-next test must fail; drop the `is_htmx` branch: the HTMX redirect test must fail; delete the `from_trusted_proxy` check: the untrusted-address test must fail; delete the account-reread block: the four `*_kills_*` and `*_is_dead_*` tests must fail; count before recording in `reserve_attempt`: the boundary test must fail. Restore each.

---

## Task 8: The API client

**Files:**
- Create: `src/seller_console/client.py`
- Modify: `tests/conftest.py` (add `agent_app`)
- Test: `tests/test_client.py`

- [ ] **Step 1: Add the agent app fixture**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def agent_app():
    """A fresh app carrying the pinned agent's real REST routers."""
    from fastapi import FastAPI

    from ad_seller.interfaces.api.routers import ALL_ROUTERS

    app = FastAPI()
    for router in ALL_ROUTERS:
        app.include_router(router)
    return app
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_client.py
"""ConsoleApi calls the real agent routes with the console key and validates every body."""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from seller_console.client import ApiRejected, ApiUnavailable, ConsoleApi


def _api(agent_app, key, **kwargs) -> ConsoleApi:
    transport = httpx.ASGITransport(app=agent_app, raise_app_exceptions=False)
    return ConsoleApi(transport, "http://agent.test", key, **kwargs)


def _override(agent_app, fn):
    from ad_seller.interfaces.api import deps

    agent_app.dependency_overrides[deps._require_api_key_record] = fn


async def test_me_returns_console_key_info(agent_app, console_key):
    key, key_id = console_key
    me = await _api(agent_app, key).me(user="nicolas")
    assert me.key_id == key_id
    assert me.role == "operator"
    assert me.is_active is True


async def test_every_call_carries_key_and_user_header(agent_app, console_key):
    key, _ = console_key
    seen = {}

    @agent_app.middleware("http")
    async def capture(request, call_next):
        seen["authorization"] = request.headers.get("authorization")
        seen["user"] = request.headers.get("x-console-user")
        return await call_next(request)

    await _api(agent_app, key).health(user="nicolas")
    assert seen["authorization"] == f"Bearer {key}"
    assert seen["user"] == "nicolas"


async def test_health_merges_root_and_health(agent_app, console_key):
    key, _ = console_key
    health = await _api(agent_app, key).health(user="nicolas")
    assert health.status == "healthy"
    assert health.name == "Ad Seller System API"
    assert health.version


async def test_inventory_sync_status_shape(agent_app, console_key):
    key, _ = console_key
    status = await _api(agent_app, key).inventory_sync_status(user="nicolas")
    assert status.enabled is False
    assert status.sync_count == 0


async def test_last_event_is_none_or_typed(agent_app, console_key):
    key, _ = console_key
    event = await _api(agent_app, key).last_event(user="nicolas")
    assert event is None or event.event_type  # the agent's bus is process-wide; other tests may publish


async def test_revoked_key_raises_rejected(agent_app, agent_storage, console_key):
    from ad_seller.auth.api_key_service import ApiKeyService

    key, key_id = console_key
    await ApiKeyService(agent_storage).revoke_key(key_id)
    with pytest.raises(ApiRejected) as exc:
        await _api(agent_app, key).me(user="nicolas")
    assert exc.value.status == 401


@pytest.mark.parametrize("status", [301, 302, 307, 308])
async def test_redirects_are_never_followed_or_parsed(agent_app, console_key, status):
    from fastapi.responses import RedirectResponse

    key, _ = console_key

    def redirect():
        raise HTTPException(status_code=status, headers={"Location": "/elsewhere"})

    _override(agent_app, redirect)
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(agent_app, key).me(user="nicolas")
    finally:
        agent_app.dependency_overrides.clear()
    assert exc.value.status == status
    assert exc.value.detail == "redirect"


class SpyTransport(httpx.AsyncBaseTransport):
    """Wraps a transport and records how many times it was closed."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner
        self.closes = 0

    async def handle_async_request(self, request):
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        self.closes += 1
        await self.inner.aclose()


async def test_transport_is_shared_across_calls_and_closed_once(agent_app, console_key):
    key, _ = console_key
    spy = SpyTransport(httpx.ASGITransport(app=agent_app, raise_app_exceptions=False))
    api = ConsoleApi(spy, "http://agent.test", key)
    await api.health(user="nicolas")  # two concurrent requests inside
    await asyncio.gather(api.me(user="nicolas"), api.health(user="nicolas"), api.inventory_sync_status(user="nicolas"))
    assert spy.closes == 0
    await api.aclose()
    assert spy.closes == 1


@pytest.mark.parametrize("status", [404, 409, 429, 500, 502, 503])
async def test_error_statuses_raise_unavailable_with_the_status(agent_app, console_key, status):
    key, _ = console_key

    def fail():
        raise HTTPException(status_code=status)

    _override(agent_app, fail)
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(agent_app, key).me(user="nicolas")
    finally:
        agent_app.dependency_overrides.clear()
    assert exc.value.status == status


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_statuses_raise_rejected(agent_app, console_key, status):
    key, _ = console_key

    def fail():
        raise HTTPException(status_code=status)

    _override(agent_app, fail)
    try:
        with pytest.raises(ApiRejected) as exc:
            await _api(agent_app, key).me(user="nicolas")
    finally:
        agent_app.dependency_overrides.clear()
    assert exc.value.status == status


async def test_server_error_raises_unavailable(agent_app, console_key):
    key, _ = console_key

    def boom():
        raise RuntimeError("storage down")

    _override(agent_app, boom)
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(agent_app, key).me(user="nicolas")
    finally:
        agent_app.dependency_overrides.clear()
    assert exc.value.status == 500
    assert key not in str(exc.value)


@pytest.mark.parametrize("body", [[], None, "text", {"unexpected": 1}, {"events": None}, {"events": [{"no": "fields"}]}])
async def test_every_method_rejects_malformed_bodies(agent_app, console_key, body, monkeypatch):
    key, _ = console_key
    api = _api(agent_app, key)

    async def fake_get(path, user, params=None):
        return body

    monkeypatch.setattr(api, "_get", fake_get)
    for method in (api.me, api.health, api.inventory_sync_status, api.last_event):
        with pytest.raises(ApiUnavailable) as exc:
            await method(user="nicolas")
        assert "unexpected response shape" in str(exc.value)


async def test_timeout_raises_unavailable(agent_app, console_key):
    key, _ = console_key

    async def slow():
        await asyncio.sleep(0.5)

    _override(agent_app, slow)
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(agent_app, key, timeout=0.05).me(user="nicolas")
    finally:
        agent_app.dependency_overrides.clear()
    assert exc.value.status == 0
    assert "timeout" in str(exc.value)


async def test_unreachable_agent_raises_unavailable(console_key):
    key, _ = console_key
    api = ConsoleApi(httpx.AsyncHTTPTransport(), "http://127.0.0.1:9", key)  # nothing listens on port 9
    with pytest.raises(ApiUnavailable) as exc:
        await api.me(user="nicolas")
    assert exc.value.status == 0
    assert "unreachable" in str(exc.value)
```

- [ ] **Step 3: Run to verify they fail**

```bash
uv run pytest tests/test_client.py -q
```
Expected: `ModuleNotFoundError: No module named 'seller_console.client'`.

- [ ] **Step 4: Implement**

```python
# src/seller_console/client.py
"""HTTP client from the console to the agent's REST API.

The transport is injected: ``httpx.AsyncHTTPTransport`` in production, an ASGI
transport over the pinned agent app in tests. One client lives for the life of the
app and is closed by its lifespan. Nothing else in the console imports httpx. Every body is validated into a console-owned model; anything else degrades
one card, never the page. ``X-Console-User`` is display context for the agent's logs,
not attribution: the agent authenticates the key only.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class KeyInfo(BaseModel):
    key_id: str
    label: str
    role: str
    is_active: bool
    expires_at: Optional[str] = None


class Health(BaseModel):
    status: str
    name: str
    version: str


class SyncStatus(BaseModel):
    enabled: bool
    last_sync: Optional[str] = None
    sync_count: int = 0


class EventSummary(BaseModel):
    event_type: str
    timestamp: str


class ApiRejected(Exception):
    """The agent refused the console key: 401 (invalid/revoked) or 403 (not an operator)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"agent rejected the console key with status {status}")
        self.status = status


class ApiUnavailable(Exception):
    """The agent could not answer: unreachable, timeout, non-2xx, non-JSON, or an unexpected shape."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"agent unavailable ({status}): {detail}")
        self.status = status
        self.detail = detail


class ConsoleApi:
    def __init__(self, transport: httpx.AsyncBaseTransport, base_url: str, operator_api_key: str, timeout: float = 2.0) -> None:
        # One long-lived client over the injected transport. httpx closes a supplied transport
        # when the client that owns it closes, so a client per call would close the shared
        # transport after the first request; concurrent calls share this one client instead.
        self._client = httpx.AsyncClient(transport=transport, base_url=base_url, follow_redirects=False)
        self._key = operator_api_key
        self._timeout = timeout

    async def aclose(self) -> None:
        """Closed exactly once, by the app's lifespan at shutdown."""
        await self._client.aclose()

    async def _get(self, path: str, user: str, params: Optional[dict] = None) -> Any:
        headers = {"Authorization": f"Bearer {self._key}", "X-Console-User": user}
        try:
            response = await asyncio.wait_for(self._client.get(path, headers=headers, params=params), self._timeout)
        except asyncio.TimeoutError as exc:
            raise ApiUnavailable(0, f"timeout after {self._timeout}s") from exc
        except httpx.ConnectError as exc:
            raise ApiUnavailable(0, "agent unreachable") from exc
        except httpx.HTTPError as exc:
            raise ApiUnavailable(0, type(exc).__name__) from exc
        if response.status_code in (401, 403):
            raise ApiRejected(response.status_code)
        if not 200 <= response.status_code < 300:
            # Redirects included: the client never follows and never parses them.
            raise ApiUnavailable(response.status_code, "error status" if response.status_code >= 400 else "redirect")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiUnavailable(response.status_code, "non-JSON body") from exc

    @staticmethod
    def _parse(model: type[M], body: Any) -> M:
        try:
            return model.model_validate(body)
        except (ValidationError, TypeError) as exc:
            raise ApiUnavailable(200, f"unexpected response shape for {model.__name__}") from exc

    async def me(self, user: str) -> KeyInfo:
        return self._parse(KeyInfo, await self._get("/auth/api-keys/me", user))

    async def health(self, user: str) -> Health:
        health, root = await asyncio.gather(self._get("/health", user), self._get("/", user))
        if not isinstance(health, dict) or not isinstance(root, dict):
            raise ApiUnavailable(200, "unexpected response shape for Health")
        return self._parse(Health, {**root, **health})

    async def inventory_sync_status(self, user: str) -> SyncStatus:
        return self._parse(SyncStatus, await self._get("/api/v1/inventory-sync/status", user))

    async def last_event(self, user: str) -> Optional[EventSummary]:
        body = await self._get("/events", user, params={"limit": 50})
        events = body.get("events") if isinstance(body, dict) else None
        if not isinstance(events, list):
            raise ApiUnavailable(200, "unexpected response shape for events")
        if not events:
            return None
        return max((self._parse(EventSummary, e) for e in events), key=lambda e: e.timestamp)
```

- [ ] **Step 5: Run to verify they pass, then commit**

```bash
uv run pytest tests/test_client.py -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/client.py tests/conftest.py tests/test_client.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: typed client to the agent's REST API over an injected transport"
```
Expected: `28 passed`. Revert checks: remove the `X-Console-User` header: the header test must fail; make `_parse` return `body`: the malformed-body test must fail; change the status check back to `>= 400`: the four redirect tests must fail; open a client per call in `_get`: the shared-transport test must fail. Restore.

---

## Task 9: Templates and static assets

**Files:**
- Create: `src/seller_console/templates/base.html`, `login.html`, `home.html`, `error.html`, `partials/health_cards.html`
- Create: `src/seller_console/static/console.css`, `static/htmx.min.js`
- Test: `tests/test_assets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assets.py
"""The console ships its own assets: no CDN, no build step, no hardcoded mount."""

from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1] / "src" / "seller_console"


# sha256 of htmx.org@2.0.4/dist/htmx.min.js, obtained independently of the vendoring step
# (checked against both unpkg and jsDelivr on 2026-09-16). The vendored file is that
# exact byte sequence after the one-line provenance header.
HTMX_SHA256 = "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447"


def test_htmx_is_vendored_and_matches_the_pinned_digest():
    import hashlib

    raw = (CONSOLE / "static" / "htmx.min.js").read_bytes()
    header, _, body = raw.partition(b"\n")
    assert header.startswith(b"/* htmx 2.0.4") and b"2.0.4" in header
    assert hashlib.sha256(body).hexdigest() == HTMX_SHA256


def test_templates_exist():
    for name in ("base.html", "login.html", "home.html", "error.html", "partials/health_cards.html"):
        assert (CONSOLE / "templates" / name).exists(), name


def test_templates_reference_no_external_hosts_and_no_fixed_mount():
    for path in (CONSOLE / "templates").rglob("*.html"):
        text = path.read_text()
        assert "https://" not in text and "http://" not in text, path
        assert "/console/" not in text, path
```

- [ ] **Step 2: Vendor HTMX**

```bash
curl -fsSL https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o /tmp/htmx.min.js
echo "e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447  /tmp/htmx.min.js" | shasum -a 256 -c -
{ printf '/* htmx 2.0.4 — vendored from https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js — sha256 e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447 — BSD-2-Clause */\n'; cat /tmp/htmx.min.js; } > src/seller_console/static/htmx.min.js
```
The digest is pinned in the test file, not derived from the download: if the CDN serves different bytes, `shasum -c` fails here and the test fails later.

- [ ] **Step 3: Write the stylesheet**

`src/seller_console/static/console.css`:

```css
/* IAB Tech Lab palette (sampled from the logo and site) plus semantic status colors. */
:root {
  --brand: #ee3126; --ink: #221f1f; --text: #3f3f3f; --text-2: #5d5d5d; --label: #7d7d7d;
  --line: #e4e4e4; --ground: #f7f6f6; --ok: #1f7a3f; --warn: #b7791f; --error: #b3261e; --error-bg: #fdecea;
  --font: system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: var(--font); font-size: 14px; color: var(--text); background: #fff; }
a { color: var(--brand); }
code { background: #f0eeee; padding: 0 3px; border-radius: 3px; }
.top { height: 48px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
.wordmark { font-weight: 800; letter-spacing: -0.02em; font-size: 18px; color: var(--ink); text-decoration: none; }
.wordmark i { color: var(--brand); font-style: normal; }
.wordmark span { font-weight: 500; color: var(--brand); font-size: 12px; margin-left: 6px; letter-spacing: 0.04em; }
.wordmark small { font-weight: 500; color: var(--text-2); font-size: 13px; margin-left: 12px; letter-spacing: 0; }
.who { color: var(--text-2); } .who b { color: var(--ink); } .who form { display: inline; }
.who button { background: none; border: 0; color: var(--brand); cursor: pointer; font: inherit; text-decoration: underline; padding: 0; }
.body { display: flex; min-height: calc(100vh - 48px); }
.nav { width: 208px; border-right: 1px solid var(--line); background: var(--ground); padding: 16px 12px; }
.nav .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--label); padding: 4px 10px 10px; }
.nav a, .nav .off { display: flex; justify-content: space-between; align-items: center; padding: 9px 10px; border-radius: 4px; color: var(--text); text-decoration: none; }
.nav a.active { background: var(--brand); color: #fff; font-weight: 600; }
.nav .off { color: #bababa; } .nav .off small { font-size: 10px; border: 1px solid #d5d5d5; border-radius: 8px; padding: 0 6px; }
.main { flex: 1; padding: 24px 28px; max-width: 1100px; }
h1 { margin: 0 0 16px; font-size: 20px; color: var(--ink); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.card { border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
.card .t { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--label); margin-bottom: 6px; }
.card .v { font-size: 16px; font-weight: 600; color: var(--ink); } .card .s { color: var(--text-2); margin-top: 4px; }
.ok { color: var(--ok); } .warn { color: var(--warn); } .error { color: var(--error); }
.note { color: var(--text-2); margin-top: 16px; }
.login { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: var(--ground); }
.login-card { background: #fff; border: 1px solid var(--line); border-radius: 6px; padding: 26px 30px; width: 340px; }
.login-card h1 { font-size: 17px; margin: 8px 0 2px; }
.login-card label { display: block; font-size: 12px; color: var(--text-2); margin: 14px 0 4px; }
.login-card input { width: 100%; border: 1px solid var(--label); border-radius: 4px; padding: 8px 9px; font: inherit; }
.btn { background: var(--brand); color: #fff; border: 0; border-radius: 4px; padding: 9px 16px; font: inherit; font-weight: 600; cursor: pointer; margin-top: 16px; }
.alert { margin-top: 12px; color: var(--error); background: var(--error-bg); padding: 8px 10px; border-radius: 4px; }
.help { margin-top: 14px; color: var(--text-2); font-size: 12px; }
```

- [ ] **Step 4: Write the templates**

`templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Seller Agent Console{% endblock %}</title>
  <link rel="stylesheet" href="{{ root }}/static/console.css">
  <script src="{{ root }}/static/htmx.min.js" defer></script>
</head>
<body>
{% block body %}
<header class="top">
  <a class="wordmark" href="{{ root }}/">iab<i>.</i><span>TECH LAB</span><small>Seller Agent Console</small></a>
  <div class="who" id="who">
    Signed in as <b>{{ operator.username }}</b>
    {% if not sso %}
    · <form method="post" action="{{ root }}/logout" id="logout-form">
        <input type="hidden" name="csrf" id="csrf" value="{{ csrf }}">
        <button type="submit">Sign out</button>
      </form>
    {% endif %}
  </div>
</header>
<div class="body">
  <nav class="nav">
    <div class="lbl">Control room</div>
    {% for item in nav %}
      {% if item.built %}
        <a href="{{ root }}{{ item.path }}" class="{{ 'active' if item.active else '' }}" id="nav-{{ item.slug }}">{{ item.label }}</a>
      {% else %}
        <div class="off" id="nav-{{ item.slug }}"><span>{{ item.label }}</span><small>soon</small></div>
      {% endif %}
    {% endfor %}
  </nav>
  <main class="main">
    {% block main %}{% endblock %}
  </main>
</div>
{% endblock %}
</body>
</html>
```

`templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Sign in · Seller Agent Console{% endblock %}
{% block body %}
<div class="login">
  <form class="login-card" method="post" action="{{ root }}/login" id="login-form">
    <a class="wordmark" href="{{ root }}/login">iab<i>.</i><span>TECH LAB</span></a>
    <h1>Seller Agent Console</h1>
    <div class="help" style="margin-top:0">Sign in</div>
    <input type="hidden" name="csrf" id="csrf" value="{{ csrf }}">
    <input type="hidden" name="next" value="{{ next }}">
    <label for="username">Username</label>
    <input id="username" name="username" autocomplete="username" required autofocus>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    {% if error %}<div class="alert" id="login-error">{{ error }}</div>{% endif %}
    <button class="btn" type="submit">Sign in</button>
    <div class="help">Accounts are created on the host with <code>seller-console create-user</code>. When single sign-on is configured, this page is off.</div>
  </form>
</div>
{% endblock %}
```

`templates/home.html`:

```html
{% extends "base.html" %}
{% block title %}Setup and health · Seller Agent Console{% endblock %}
{% block main %}
<h1>Setup and health</h1>
<div id="health" hx-get="{{ root }}/partials/health" hx-trigger="every 30s" hx-swap="innerHTML">
  {% include "partials/health_cards.html" %}
</div>
<p class="note">Cards refresh every 30 seconds.</p>
{% endblock %}
```

`templates/partials/health_cards.html`:

```html
<div class="cards" data-checked-at="{{ checked_at }}">
  {% for card in cards %}
  <div class="card" id="card-{{ card.slug }}" data-state="{{ card.state }}">
    <div class="t">{{ card.title }}</div>
    <div class="v {{ card.tone }}">{{ card.value }}</div>
    <div class="s">{{ card.detail }}</div>
  </div>
  {% endfor %}
</div>
```

`templates/error.html`:

```html
{% extends "base.html" %}
{% block title %}Something went wrong · Seller Agent Console{% endblock %}
{% block body %}
<div class="login">
  <div class="login-card">
    <h1>Something went wrong</h1>
    <p>The console hit an unexpected error. It has been logged with request id <code id="request-id">{{ request_id }}</code>.</p>
    <p><a href="{{ root }}/">Back to the console</a></p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 5: Run the asset tests, then commit**

```bash
uv run pytest tests/test_assets.py -q
git add src/seller_console/templates src/seller_console/static tests/test_assets.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console templates, stylesheet, and vendored htmx"
```
Expected: `3 passed`.

---

## Task 10: Routes, `create_app`, login and logout

**Files:**
- Create: `src/seller_console/routes.py`, `src/seller_console/main.py`
- Modify: `tests/conftest.py` (config, console app, client, HTML helper, login helper)
- Test: `tests/test_login.py`

- [ ] **Step 1: Add the fixtures and helpers**

Append to `tests/conftest.py` (the imports go to the import block at the top of the file):

```python
import httpx
from html.parser import HTMLParser
from httpx import ASGITransport

from seller_console.config import ConsoleConfig
from seller_console.main import create_app


class _Index(HTMLParser):
    """Collects elements by id: id -> {tag, attrs, text}."""

    def __init__(self):
        super().__init__()
        self.by_id: dict[str, dict] = {}
        self._open: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.by_id[attrs["id"]] = {"tag": tag, "attrs": attrs, "text": ""}
            self._open.append(attrs["id"])
        else:
            self._open.append("")

    def handle_endtag(self, tag):
        if self._open:
            self._open.pop()

    def handle_data(self, data):
        for element_id in self._open:
            if element_id:
                self.by_id[element_id]["text"] += data


def html_index(text: str) -> dict[str, dict]:
    parser = _Index()
    parser.feed(text)
    return parser.by_id


@pytest.fixture
def config(console_key, tmp_path) -> ConsoleConfig:
    key, _ = console_key
    return ConsoleConfig(
        _env_file=None,
        seller_agent_url="http://agent.test",
        console_operator_api_key=key,
        console_db_url=f"sqlite:///{tmp_path}/console.db",
        failure_delay_seconds=0,
    )


@pytest.fixture
async def console_app(agent_app, config, store):
    transport = ASGITransport(app=agent_app, raise_app_exceptions=False)
    app = create_app(config, transport=transport, store=store)
    yield app
    await app.state.console.api.aclose()  # the lifespan is not entered here, so close the client ourselves


@pytest.fixture
def client(console_app):
    return httpx.AsyncClient(
        transport=ASGITransport(app=console_app, raise_app_exceptions=False), base_url="http://console.test"
    )


@pytest.fixture
async def account(store):
    from seller_console import accounts

    return await accounts.create_account(store, "nicolas", "correct horse battery")


def csrf_from(page_text: str) -> str:
    """The synchronizer token embedded in the page's form (there is no CSRF cookie)."""
    return html_index(page_text)["csrf"]["attrs"]["value"]


async def login(client: httpx.AsyncClient, username="nicolas", password="correct horse battery"):
    page = await client.get("/login")
    return await client.post("/login", data={"username": username, "password": password, "csrf": csrf_from(page.text), "next": "/"})
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_login.py
"""Login, logout, cookies, CSRF, rate limit, the shell, and the health endpoint."""

import httpx
import pytest

from seller_console import auth
from tests.conftest import csrf_from, html_index, login


async def test_static_is_served(client):
    css = await client.get("/static/console.css")
    assert css.status_code == 200
    assert "--brand: #ee3126" in css.text


async def test_healthz_is_503_until_startup_check_passes(client, console_app):
    assert (await client.get("/healthz")).status_code == 503
    console_app.state.ready = True
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["version"]


async def test_login_page_embeds_a_server_stored_token(client, store):
    page = await client.get("/login")
    assert page.status_code == 200
    form = html_index(page.text)
    assert form["login-form"]["attrs"]["action"] == "/login"
    assert "login-error" not in form
    token = csrf_from(page.text)
    assert await store.get("csrf:" + token) == {"owner": "anonymous"}
    assert "console_csrf" not in page.cookies  # synchronizer tokens, no cookie


async def test_login_success_sets_session_cookie_and_redirects(client, account):
    response = await login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"].lower()
    assert "console_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/" in cookie
    assert "secure" not in cookie  # http in tests


async def test_session_cookie_is_secure_behind_https_proxy(client, account):
    page = await client.get("/login")
    response = await client.post(
        "/login",
        data={"username": "nicolas", "password": "correct horse battery", "csrf": csrf_from(page.text), "next": "/"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert "secure" in response.headers["set-cookie"].lower()


async def test_wrong_password_is_generic_401(client, account):
    response = await login(client, password="wrong horse battery")
    assert response.status_code == 401
    assert html_index(response.text)["login-error"]["text"] == "Wrong username or password."
    assert "console_session" not in response.cookies


async def test_unknown_user_gets_the_same_message(client, account):
    response = await login(client, username="nobody")
    assert response.status_code == 401
    assert html_index(response.text)["login-error"]["text"] == "Wrong username or password."


async def test_missing_or_unknown_csrf_is_400(client, account):
    await client.get("/login")
    for csrf in ("", "bogus"):
        response = await client.post("/login", data={"username": "nicolas", "password": "correct horse battery", "csrf": csrf, "next": "/"})
        assert response.status_code == 400


async def test_csrf_token_is_single_use(client, account):
    page = await client.get("/login")
    token = csrf_from(page.text)
    first = await client.post("/login", data={"username": "nicolas", "password": "wrong horse battery", "csrf": token, "next": "/"})
    assert first.status_code == 401
    second = await client.post("/login", data={"username": "nicolas", "password": "correct horse battery", "csrf": token, "next": "/"})
    assert second.status_code == 400  # spent by the first attempt


async def test_csrf_token_is_bound_to_the_session(client, account, store):
    """A token issued to an authenticated page cannot be spent anonymously, and vice versa."""
    from seller_console import auth as auth_module

    anonymous = await auth_module.issue_csrf_token(store, "anonymous")
    await login(client)
    logout = await client.post("/logout", data={"csrf": anonymous})
    assert logout.status_code == 400
    page = await client.get("/")  # issues a token bound to nicolas
    logout = await client.post("/logout", data={"csrf": csrf_from(page.text)})
    assert logout.status_code == 303


async def test_cross_origin_unsafe_requests_are_refused(client, account):
    page = await client.get("/login")
    token = csrf_from(page.text)
    response = await client.post(
        "/login",
        data={"username": "nicolas", "password": "correct horse battery", "csrf": token, "next": "/"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 400
    same = await client.post(
        "/login",
        data={"username": "nicolas", "password": "correct horse battery", "csrf": csrf_from((await client.get("/login")).text), "next": "/"},
        headers={"Origin": "http://console.test"},
    )
    assert same.status_code == 303


async def test_sixth_failure_is_rate_limited(client, account, store):
    for _ in range(5):
        assert (await login(client, password="wrong horse battery")).status_code == 401
    response = await login(client, password="wrong horse battery")
    assert response.status_code == 429
    assert "Too many attempts" in html_index(response.text)["login-error"]["text"]
    assert (await login(client)).status_code == 429  # a correct password is refused while limited
    await auth.clear_user_failures(store, "nicolas")
    for key in await store.keys("rate_limit:addr:*"):
        await store.delete(key)
    assert (await login(client)).status_code == 303


async def test_success_does_not_reset_the_address_budget(client, account, store):
    for _ in range(3):
        await login(client, username="someone-else", password="wrong horse battery")
    assert (await login(client)).status_code == 303  # nicolas logs in from the same address
    assert await auth.failures(store, "someone-else", "127.0.0.1") == 3  # their failures still count


async def test_logout_deletes_session_and_clears_cookie(client, account, store):
    await login(client)
    token = client.cookies["console_session"]
    assert await store.get(auth.SESSION_PREFIX + token) is not None
    page = await client.get("/")
    response = await client.post("/logout", data={"csrf": csrf_from(page.text)})
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert await store.get(auth.SESSION_PREFIX + token) is None
    assert "max-age=0" in response.headers["set-cookie"].lower() or 'console_session=""' in response.headers["set-cookie"]


async def test_logout_without_csrf_is_400_and_keeps_the_session(client, account, store):
    await login(client)
    token = client.cookies["console_session"]
    assert (await client.post("/logout", data={"csrf": "bogus"})).status_code == 400
    assert await store.get(auth.SESSION_PREFIX + token) is not None


async def test_every_unsafe_route_requires_csrf(console_app):
    from fastapi.routing import APIRoute

    from seller_console.routes import require_csrf

    unsafe = [r for r in console_app.routes if isinstance(r, APIRoute) and r.methods & {"POST", "PUT", "PATCH", "DELETE"}]
    assert unsafe
    for route in unsafe:
        assert any(d.dependency is require_csrf for d in route.dependencies), route.path


async def test_login_rotates_token(client, account):
    await login(client)
    first = client.cookies["console_session"]
    await login(client)
    assert client.cookies["console_session"] != first


async def test_login_never_logs_secrets(client, account, caplog):
    caplog.set_level("DEBUG")
    await login(client, password="wrong horse battery")
    await login(client)
    assert "wrong horse battery" not in caplog.text
    assert "correct horse battery" not in caplog.text
    assert client.cookies["console_session"] not in caplog.text


@pytest.fixture
def sso_client(agent_app, config, store):
    from httpx import ASGITransport

    from seller_console.main import create_app

    sso = config.model_copy(update={"console_trusted_identity_header": "X-Forwarded-Email", "console_trusted_proxy_cidrs": "127.0.0.1/32"})
    app = create_app(sso, transport=ASGITransport(app=agent_app, raise_app_exceptions=False), store=store)
    return httpx.AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://console.test")


async def test_password_endpoints_are_404_in_sso_mode(sso_client, account):
    assert (await sso_client.get("/login")).status_code == 404
    assert (await sso_client.post("/login", data={"username": "nicolas", "password": "correct horse battery", "csrf": "x"})).status_code == 404
    assert (await sso_client.post("/logout", data={"csrf": "x"})).status_code == 404


async def test_pages_issue_session_bound_tokens_in_sso_mode(sso_client, store):
    from seller_console import accounts

    await accounts.create_account(store, "nicolas@example.com", "correct horse battery")
    page = await sso_client.get("/", headers={"X-Forwarded-Email": "nicolas@example.com"})
    assert page.status_code == 200
    assert await store.get("csrf:" + csrf_from(page.text)) == {"owner": "nicolas@example.com"}
```

- [ ] **Step 3: Run to verify they fail**

```bash
uv run pytest tests/test_login.py -q
```
Expected: `ImportError: cannot import name 'create_app'`.

- [ ] **Step 4: Implement routes**

```python
# src/seller_console/routes.py
"""Console pages: login, logout, the landing page, the health partial, and /healthz."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import __version__, auth
from .accounts import check_credentials
from .auth import ConsoleState, Operator, current_operator
from .client import ApiRejected, ApiUnavailable, EventSummary, Health, KeyInfo, SyncStatus

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

NAV = [
    {"label": "Inbox", "slug": "inbox", "path": "/inbox", "built": False},
    {"label": "Orders", "slug": "orders", "path": "/orders", "built": False},
    {"label": "Deals", "slug": "deals", "path": "/deals", "built": False},
    {"label": "Negotiation", "slug": "negotiation", "path": "/negotiation", "built": False},
    {"label": "Catalog", "slug": "catalog", "path": "/catalog", "built": False},
    {"label": "Setup", "slug": "setup", "path": "/", "built": True},
]
GENERIC_LOGIN_ERROR = "Wrong username or password."
RATE_LIMITED_ERROR = "Too many attempts. Try again in 10 minutes."


def _state(request: Request) -> ConsoleState:
    return request.app.state.console


def _nav(active_slug: str) -> list[dict[str, Any]]:
    return [{**item, "active": item["slug"] == active_slug} for item in NAV]


async def _render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    """Every rendered page carries a fresh server-stored CSRF token (synchronizer pattern).

    The token is bound to the signed-in username, or to "anonymous" before login, so a
    token issued to one session cannot be spent by another. require_csrf consumes it.
    """
    state = _state(request)
    operator = context.get("operator")
    if context.pop("issue_csrf", True):  # partials carry no forms: no token per poll
        context["csrf"] = await auth.issue_csrf_token(state.store, operator.username if operator else auth.ANONYMOUS)
    context.setdefault("root", auth.root(request))
    context.setdefault("sso", state.config.sso)
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def _same_origin(request: Request) -> bool:
    """Unsafe requests must come from this origin. Origin first, Referer as the fallback, absent is allowed
    (older clients); a mismatch is never allowed."""
    scheme = "https" if auth.is_secure(request) else "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    expected = f"{scheme}://{host}"
    origin = request.headers.get("origin")
    if origin:
        return origin == expected
    referer = request.headers.get("referer")
    return not referer or referer.startswith(expected + "/")


async def require_csrf(request: Request, csrf: str = Form("")) -> None:
    """Dependency on every unsafe route: same origin, and a live token bound to this session."""
    if not _same_origin(request):
        raise HTTPException(status_code=400, detail="Cross-origin request refused")
    state = _state(request)
    token = request.cookies.get(auth.SESSION_COOKIE)
    session = await auth.load_session(state.store, token) if token else None
    owner = session["username"] if session else auth.ANONYMOUS
    if not await auth.consume_csrf_token(state.store, csrf, owner):
        raise HTTPException(status_code=400, detail="CSRF token missing, used, or not yours; reload the page")


async def unexpected_error(request: Request, exc: Exception) -> HTMLResponse:
    """Registered on the app for Exception; HTTPException keeps FastAPI's own handler."""
    request_id = uuid.uuid4().hex[:8]
    logger.exception("console request %s failed (request id %s)", request.url.path, request_id)
    return await _render(request, "error.html", status_code=500, request_id=request_id, operator=None, nav=[])


async def _password_login_enabled(request: Request) -> None:
    """Also a route dependency, listed before require_csrf so SSO mode answers 404, not 400."""
    if _state(request).config.sso:
        raise HTTPException(status_code=404)


async def _login_page(request: Request, *, error: str | None, status_code: int, next_path: str) -> HTMLResponse:
    return await _render(request, "login.html", status_code=status_code, error=error, next=next_path)


@router.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    if not getattr(request.app.state, "ready", False):
        return JSONResponse({"status": "starting"}, status_code=503)
    return JSONResponse({"status": "ok", "version": __version__})


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str | None = None) -> Any:
    await _password_login_enabled(request)
    return await _login_page(request, error=None, status_code=200, next_path=auth.safe_next(next, auth.root(request)))


@router.post("/login", response_class=HTMLResponse, dependencies=[Depends(_password_login_enabled), Depends(require_csrf)])
async def login_submit(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("")) -> Any:
    state = _state(request)
    next_path = auth.safe_next(next, auth.root(request))
    address = auth.client_address(request)
    count, stamp = await auth.reserve_attempt(state.store, username, address)  # record first, then admit
    if count > auth.RATE_LIMIT_MAX:
        return await _login_page(request, error=RATE_LIMITED_ERROR, status_code=429, next_path=next_path)
    account = await check_credentials(state.store, username, password)
    if account is None:
        await asyncio.sleep(state.config.failure_delay_seconds)  # the attempt row stays
        return await _login_page(request, error=GENERIC_LOGIN_ERROR, status_code=401, next_path=next_path)
    await auth.release_attempt(state.store, username, address, stamp)
    await auth.clear_user_failures(state.store, username)
    token, _ = await auth.create_session(
        state.store, account.username, account.role, account.credential_version, ttl_hours=state.config.console_session_ttl_hours
    )
    response = RedirectResponse(next_path, status_code=303)
    auth.set_session_cookie(response, request, token, max_age=state.config.console_session_ttl_hours * 3600)
    logger.info("console login: %s", account.username)
    return response


@router.post("/logout", dependencies=[Depends(_password_login_enabled), Depends(require_csrf)])
async def logout(request: Request) -> Any:
    response = RedirectResponse(auth.login_path(request), status_code=303)
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        await auth.delete_session(_state(request).store, token)
    auth.clear_session_cookie(response, request)
    return response
```

The landing page and the partial are added in Task 13; `Awaitable`, the card models, `datetime`, and `Operator` are imported now so Task 12 only appends. Until then ruff reports them unused: add `# noqa: F401` to those two import lines and remove it in Task 13.

- [ ] **Step 5: Implement `create_app`**

```python
# src/seller_console/main.py
"""Application factory, lifespan, and the startup key check.

Run with: uvicorn seller_console.main:create_app --factory --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .auth import ConsoleState
from .client import ApiRejected, ApiUnavailable, ConsoleApi
from .config import ConsoleConfig
from .routes import router, unexpected_error
from .store import Store

logger = logging.getLogger(__name__)
_STATIC = Path(__file__).parent / "static"


async def verify_console_key(
    state: ConsoleState,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """The key must be a valid operator key on the agent, or the app must not serve.

    The agent may still be starting: while it is unreachable the check retries for
    CONSOLE_STARTUP_TIMEOUT_SECONDS. A rejection is final.
    """
    deadline = clock() + state.config.console_startup_timeout_seconds
    while True:
        try:
            me = await state.api.me(user="startup")
        except ApiRejected as exc:
            raise RuntimeError(
                f"CONSOLE_OPERATOR_API_KEY was rejected by the agent (status {exc.status}): "
                "it must be a valid, active operator key"
            ) from exc
        except ApiUnavailable as exc:
            if exc.status == 0 and clock() < deadline:
                logger.warning("agent not reachable yet (%s); retrying", exc.detail)
                await sleep(2)
                continue
            raise RuntimeError(f"console startup check could not reach the agent: {exc.detail}") from exc
        if me.role != "operator":
            raise RuntimeError("CONSOLE_OPERATOR_API_KEY is not an operator key")
        logger.info("console ready: agent key %s (%s)", me.key_id, me.label)
        return


@asynccontextmanager
async def lifespan(app: FastAPI):
    state: ConsoleState = app.state.console
    await state.store.connect()
    try:
        await state.store.purge_expired()
        await verify_console_key(state)
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        await state.api.aclose()  # the one place the API client is closed
        await state.store.close()


def create_app(
    config: Optional[ConsoleConfig] = None,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    store: Optional[Store] = None,
) -> FastAPI:
    config = config or ConsoleConfig()
    if config.sso and not config.proxy_cidrs:
        raise RuntimeError(
            "CONSOLE_TRUSTED_IDENTITY_HEADER is set but CONSOLE_TRUSTED_PROXY_CIDRS is empty: "
            "SSO mode only trusts the header from the proxy's addresses"
        )
    api = ConsoleApi(
        transport or httpx.AsyncHTTPTransport(),
        config.seller_agent_url,
        config.resolved_operator_key(),
        timeout=config.api_timeout_seconds,
    )
    # root_path is what FastAPI needs behind a proxy prefix; templates and cookies read it from the scope.
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan, root_path=config.console_root_path)
    app.state.console = ConsoleState(config=config, api=api, store=store or Store(config.console_db_url))
    app.state.ready = False
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    # Starlette re-raises after sending the page; the test client uses raise_app_exceptions=False.
    app.add_exception_handler(Exception, unexpected_error)
    return app
```

The ASGI transport does not run the lifespan, which is why `test_healthz_is_503_until_startup_check_passes` flips `ready` by hand; the tests in Task 11 enter the lifespan the way a server does, through Starlette's `TestClient` on the built app. `TestClient` runs the lifespan in its own thread; the agent's in-process transport and the SQLite store both work there.

- [ ] **Step 6: Run to verify they pass, then commit**

```bash
uv run pytest tests -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/routes.py src/seller_console/main.py tests/conftest.py tests/test_login.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console app with login, logout, CSRF policy, and healthz"
```
Expected: `test_login.py`: 21 passed; everything else still green. Revert checks: remove `Depends(require_csrf)` from `login_submit`: the CSRF tests must fail; make `consume_csrf_token` skip the delete: the single-use test must fail; make `_same_origin` return `True`: the cross-origin test must fail; change `> auth.RATE_LIMIT_MAX` to `> 100`: the rate-limit test must fail. Restore.

---

## Task 11: Startup and wiring tests

**Files:**
- Test: `tests/test_startup.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_startup.py
"""create_app refuses bad configuration; the real lifespan enforces the key; the retry gives up on time."""

import httpx
import pytest
from httpx import ASGITransport

from starlette.testclient import TestClient

from seller_console.auth import ConsoleState
from seller_console.client import ConsoleApi
from seller_console.config import ConsoleConfig
from seller_console.main import create_app, verify_console_key
from seller_console.store import Store


def _config(console_key, tmp_path, **kw):
    key, _ = console_key
    base = dict(seller_agent_url="http://agent.test", console_operator_api_key=key, console_db_url=f"sqlite:///{tmp_path}/c.db")
    return ConsoleConfig(_env_file=None, **{**base, **kw})


def test_sso_without_proxy_cidrs_refuses_to_build(console_key, tmp_path):
    with pytest.raises(RuntimeError, match="CONSOLE_TRUSTED_PROXY_CIDRS"):
        create_app(_config(console_key, tmp_path, console_trusted_identity_header="X-Forwarded-Email"))


def test_missing_key_refuses_to_build(monkeypatch):
    for name in ("CONSOLE_OPERATOR_API_KEY", "CONSOLE_OPERATOR_API_KEY_FILE"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="CONSOLE_OPERATOR_API_KEY"):
        create_app(ConsoleConfig(_env_file=None, seller_agent_url="http://agent.test"))


async def test_root_path_moves_every_link_and_cookie(agent_app, console_key, tmp_path, store):
    """CONSOLE_ROOT_PATH is the production way to sit behind a proxy prefix."""
    import httpx

    from seller_console import accounts

    await accounts.create_account(store, "nicolas", "correct horse battery")
    app = create_app(_config(console_key, tmp_path, console_root_path="/console", failure_delay_seconds=0),
                     transport=ASGITransport(app=agent_app, raise_app_exceptions=False), store=store)
    client = httpx.AsyncClient(transport=ASGITransport(app=app, root_path="/console"), base_url="http://console.test")
    page = await client.get("/console/login")
    assert 'action="/console/login"' in page.text and 'href="/console/static/console.css"' in page.text
    redirect = await client.get("/console/")
    assert redirect.status_code == 303 and redirect.headers["location"].startswith("/console/login")


def _serve(app):
    """Enter the app the way a server does: Starlette's TestClient runs the app's own lifespan.

    Calling ``lifespan()`` directly would keep passing if the lifespan were unhooked from the app.
    """
    return TestClient(app)


async def test_lifespan_starts_and_stops_with_a_valid_key(agent_app, console_key, tmp_path):
    app = create_app(_config(console_key, tmp_path), transport=ASGITransport(app=agent_app, raise_app_exceptions=False))
    with _serve(app) as client:
        assert app.state.ready is True
        assert client.get("/healthz").status_code == 200
    assert app.state.ready is False


async def test_lifespan_refuses_a_revoked_key(agent_app, agent_storage, console_key, tmp_path):
    from ad_seller.auth.api_key_service import ApiKeyService

    _, key_id = console_key
    await ApiKeyService(agent_storage).revoke_key(key_id)
    app = create_app(_config(console_key, tmp_path), transport=ASGITransport(app=agent_app, raise_app_exceptions=False))
    with pytest.raises(RuntimeError, match="rejected"):
        with _serve(app):
            pass


async def test_lifespan_refuses_a_buyer_key(agent_app, agent_storage, tmp_path):
    from ad_seller.auth.api_key_service import ApiKeyService
    from ad_seller.models.api_key import ApiKeyCreateRequest

    buyer = await ApiKeyService(agent_storage).create_key(ApiKeyCreateRequest(agency_id="agy-1", agency_name="Acme", label="acme"))
    config = ConsoleConfig(_env_file=None, seller_agent_url="http://agent.test", console_operator_api_key=buyer.api_key, console_db_url=f"sqlite:///{tmp_path}/c.db")
    app = create_app(config, transport=ASGITransport(app=agent_app, raise_app_exceptions=False))
    # a buyer key is valid, so /me answers 200 with role=buyer: the check must read the role
    with pytest.raises(RuntimeError, match="not an operator key"):
        with _serve(app):
            pass


async def test_startup_retries_while_unreachable_then_gives_up(console_key, tmp_path):
    key, _ = console_key
    config = _config(console_key, tmp_path, console_startup_timeout_seconds=10)
    api = ConsoleApi(httpx.AsyncHTTPTransport(), "http://127.0.0.1:9", key)
    state = ConsoleState(config=config, api=api, store=Store(config.console_db_url))
    ticks = iter([0, 3, 6, 9, 12])
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    try:
        with pytest.raises(RuntimeError, match="could not reach the agent"):
            await verify_console_key(state, clock=lambda: next(ticks), sleep=fake_sleep)
    finally:
        await api.aclose()
    assert len(slept) == 3  # retried at 3, 6, 9; gave up at 12 > deadline 10
```

- [ ] **Step 2: Run, then commit**

```bash
uv run pytest tests/test_startup.py -q
git add tests/test_startup.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "test: startup key check, lifespan, and configuration refusals"
```
Expected: `7 passed`. Revert checks: make `verify_console_key` return immediately: the revoked-key and buyer-key tests must fail; remove `lifespan=lifespan` from the `FastAPI(...)` call: the three lifespan tests must fail; remove the retry branch: the retry test must fail. Restore.

This closes console PR 2: title `feat: console foundation (store, accounts, sessions, login, shell)`.

---

## Task 12: Container, compose, README

**Files:**
- Create: `Dockerfile`, `compose.yml`, `compose.proxy.yml`, `Caddyfile`, `agent.env.example`, `console.env.example`, `scripts/smoke.sh`, `README.md`
- Modify: `.github/workflows/ci.yml` (smoke job)
- Modify: `tests/test_contract.py` (compose pin check)

- [ ] **Step 1: Dockerfile**

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 console && apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 CONSOLE_DB_URL=sqlite:////data/console.db
RUN mkdir -p /data && chown console /data
USER console
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD curl -fs http://localhost:8080/healthz || exit 1
CMD ["uvicorn", "seller_console.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
```

`uv lock` must have been run (Task 0) so `uv.lock` exists. `--no-dev` keeps the agent package out of the image (the runtime never needs it), and `--no-editable` installs the console package into the environment as files, so copying `.venv` alone into the final stage carries the code; an editable install would leave a path pointer at `/build/src`, which does not exist there. The image sets `CONSOLE_DB_URL` to the `/data` volume; the relative default in `config.py` is for development only.

- [ ] **Step 2: Compose file**

The console repository ships a complete stack so the smoke test and a demo need nothing else: the agent is built from its git repository at the pinned version, with the agent's own compose values for Postgres and Redis.

```yaml
# compose.yml — the console next to the pinned agent. Each service reads its own env file
# (agent.env, console.env; see the .example files). No file is shared between services.
services:
  app:
    build:
      context: https://github.com/numarasSigmaSoftware/seller-agent.git#701ce06bff7b7fa607d0156383a757a32992b3e4
      dockerfile: infra/docker/Dockerfile
    environment:
      STORAGE_TYPE: hybrid
      DATABASE_URL: postgresql+asyncpg://seller:seller@postgres:5432/ad_seller
      REDIS_URL: redis://redis:6379/0
    env_file: [agent.env]      # the agent's provider keys and settings; the console never sees this file
    ports: ["127.0.0.1:8000:8000"]
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    restart: unless-stopped
  postgres:
    image: postgres:16-alpine
    environment: { POSTGRES_USER: seller, POSTGRES_PASSWORD: seller, POSTGRES_DB: ad_seller }
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U seller -d ad_seller"], interval: 5s, timeout: 3s, retries: 5 }
  redis:
    image: redis:7-alpine
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 5s, timeout: 3s, retries: 5 }
  console:
    build: .
    image: seller-console:local
    environment:
      SELLER_AGENT_URL: http://app:8000
    env_file: [console.env]    # the console key and settings; the agent never sees this file
    ports: ["127.0.0.1:8080:8080"]   # loopback only; production reaches the console through compose.proxy.yml
    volumes: [console-data:/data]
    depends_on:
      app: { condition: service_healthy }
    restart: unless-stopped
volumes:
  pgdata:
  console-data:
```

The git build context is what keeps the compose file self-contained; the commit after `#` is the full SHA in `contract/AGENT_VERSION`, and a test below checks that. To add the console to an existing agent stack instead, copy only the `console` service and the `console-data` volume into that stack's compose file.

`compose.proxy.yml`, the production overlay, puts a TLS-terminating proxy in front and stops publishing the console port; the console is then reachable only through the proxy, which is what SSO mode requires:

```yaml
# compose.proxy.yml — production: docker compose -f compose.yml -f compose.proxy.yml up -d
services:
  console:
    ports: !reset []           # not published; only the proxy reaches it on the compose network
  proxy:
    image: caddy:2-alpine
    ports: ["443:443", "80:80"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
    depends_on:
      console: { condition: service_healthy }
volumes:
  caddy-data:
```

with a `Caddyfile` in the repository (`console.example.com { reverse_proxy console:8080 }`; Caddy obtains the certificate; the hostname is the one line an operator edits).

```
# Caddyfile — replace the hostname; Caddy obtains and renews the certificate
console.example.com {
    reverse_proxy console:8080
}
``` An identity-aware proxy such as oauth2-proxy slots in the same place and sets the header named by `CONSOLE_TRUSTED_IDENTITY_HEADER`; `CONSOLE_TRUSTED_PROXY_CIDRS` is then the compose network.

- [ ] **Step 3: the two env example files**

`agent.env.example` (copied to `agent.env`; the agent's own variables, see the seller-agent repository):

```bash
# ANTHROPIC_API_KEY=
# GAM_ENABLED=false
```

`console.env.example` (copied to `console.env`):

```bash
CONSOLE_OPERATOR_API_KEY=            # docker compose run --rm app ad-seller create-operator-key --label console --quiet
# CONSOLE_OPERATOR_API_KEY_FILE=     # alternative: path of a mounted secret file holding the key; wins over the variable
CONSOLE_SESSION_TTL_HOURS=12
# CONSOLE_ROOT_PATH=                 # mount prefix when served behind a proxy prefix, e.g. /console
# CONSOLE_TRUSTED_IDENTITY_HEADER=   # e.g. X-Forwarded-Email behind an identity-aware proxy
# CONSOLE_TRUSTED_PROXY_CIDRS=       # networks the header is trusted from, e.g. 10.0.1.0/24
# CONSOLE_STARTUP_TIMEOUT_SECONDS=60
```

Both `agent.env` and `console.env` are in `.gitignore`.

- [ ] **Step 4: README**

```markdown
# Seller Agent Console

A browser control room for the people who supervise the IAB Tech Lab seller agent. It runs as its own container next to the agent and talks to it only through the agent's REST API.

## Run it

1. Copy `agent.env.example` to `agent.env` and `console.env.example` to `console.env`. Each service reads only its own file.
2. Mint the console's operator key on the agent and put it in `console.env` (or mount it as a file and set `CONSOLE_OPERATOR_API_KEY_FILE`):
   ```bash
   docker compose run --rm app ad-seller create-operator-key --label console --quiet
   ```
3. Start everything: `docker compose up -d --build`. The console waits for the agent to be healthy, verifies its key, and refuses to start if the key is missing, revoked, or not an operator key.
4. Create an account, then sign in at http://localhost:8080/:
   ```bash
   docker compose exec console seller-console create-user --username nicolas
   ```
   Reset with `--reset-password`, disable with `--disable`. Passwords are prompted, at least 12 characters, stored as scrypt hashes.

## How it works

Every page reads through the agent's API with the console key and an `X-Console-User` header naming the person (context for logs, not attribution). Sessions are opaque tokens in the console's own SQLite store on the `/data` volume, 12 hours by default, ended at once when an account is disabled or its password reset. Five failed logins per username or client address in ten minutes are refused for ten minutes. Revoking the console key on the agent ends all console access; the landing page shows the rejected key.

## Single sign-on

Behind an identity-aware proxy that sets a verified identity header, set `CONSOLE_TRUSTED_IDENTITY_HEADER` and `CONSOLE_TRUSTED_PROXY_CIDRS`. The header is then required on every request and trusted only from those networks, the password login is switched off, and accounts are looked up by the header value, so create them with the email as the username. The console must not be reachable except through the proxy.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SELLER_AGENT_URL` | required | base URL of the agent's API |
| `CONSOLE_OPERATOR_API_KEY` | required unless the file variable is set | operator key for every API call |
| `CONSOLE_OPERATOR_API_KEY_FILE` | empty | mounted secret file holding the key; wins over the variable |
| `CONSOLE_DB_URL` | `sqlite:///data/console.db` (image: `sqlite:////data/console.db`) | the console's own store |
| `CONSOLE_ROOT_PATH` | empty | mount prefix behind a proxy prefix |
| `CONSOLE_SESSION_TTL_HOURS` | `12` | session lifetime |
| `CONSOLE_TRUSTED_IDENTITY_HEADER` | empty | when set, SSO mode |
| `CONSOLE_TRUSTED_PROXY_CIDRS` | empty | networks the header is trusted from; required in SSO mode |
| `CONSOLE_STARTUP_TIMEOUT_SECONDS` | `60` | how long to wait for the agent at startup |

## Agent version

The console is built and tested against the agent commit in `contract/AGENT_VERSION`; `contract/openapi.json` is that agent's API document and the tests fail if the two diverge. To move the pin: update `AGENT_VERSION`, the dev dependency in `pyproject.toml`, and the build context in `compose.yml` to the same commit, run `uv lock`, regenerate the document (`uv run python -c "import json; from ad_seller.interfaces.api.main import app; print(json.dumps(app.openapi(), indent=2, sort_keys=True))" > contract/openapi.json`), and run the tests.

## Production

`docker compose -f compose.yml -f compose.proxy.yml up -d` adds a TLS proxy (Caddy; `Caddyfile`: `console.example.com { reverse_proxy console:8080 }`) and stops publishing the console port. The development stack binds the console and the agent to loopback only.

## Development

```bash
uv sync --extra dev   # installs the pinned agent for the tests
uv run pytest -q
uv run uvicorn seller_console.main:create_app --factory --reload --port 8080
```
```

- [ ] **Step 5: The checked smoke script**

`scripts/smoke.sh` runs the whole stack and asserts every step with exit codes. CI runs it; so does Task 14 by hand.

```bash
#!/usr/bin/env bash
# Compose smoke: a bad key stops the console; a good key serves; no service sees another's secrets.
set -euo pipefail
cd "$(dirname "$0")/.."
cleanup() { docker compose down -v --remove-orphans >/dev/null 2>&1 || true; rm -f agent.env console.env; }
trap cleanup EXIT

cp agent.env.example agent.env
cp console.env.example console.env
echo "ANTHROPIC_API_KEY=sk-ant-smoke-secret" >> agent.env

# 0. secret isolation: render the configuration and check each service's environment
docker compose config --format json > /tmp/compose.json
python3 - <<'EOF'
import json, sys
cfg = json.load(open("/tmp/compose.json"))
env = {name: svc.get("environment", {}) for name, svc in cfg["services"].items()}
bad = []
if any(k.startswith("CONSOLE_") for k in env["app"]): bad.append("agent sees console variables")
if "ANTHROPIC_API_KEY" in env["console"] or any(k.endswith("_API_KEY") and not k.startswith("CONSOLE_") for k in env["console"]): bad.append("console sees agent secrets")
if bad: print("SECRET ISOLATION FAILED:", bad); sys.exit(1)
print("secret isolation ok")
EOF

# 1. a bad key must stop the console
sed -i.bak 's/^CONSOLE_OPERATOR_API_KEY=.*/CONSOLE_OPERATOR_API_KEY=ask_live_bogus/' console.env
docker compose up -d --build app postgres redis
if docker compose up --build --abort-on-container-exit --exit-code-from console console; then
  echo "console started with a bogus key"; exit 1
fi
docker compose logs console 2>&1 | grep -q "was rejected by the agent" || { echo "no rejected-key log line"; exit 1; }

# 2. the real key and an account
KEY=$(docker compose run --rm -T app ad-seller create-operator-key --label console --quiet)
sed -i.bak "s|^CONSOLE_OPERATOR_API_KEY=.*|CONSOLE_OPERATOR_API_KEY=$KEY|" console.env
docker compose up -d --build console
for _ in $(seq 1 30); do
  curl -fs http://127.0.0.1:8080/healthz >/dev/null && break
  sleep 2
done
curl -fs http://127.0.0.1:8080/healthz | grep -q '"status":"ok"' || { echo "healthz not ok"; exit 1; }
printf 'correct horse battery\ncorrect horse battery\n' | docker compose exec -T console seller-console create-user --username smoke

# 3. the console serves
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/login)" = "200" ] || { echo "login page not 200"; exit 1; }
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/static/htmx.min.js)" = "200" ] || { echo "htmx not served"; exit 1; }
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/)" = "303" ] || { echo "landing did not redirect to login"; exit 1; }
echo "smoke ok"
```

```bash
chmod +x scripts/smoke.sh
```

Add a second job to `.github/workflows/ci.yml`:

```yaml
  smoke:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - run: scripts/smoke.sh
```

The job builds the pinned agent from git inside the runner; it takes several minutes and needs no secrets.

- [ ] **Step 6: Add the pin check and commit**

Append to `tests/test_contract.py`:

```python
def test_compose_builds_the_pinned_agent():
    version = (REPO / "contract" / "AGENT_VERSION").read_text().strip()
    assert f"seller-agent.git#{version}" in (REPO / "compose.yml").read_text()
```

```bash
uv run pytest tests/test_contract.py -q
docker build -t seller-console:local .
git add Dockerfile compose.yml compose.proxy.yml Caddyfile agent.env.example console.env.example README.md scripts/smoke.sh .github/workflows/ci.yml tests/test_contract.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: container image, compose stack with the pinned agent, proxy overlay, checked smoke, README"
```
Expected: `4 passed`; the image builds; `scripts/smoke.sh` prints `secret isolation ok` and `smoke ok` locally before the push, and the `smoke` job is green on the PR.

---

## Task 13: The landing page and the health partial

**Files:**
- Modify: `src/seller_console/routes.py` (append)
- Test: `tests/test_home.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_home.py
"""The landing page: four cards from the real agent, degrading one card at a time."""

import asyncio

from tests.conftest import html_index, login


async def test_home_requires_login(client):
    response = await client.get("/")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


async def test_home_renders_shell_and_cards(client, account, console_key):
    _, key_id = console_key
    await login(client)
    page = await client.get("/")
    assert page.status_code == 200
    els = html_index(page.text)
    assert "nicolas" in els["who"]["text"]
    assert "active" in els["nav-setup"]["attrs"]["class"]
    assert els["nav-inbox"]["tag"] == "div" and "soon" in els["nav-inbox"]["text"]
    assert els["card-agent"]["attrs"]["data-state"] == "ok"
    assert "Healthy" in els["card-agent"]["text"] and "Ad Seller System API" in els["card-agent"]["text"]
    assert els["card-access"]["attrs"]["data-state"] == "ok"
    assert "nicolas" in els["card-access"]["text"] and key_id in els["card-access"]["text"]
    assert els["card-sync"]["attrs"]["data-state"] == "ok" and "Disabled" in els["card-sync"]["text"]
    assert els["card-events"]["attrs"]["data-state"] == "ok"
    assert "No events yet" in els["card-events"]["text"] or "Last event" in els["card-events"]["text"]
    assert 'hx-get="/partials/health"' in page.text and 'hx-trigger="every 30s"' in page.text
    assert 'href="/static/console.css"' in page.text


async def test_partial_returns_cards_without_shell(client, account):
    await login(client)
    partial = await client.get("/partials/health", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "<html" not in partial.text and "card-agent" in partial.text


async def test_partial_without_session_tells_htmx_to_redirect(client):
    partial = await client.get("/partials/health", headers={"HX-Request": "true"})
    assert partial.status_code == 401
    assert partial.headers["hx-redirect"].startswith("/login")


async def test_revoked_console_key_degrades_access_card_only(client, account, agent_storage, console_key):
    from ad_seller.auth.api_key_service import ApiKeyService

    _, key_id = console_key
    await login(client)
    await ApiKeyService(agent_storage).revoke_key(key_id)
    page = await client.get("/")
    els = html_index(page.text)
    assert page.status_code == 200
    assert els["card-access"]["attrs"]["data-state"] == "rejected"
    assert els["card-agent"]["attrs"]["data-state"] == "ok"  # health and root need no key
    assert (await client.get("/")).status_code == 200  # the session survives


async def test_slow_route_degrades_its_card(client, console_app, agent_app, account):
    from ad_seller.interfaces.api import deps

    await login(client)

    async def slow():
        await asyncio.sleep(0.5)

    agent_app.dependency_overrides[deps._require_api_key_record] = slow
    console_app.state.console.api._timeout = 0.05
    try:
        page = await client.get("/")
    finally:
        agent_app.dependency_overrides.clear()
    els = html_index(page.text)
    assert page.status_code == 200
    assert els["card-access"]["attrs"]["data-state"] == "unavailable" and "timeout" in els["card-access"]["text"]
    assert els["card-agent"]["attrs"]["data-state"] == "ok"


async def test_unreachable_agent_degrades_every_card_but_keeps_the_page(client, console_app, account):
    import httpx

    await login(client)
    api = console_app.state.console.api
    await api._client.aclose()
    api._client = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(), base_url="http://127.0.0.1:9")  # nothing listens
    page = await client.get("/")
    els = html_index(page.text)
    assert page.status_code == 200
    for slug in ("agent", "access", "sync", "events"):
        assert els[f"card-{slug}"]["attrs"]["data-state"] == "unavailable"
        assert "unreachable" in els[f"card-{slug}"]["text"]


async def test_malformed_api_body_degrades_one_card(client, console_app, account, monkeypatch):
    await login(client)
    api = console_app.state.console.api
    real_get = api._get

    async def get(path, user, params=None):
        return [] if path == "/health" else await real_get(path, user, params)

    monkeypatch.setattr(api, "_get", get)
    page = await client.get("/")
    els = html_index(page.text)
    assert els["card-agent"]["attrs"]["data-state"] == "unavailable"
    assert "unexpected response shape" in els["card-agent"]["text"]
    assert els["card-access"]["attrs"]["data-state"] == "ok"


async def test_unexpected_error_renders_error_page(client, account, caplog):
    from seller_console import routes

    await login(client)

    def boom(*args, **kwargs):
        raise RuntimeError("template exploded")

    original = routes.build_cards
    routes.build_cards = boom
    try:
        page = await client.get("/")
    finally:
        routes.build_cards = original
    assert page.status_code == 500
    assert len(html_index(page.text)["request-id"]["text"]) == 8
    assert "template exploded" not in page.text
    assert "template exploded" in caplog.text
    assert client.cookies["console_session"] not in caplog.text
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/test_home.py -q
```
Expected: 404s and an `AttributeError` for `build_cards`.

- [ ] **Step 3: Append the cards, home, and partial to `routes.py`** (and drop the `# noqa: F401` markers from Task 10)

```python
def _card(slug: str, title: str, state: str, tone: str, value: str, detail: str) -> dict[str, str]:
    return {"slug": slug, "title": title, "state": state, "tone": tone, "value": value, "detail": detail}


def _degraded(slug: str, title: str, exc: Exception) -> dict[str, str]:
    if isinstance(exc, ApiRejected):
        reason = "console key rejected" if exc.status == 401 else "console key is not an operator key"
        return _card(slug, title, "rejected", "error", "Console key rejected", f"{reason} (HTTP {exc.status}); replace CONSOLE_OPERATOR_API_KEY")
    if isinstance(exc, ApiUnavailable):
        return _card(slug, title, "unavailable", "warn", "Unavailable", f"{exc.detail} (status {exc.status})")
    raise exc


async def _call(coro: Awaitable[Any]) -> Any:
    try:
        return await coro
    except (ApiRejected, ApiUnavailable) as exc:
        return exc


def _agent_card(result: Health | Exception, checked: str) -> dict[str, str]:
    if isinstance(result, Exception):
        return _degraded("agent", "Agent", result)
    healthy = result.status == "healthy"
    return _card("agent", "Agent", "ok", "ok" if healthy else "error", "Healthy" if healthy else result.status.title(), f"{result.name} {result.version} · checked {checked}")


def _access_card(result: KeyInfo | Exception, operator: Operator) -> dict[str, str]:
    if isinstance(result, Exception):
        return _degraded("access", "Console access", result)
    if operator.session_expires_at is not None:
        left = operator.session_expires_at - datetime.now(timezone.utc)
        session = f"session {max(int(left.total_seconds() // 3600), 0)} h left"
    else:
        session = "signed in through the identity proxy"
    status = "active" if result.is_active else "revoked or expired"
    return _card("access", "Console access", "ok", "ok" if result.is_active else "error", f"{operator.username} · {session}",
                 f"API calls use key {result.label} ({result.key_id}), {status}, expires: {result.expires_at or 'never'}")


def _sync_card(result: SyncStatus | Exception) -> dict[str, str]:
    if isinstance(result, Exception):
        return _degraded("sync", "Inventory sync", result)
    return _card("sync", "Inventory sync", "ok", "ok" if result.enabled else "warn", "Enabled" if result.enabled else "Disabled",
                 f"last sync: {result.last_sync or 'no sync yet'} · runs: {result.sync_count}")


def _events_card(result: EventSummary | None | Exception) -> dict[str, str]:
    """Only what the agent says: the console reads no agent settings."""
    if isinstance(result, Exception):
        return _degraded("events", "Event bus", result)
    if result is None:
        return _card("events", "Event bus", "ok", "warn", "No events yet", "the bus has published nothing this process can see")
    return _card("events", "Event bus", "ok", "ok", "Last event", f"{result.event_type} at {result.timestamp}")


async def build_cards(state: ConsoleState, operator: Operator) -> tuple[list[dict[str, str]], str]:
    api, user = state.api, operator.username
    health, me, sync, event = await asyncio.gather(
        _call(api.health(user)), _call(api.me(user)), _call(api.inventory_sync_status(user)), _call(api.last_event(user))
    )
    checked = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return [_agent_card(health, checked), _access_card(me, operator), _sync_card(sync), _events_card(event)], checked


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, operator: Operator = Depends(current_operator)) -> Any:
    cards, checked = await build_cards(_state(request), operator)
    return await _render(request, "home.html", operator=operator, nav=_nav("setup"), cards=cards, checked_at=checked)


@router.get("/partials/health", response_class=HTMLResponse)
async def health_partial(request: Request, operator: Operator = Depends(current_operator)) -> Any:
    cards, checked = await build_cards(_state(request), operator)
    return await _render(request, "partials/health_cards.html", operator=operator, cards=cards, checked_at=checked, issue_csrf=False)
```

`home` and `health_partial` look up `build_cards` as a module global at call time, which is what lets the error-page test replace it.

- [ ] **Step 4: Run to verify they pass, then commit**

```bash
uv run pytest tests -q
uv run ruff format src tests && uv run ruff check src tests
git add src/seller_console/routes.py tests/test_home.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: landing page with agent, access, sync, and event cards"
```
Expected: `test_home.py`: 9 passed; whole suite green. Revert checks: remove the `except` in `_call`: the three degradation tests must fail; remove `add_exception_handler` in `create_app`: the error-page test must fail. Restore.

This closes console PR 4: title `feat: landing page (Setup and health)`.

---

## Task 14: Full suite, compose smoke, and the manual browser smoke test

**Files:** none changed unless the runs find something.

Browser automation is intentionally deferred from the Foundation. Server-side tests verify the HTMX attributes, the partial response, asset serving, and the HX-Redirect behaviour. Before PR 4 (the landing page) merges, the manual smoke test below must confirm login, the 30-second DOM refresh, the session-expiry redirect, and logout; the stack it runs on landed in PR 3. Browser automation is added before the first mutating or multi-step HTMX workflow.

- [ ] **Step 1: Full test suite**

```bash
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
```
Expected: about 90 passed, none skipped. Any failure is fixed, never deselected.

- [ ] **Step 2: Compose smoke**

```bash
scripts/smoke.sh
```
Expected: the script exits 0 after printing `secret isolation ok` and `smoke ok`; any failed assertion names itself and exits 1. The script tears the stack down; for the browser check below, start it again with a real key:

```bash
cp agent.env.example agent.env && cp console.env.example console.env
docker compose up -d --build app postgres redis
KEY=$(docker compose run --rm -T app ad-seller create-operator-key --label console --quiet)
sed -i.bak "s|^CONSOLE_OPERATOR_API_KEY=.*|CONSOLE_OPERATOR_API_KEY=$KEY|" console.env
docker compose up -d --build console
printf 'correct horse battery\ncorrect horse battery\n' | docker compose exec -T console seller-console create-user --username nicolas
```

- [ ] **Step 3: Manual browser smoke test (required before PR 4 merges)**

With that stack running, in a browser, confirm each and tick them in the PR body:

1. `http://localhost:8080/` redirects to the login page; a wrong password shows the generic message; the right one lands on Setup and health with four cards, the Agent card healthy.
2. Wait 30 seconds without reloading: the "checked" time in the Agent card advances.
3. Session expiry: delete the session records and wait for the next poll:
   ```bash
   docker compose exec console python -c "
   import asyncio, os
   from seller_console.store import Store
   async def main():
       s = Store(os.environ['CONSOLE_DB_URL']); await s.connect()
       for k in await s.keys('session:*'): await s.delete(k)
       await s.close()
   asyncio.run(main())"
   ```
   The next poll must send the browser to the login page, not leave a stale page.
4. Sign out returns to the login page, and the back button does not show the landing page without a new login.
5. Stop the agent (`docker compose stop app`), reload the console: all four cards read "unavailable, agent unreachable", the page is still served, and logging out and in still works. Start the agent again: the cards recover on the next poll.

```bash
docker compose down -v && rm -f agent.env console.env console.env.bak
```

This closes console PR 3: title `feat: container image, compose stack, README, and smoke`.

---

## Self-review against the spec

- §3 repository, package, contract, agent enablers, CLI: Tasks 0, 1, 5, 6, 9, 10, 12. The runtime-never-imports-the-agent rule and the drift test: Task 0; the compose pin check: Task 12; the pinned HTMX digest: Task 9.
- §4 store with compare-and-set, accounts with credential versions, reserve-then-count login, synchronizer CSRF, sessions, `current_operator`, console key from variable or file: Tasks 3, 4, 5, 7, 10, 11; startup retry with the compose ordering: Tasks 11 and 12.
- §5 pages and palette: Tasks 9 and 12.
- §6 client with injected transport, one long-lived client closed by the lifespan, 2xx-only, typed responses, connection errors: Task 8.
- §7 error handling including "agent unreachable", redirects, CSRF, and `/healthz`: Tasks 8, 10, 13.
- §8 testing: real store, real pinned agent, race tests on two connections, boundary-forced failures, HTML by id, security and structural and wiring tests, the lifespan through `TestClient`, the checked smoke in CI, browser decision: every task, Task 14.
- §9 configuration (root path, key file), per-service env files, proxy overlay, README: Tasks 3 and 12.
- §10 delivery: PR boundaries after Tasks 0, 2, 11, 12, 14; the container lands before the landing page so the browser check has a stack.
- §11 and §12 are not built here, by design.
