# Console Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A person can enable the console with two environment variables, create an account with one CLI command, log in from a browser, and see the agent's health, their session, inventory sync, and the event bus on a landing page that refreshes itself.

**Architecture:** A new package `src/ad_seller/interfaces/console/` is a FastAPI sub-application mounted at `/console` on the existing app when `CONSOLE_ENABLED=true`. Pages are Jinja2 templates with HTMX partials. Every read goes through the existing REST API in-process (httpx ASGI transport) with one server-held operator key and an `X-Console-User` header. Accounts and sessions live in the existing key-value store.

**Tech Stack:** Python 3.11, FastAPI, Starlette, Jinja2, HTMX 2 (vendored), httpx, pytest with pytest-asyncio, uv.

**Spec:** `docs/superpowers/specs/2026-09-15-console-foundation-design.md`

---

## Working rules for every task

- Worktree: the branch is cut from the fork's `ui/dev`. Run every command from the repository root of that worktree.
- Test command prefix. The sibling worktrees share one virtual environment whose editable install points elsewhere, so every `pytest`, `ruff`, and `python` invocation in this plan is written as:
  ```bash
  PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync <command>
  ```
  If you are in a normal checkout with its own `.venv`, drop the prefix and use `uv run <command>`.
- Before any test run and before any commit: `rm -f ad_seller.db data/audit_fallback.jsonl`. The unit suite writes a real SQLite file, and stale idempotency records make unrelated tests fail (upstream issue #82).
- Commit author: `git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit ...`. No co-author trailers.
- Format and lint the files a commit touches before committing: `uv run --no-sync ruff format <paths> && uv run --no-sync ruff check <paths>` (with the prefix above).
- The repository's hygiene hook rejects commit messages containing bead ids or session trailers. Keep messages to a conventional-commit subject and a short body.
- Never `git add -A`. Stage explicit paths.

## File structure

New files:

| Path | Responsibility |
|---|---|
| `src/ad_seller/interfaces/console/__init__.py` | `mount_console(root_app, config)`, `verify_console_key(root_app)`, the sub-application object |
| `src/ad_seller/interfaces/console/config.py` | `ConsoleConfig` dataclass and `from_settings()` |
| `src/ad_seller/interfaces/console/accounts.py` | password hashing, account records, credential check; the only module that touches storage for accounts |
| `src/ad_seller/interfaces/console/auth.py` | sessions, CSRF cookie, login rate limit, `Operator`, `current_operator` dependency |
| `src/ad_seller/interfaces/console/client.py` | `ConsoleApi`: in-process HTTP client to the REST API, `ApiRejected`, `ApiUnavailable` |
| `src/ad_seller/interfaces/console/routes.py` | login, logout, landing page, health partial, rendering helpers |
| `src/ad_seller/interfaces/console/templates/base.html` | shell: top bar, sidebar, content block |
| `src/ad_seller/interfaces/console/templates/login.html` | login card |
| `src/ad_seller/interfaces/console/templates/home.html` | landing page |
| `src/ad_seller/interfaces/console/templates/partials/health_cards.html` | the four cards |
| `src/ad_seller/interfaces/console/templates/error.html` | unexpected-error page |
| `src/ad_seller/interfaces/console/static/htmx.min.js` | vendored HTMX 2.0.4 |
| `src/ad_seller/interfaces/console/static/console.css` | the IAB palette and layout |
| `tests/unit/console/__init__.py` | package marker |
| `tests/unit/console/conftest.py` | real SQLite storage, minted console key, a fresh API app with the console mounted, an httpx client |
| `tests/unit/console/test_accounts.py` | hashing and account records |
| `tests/unit/console/test_cli_console_user.py` | the CLI command |
| `tests/unit/console/test_auth.py` | sessions, rate limit, `current_operator` |
| `tests/unit/console/test_client.py` | `ConsoleApi` against the real API |
| `tests/unit/console/test_login_routes.py` | login, logout, cookies, CSRF, rate limit |
| `tests/unit/console/test_home.py` | landing page, partial, degraded cards |
| `tests/unit/console/test_startup.py` | key verification at startup, mount guard |
| `tests/unit/console/test_import_rule.py` | the console never imports internals |
| `tests/unit/test_api_key_me_route.py` | the new `me` route |
| `docs/guides/console.md` | operator guide |

Modified files:

| Path | Change |
|---|---|
| `src/ad_seller/interfaces/api/deps.py` | add `_require_api_key_record` wrapper |
| `src/ad_seller/interfaces/api/routers/admin.py` | add `GET /auth/api-keys/me` before the `{key_id}` route |
| `src/ad_seller/config/settings.py` | four `console_*` settings |
| `src/ad_seller/interfaces/api/main.py` | flag-gated mount at the end; startup key check in `lifespan` |
| `src/ad_seller/interfaces/cli/main.py` | `create-console-user` command |
| `pyproject.toml`, `uv.lock` | `jinja2` and `python-multipart` become direct dependencies |
| `docs/api/openapi.json`, `docs/reference/endpoints.md` | regenerated |
| `docs/api/overview.md`, `docs/index.md`, `README.md` | endpoint count 88 to 89, `me` row |
| `mkdocs.yml` | nav entry for the guide |
| `.env.example`, `infra/docker/docker-compose.yml` | commented console variables |
| `CHANGELOG.md` | Unreleased entries |

Delivery: tasks 1 to 2 are pull request 1 (`me` route, also upstream). Tasks 3 to 10 are pull request 2 (console package). Tasks 11 to 12 are pull request 3 (landing page). Task 13 is pull request 4 (docs and examples). Each PR targets `ui/dev` on the fork.

---

## Task 1: `GET /auth/api-keys/me`

**Files:**
- Modify: `src/ad_seller/interfaces/api/deps.py` (after `_require_operator_api_key_record`)
- Modify: `src/ad_seller/interfaces/api/routers/admin.py` (before `get_api_key_details`, currently line 171)
- Test: `tests/unit/test_api_key_me_route.py`

Route order matters: `/auth/api-keys/{key_id}` already exists, so `/auth/api-keys/me` must be registered before it or `me` is captured as a key id and answers 404.

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
Expected: `test_me_route_is_registered_before_key_id_route` fails with `'/auth/api-keys/me' is not in list`; the keyed tests fail with 404 (captured by `{key_id}`).

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

In `src/ad_seller/interfaces/api/routers/admin.py`, insert immediately before `@router.get("/auth/api-keys/{key_id}", tags=["Authentication"])`:

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

Temporarily move the new route below `get_api_key_details`, rerun: `test_me_route_is_registered_before_key_id_route` and the two keyed tests must fail. Restore the order and confirm green.

- [ ] **Step 7: Format, lint, commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/api/deps.py src/ad_seller/interfaces/api/routers/admin.py tests/unit/test_api_key_me_route.py
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/api/deps.py src/ad_seller/interfaces/api/routers/admin.py tests/unit/test_api_key_me_route.py
git add src/ad_seller/interfaces/api/deps.py src/ad_seller/interfaces/api/routers/admin.py tests/unit/test_api_key_me_route.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: add GET /auth/api-keys/me so a caller can read its own key metadata"
```

---

## Task 2: Regenerate the API documents for the `me` route

**Files:**
- Regenerate: `docs/api/openapi.json`, `docs/reference/endpoints.md`
- Modify: `docs/api/overview.md` (line 3 count; Authentication table around line 116), `docs/index.md` (three counts), `README.md` (two counts), `CHANGELOG.md`

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
git diff --stat
```
Expected: `docs/api/openapi.json` and `docs/reference/endpoints.md` changed; the endpoints total reads 89.

- [ ] **Step 3: Update the hand-written counts and the Authentication table**

```bash
grep -rn "88 endpoints\|88 REST endpoints\|all 88 endpoints" docs/api/overview.md docs/index.md README.md
```
Change every `88` in those hits to `89` (six places: `docs/api/overview.md:3`, `docs/index.md:15`, `docs/index.md:20`, `docs/index.md:57`, `README.md:34`, `README.md:218`).

In `docs/api/overview.md`, in the Authentication table that contains the row for `POST /auth/api-keys/operator`, add after it:

```markdown
| GET | `/auth/api-keys/me` | The calling key's own metadata, no secret (any valid key) |
```

Also change the sentence above that table from "All `/auth/api-keys*` routes require an **operator** credential." to "All `/auth/api-keys*` routes require an **operator** credential, except `GET /auth/api-keys/me`, which any valid key may call."

- [ ] **Step 4: CHANGELOG**

Under `## [Unreleased]` → `### Added`, add as the first bullet:

```markdown
- `GET /auth/api-keys/me` returns the calling key's own metadata, so a
  client can learn which key it holds without listing every key.
```

- [ ] **Step 5: Run the drift tests and the full unit suite**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit -q -p no:warnings --timeout=600
```
Expected: all passed (1544 or more), including both drift tests.

- [ ] **Step 6: Commit**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
git add docs/api/openapi.json docs/reference/endpoints.md docs/api/overview.md docs/index.md README.md CHANGELOG.md
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "docs: document GET /auth/api-keys/me and regenerate the API inventories"
```

This closes pull request 1. Open it against `ui/dev` on the fork with title `feat: add GET /auth/api-keys/me` and, once green, the same branch against upstream `main`.

---

## Task 3: Settings and dependencies

**Files:**
- Modify: `src/ad_seller/config/settings.py` (after `api_key_default_expiry_days`, line 246)
- Modify: `pyproject.toml` (dependencies list), `uv.lock`
- Test: `tests/unit/console/test_settings.py`

- [ ] **Step 1: Create the test package and write the failing test**

```bash
mkdir -p tests/unit/console && touch tests/unit/console/__init__.py
```

```python
# tests/unit/console/test_settings.py
"""The console is off by default and every console setting has a documented default."""

from ad_seller.config.settings import Settings


def test_console_defaults(monkeypatch):
    for name in (
        "CONSOLE_ENABLED",
        "CONSOLE_OPERATOR_API_KEY",
        "CONSOLE_SESSION_TTL_HOURS",
        "CONSOLE_TRUSTED_IDENTITY_HEADER",
        "CONSOLE_TRUSTED_PROXY_CIDRS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.console_enabled is False
    assert settings.console_operator_api_key is None
    assert settings.console_session_ttl_hours == 12
    assert settings.console_trusted_identity_header == ""
    assert settings.console_trusted_proxy_cidrs == ""


def test_console_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("CONSOLE_ENABLED", "true")
    monkeypatch.setenv("CONSOLE_OPERATOR_API_KEY", "ask_live_abc")
    monkeypatch.setenv("CONSOLE_SESSION_TTL_HOURS", "2")
    monkeypatch.setenv("CONSOLE_TRUSTED_IDENTITY_HEADER", "X-Forwarded-Email")
    monkeypatch.setenv("CONSOLE_TRUSTED_PROXY_CIDRS", "10.0.0.0/8, 127.0.0.1/32")
    settings = Settings(_env_file=None)
    assert settings.console_enabled is True
    assert settings.console_operator_api_key == "ask_live_abc"
    assert settings.console_session_ttl_hours == 2
    assert settings.console_trusted_identity_header == "X-Forwarded-Email"
    assert settings.console_trusted_proxy_cidrs == "10.0.0.0/8, 127.0.0.1/32"
```

- [ ] **Step 2: Run to verify it fails**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_settings.py -q -p no:warnings
```
Expected: `AttributeError: 'Settings' object has no attribute 'console_enabled'`.

- [ ] **Step 3: Add the settings**

In `src/ad_seller/config/settings.py`, after the line `api_key_default_expiry_days: Optional[int] = None  # None = never expires`, add:

```python
    # Operator console (interfaces/console). Off by default; when enabled,
    # CONSOLE_OPERATOR_API_KEY must hold an operator key minted for the
    # console (ad-seller create-operator-key --label console). The key is
    # verified at startup and never sent to a browser.
    console_enabled: bool = False
    console_operator_api_key: Optional[str] = None
    console_session_ttl_hours: int = 12
    # SSO mode. When CONSOLE_TRUSTED_IDENTITY_HEADER is set (e.g.
    # X-Forwarded-Email behind an identity-aware proxy) the console trusts
    # that header as the username, requires it on every request, and turns
    # the password login off. The header is only trusted when the request
    # comes from CONSOLE_TRUSTED_PROXY_CIDRS (comma-separated networks);
    # SSO mode refuses to start without them.
    console_trusted_identity_header: str = ""
    console_trusted_proxy_cidrs: str = ""
```

- [ ] **Step 4: Make Jinja2 and the multipart parser direct dependencies**

Both are already in `uv.lock` as transitive dependencies; FastAPI templating and `Form(...)` need them at import time, so declare them. In `pyproject.toml`, add to `dependencies` after `"uvicorn>=0.30.0",`:

```toml
    "jinja2>=3.1.0",
    "python-multipart>=0.0.20",
```

Then:

```bash
uv lock
git diff --stat uv.lock
```
Expected: a small diff touching only the project's own dependency block.

- [ ] **Step 5: Run to verify it passes**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_settings.py -q -p no:warnings
```
Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/config/settings.py tests/unit/console/test_settings.py
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/config/settings.py tests/unit/console/test_settings.py
git add src/ad_seller/config/settings.py pyproject.toml uv.lock tests/unit/console/__init__.py tests/unit/console/test_settings.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: add console settings and declare jinja2 and python-multipart"
```

---

## Task 4: Accounts and password hashing

**Files:**
- Create: `src/ad_seller/interfaces/console/__init__.py` (empty for now; filled in Task 9)
- Create: `src/ad_seller/interfaces/console/accounts.py`
- Create: `tests/unit/console/conftest.py`
- Test: `tests/unit/console/test_accounts.py`

- [ ] **Step 1: Write the shared fixtures**

```python
# tests/unit/console/conftest.py
"""Fixtures for the console tests.

Real SQLite storage on a temporary path (never the repo's ad_seller.db), a
real operator key minted through the key service, and ``get_storage`` patched
so both the console and the REST routes read the same backend.
"""

from unittest.mock import patch

import pytest

from ad_seller.auth.api_key_service import ApiKeyService
from ad_seller.models.api_key import OperatorApiKeyCreateRequest
from ad_seller.storage.sqlite_backend import SQLiteBackend


@pytest.fixture
async def storage(tmp_path):
    backend = SQLiteBackend(f"sqlite:///{tmp_path}/console.db")
    await backend.connect()
    with patch("ad_seller.storage.factory.get_storage", return_value=backend):
        yield backend
    await backend.disconnect()


@pytest.fixture
async def console_key(storage):
    """Raw operator key labelled 'console', plus its key_id, as (key, key_id)."""
    created = await ApiKeyService(storage).create_operator_key(
        OperatorApiKeyCreateRequest(label="console")
    )
    return created.api_key, created.key_id
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/unit/console/test_accounts.py
"""Console accounts: scrypt hashes, constant-shape credential checks, CLI-only lifecycle."""

import pytest

from ad_seller.interfaces.console import accounts


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


async def test_create_and_get_account(storage):
    account = await accounts.create_account("nicolas", "correct horse battery")
    assert account.username == "nicolas"
    assert account.role == "operator"
    assert account.disabled is False
    stored = await storage.get("console_user:nicolas")
    assert "correct horse battery" not in str(stored)
    assert set(stored) == {
        "username", "password_hash", "role", "disabled",
        "created_at", "last_login_at", "credentials_changed_at",
    }
    assert stored["password_hash"].startswith("scrypt$17$8$1$")
    assert account.credentials_changed_at == stored["credentials_changed_at"]
    assert (await accounts.get_account("nicolas")).username == "nicolas"
    assert await accounts.get_account("nobody") is None


async def test_short_password_rejected(storage):
    with pytest.raises(ValueError, match="12 characters"):
        await accounts.create_account("nicolas", "short")


async def test_bad_username_rejected(storage):
    with pytest.raises(ValueError, match="username"):
        await accounts.create_account("nic olas", "correct horse battery")


async def test_duplicate_username_rejected(storage):
    await accounts.create_account("nicolas", "correct horse battery")
    with pytest.raises(ValueError, match="exists"):
        await accounts.create_account("nicolas", "another long password")


async def test_login_rehashes_a_weaker_stored_hash(storage):
    created = await accounts.create_account("nicolas", "correct horse battery")
    record = await storage.get("console_user:nicolas")
    record["password_hash"] = accounts.hash_password("correct horse battery", log_n=14)
    await storage.set("console_user:nicolas", record)
    assert await accounts.check_credentials("nicolas", "correct horse battery") is not None
    upgraded = await storage.get("console_user:nicolas")
    assert upgraded["password_hash"].startswith("scrypt$17$8$1$")
    # a rehash is not a credential change: open sessions survive it
    assert upgraded["credentials_changed_at"] == created.credentials_changed_at


async def test_check_credentials(storage):
    await accounts.create_account("nicolas", "correct horse battery")
    assert await accounts.check_credentials("nicolas", "wrong horse battery") is None
    assert await accounts.check_credentials("nobody", "correct horse battery") is None
    ok = await accounts.check_credentials("nicolas", "correct horse battery")
    assert ok is not None and ok.username == "nicolas"
    assert (await storage.get("console_user:nicolas"))["last_login_at"] is not None


async def test_disabled_account_cannot_log_in(storage):
    created = await accounts.create_account("nicolas", "correct horse battery")
    assert await accounts.set_disabled("nicolas", True) is True
    bumped = await accounts.get_account("nicolas")
    assert bumped.credentials_changed_at > created.credentials_changed_at
    assert await accounts.check_credentials("nicolas", "correct horse battery") is None
    assert await accounts.set_disabled("nobody", True) is False


async def test_reset_password(storage):
    created = await accounts.create_account("nicolas", "correct horse battery")
    assert await accounts.reset_password("nicolas", "new horse battery staple") is True
    assert (await accounts.get_account("nicolas")).credentials_changed_at > created.credentials_changed_at
    assert await accounts.check_credentials("nicolas", "correct horse battery") is None
    assert await accounts.check_credentials("nicolas", "new horse battery staple") is not None
    assert await accounts.reset_password("nobody", "new horse battery staple") is False
```

- [ ] **Step 3: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_accounts.py -q -p no:warnings
```
Expected: `ModuleNotFoundError: No module named 'ad_seller.interfaces.console'`.

- [ ] **Step 4: Implement accounts**

Create `src/ad_seller/interfaces/console/__init__.py` with only a docstring for now:

```python
"""Operator console: a browser control room for the seller agent (see docs/guides/console.md)."""
```

Create `src/ad_seller/interfaces/console/accounts.py`:

```python
"""Console accounts: username plus scrypt password hash in the key-value store.

Accounts are created, reset, and disabled only through the CLI
(``ad-seller create-console-user``). There are no account routes.
This module is the only place the console touches storage for accounts;
it uses the generic key-value interface (get/set/delete) and nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

ACCOUNT_PREFIX = "console_user:"
MIN_PASSWORD_LENGTH = 12
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
# OWASP password storage minimum for scrypt: N=2^17, r=8, p=1 (128 MiB, ~0.3 s).
# The stored string carries its own parameters, so raising these later only
# requires a rehash on the next successful login, never a migration.
_LOG_N, _R, _P = 17, 8, 1
_DKLEN = 32
_MAXMEM = 256 * 2**20  # hashlib's default 32 MiB cap is below what N=2^17 needs


@dataclass
class Account:
    username: str
    role: str
    disabled: bool
    created_at: str
    last_login_at: Optional[str]
    credentials_changed_at: str
    """Bumped on every disable, password reset, or role change; sessions issued before it are dead."""


async def kv():
    """The console's one storage seam: the generic key-value backend."""
    from ad_seller.storage.factory import get_storage

    return await get_storage()


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
    """A record to hash against when the username does not exist.

    Keeps the failure path the same shape (one scrypt call at the current
    parameters) whether or not the account exists, so timing does not reveal
    valid usernames.
    """
    return {"password_hash": hash_password("no such account"), "disabled": True}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_account(record: dict[str, Any]) -> Account:
    return Account(
        username=record["username"],
        role=record["role"],
        disabled=bool(record["disabled"]),
        created_at=record["created_at"],
        last_login_at=record.get("last_login_at"),
        credentials_changed_at=record["credentials_changed_at"],
    )


def _validate(username: str, password: str) -> None:
    if not _USERNAME_RE.match(username or ""):
        raise ValueError(
            "username must be 1-64 characters of letters, digits, '.', '_', '@' or '-'"
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")


async def create_account(username: str, password: str) -> Account:
    _validate(username, password)
    storage = await kv()
    if await storage.get(ACCOUNT_PREFIX + username) is not None:
        raise ValueError(f"account {username!r} already exists")
    record = {
        "username": username,
        "password_hash": hash_password(password),
        "role": "operator",
        "disabled": False,
        "created_at": _now(),
        "last_login_at": None,
        "credentials_changed_at": _now(),
    }
    await storage.set(ACCOUNT_PREFIX + username, record)
    return _to_account(record)


async def get_account(username: str) -> Optional[Account]:
    record = await (await kv()).get(ACCOUNT_PREFIX + username)
    return _to_account(record) if record else None


async def check_credentials(username: str, password: str) -> Optional[Account]:
    """Return the account when username and password match and it is enabled."""
    storage = await kv()
    record = await storage.get(ACCOUNT_PREFIX + username) if username else None
    candidate = record if record is not None else _dummy_record()
    ok, needs_rehash = verify_password(password, candidate["password_hash"])
    if record is None or not ok or record["disabled"]:
        return None
    if needs_rehash:
        # Stronger parameters than the record was hashed with: upgrade in place.
        # Not a credential change, so credentials_changed_at is left alone.
        record["password_hash"] = hash_password(password)
    record["last_login_at"] = _now()
    await storage.set(ACCOUNT_PREFIX + username, record)
    return _to_account(record)


async def set_disabled(username: str, disabled: bool) -> bool:
    storage = await kv()
    record = await storage.get(ACCOUNT_PREFIX + username)
    if record is None:
        return False
    record["disabled"] = disabled
    record["credentials_changed_at"] = _now()
    await storage.set(ACCOUNT_PREFIX + username, record)
    return True


async def reset_password(username: str, password: str) -> bool:
    _validate(username, password)
    storage = await kv()
    record = await storage.get(ACCOUNT_PREFIX + username)
    if record is None:
        return False
    record["password_hash"] = hash_password(password)
    record["credentials_changed_at"] = _now()
    await storage.set(ACCOUNT_PREFIX + username, record)
    return True
```

- [ ] **Step 5: Run to verify they pass**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_accounts.py -q -p no:warnings
```
Expected: `11 passed` in about 15 seconds: every scrypt call at N=2^17 costs roughly a third of a second, which is the point.

- [ ] **Step 6: Revert check**

Change `hmac.compare_digest(candidate, expected)` to `True` and rerun: `test_hash_is_self_describing_scrypt_at_owasp_parameters` and `test_check_credentials` must fail. Restore. Then change `_LOG_N` to `14`: `test_hash_is_self_describing_scrypt_at_owasp_parameters` and `test_login_rehashes_a_weaker_stored_hash` must fail. Restore.

- [ ] **Step 7: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/console tests/unit/console
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/console tests/unit/console
git add src/ad_seller/interfaces/console/__init__.py src/ad_seller/interfaces/console/accounts.py tests/unit/console/conftest.py tests/unit/console/test_accounts.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console accounts with scrypt password hashes in the key-value store"
```

---

## Task 5: CLI command `create-console-user`

**Files:**
- Modify: `src/ad_seller/interfaces/cli/main.py` (after `list_operator_keys`)
- Test: `tests/unit/console/test_cli_console_user.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/console/test_cli_console_user.py
"""ad-seller create-console-user: the only way to manage console accounts."""

import asyncio
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ad_seller.interfaces.cli.main import app as cli
from ad_seller.interfaces.console import accounts
from ad_seller.storage.sqlite_backend import SQLiteBackend

runner = CliRunner()


@pytest.fixture
def cli_storage(tmp_path):
    backend = SQLiteBackend(f"sqlite:///{tmp_path}/cli.db")
    asyncio.run(backend.connect())
    with (
        patch("ad_seller.storage.factory.get_storage", return_value=backend),
        patch("ad_seller.storage.factory.close_storage", return_value=None),
    ):
        yield backend
    asyncio.run(backend.disconnect())


def test_create_user_prompts_for_password(cli_storage):
    result = runner.invoke(
        cli,
        ["create-console-user", "--username", "nicolas"],
        input="correct horse battery\ncorrect horse battery\n",
    )
    assert result.exit_code == 0, result.output
    assert "nicolas" in result.output
    assert "correct horse battery" not in result.output
    assert asyncio.run(accounts.get_account("nicolas")) is not None


def test_create_user_rejects_short_password(cli_storage):
    result = runner.invoke(
        cli, ["create-console-user", "--username", "nicolas"], input="short\nshort\n"
    )
    assert result.exit_code == 1
    assert "12 characters" in result.output


def test_reset_password_flag(cli_storage):
    runner.invoke(
        cli, ["create-console-user", "--username", "nicolas"],
        input="correct horse battery\ncorrect horse battery\n",
    )
    result = runner.invoke(
        cli, ["create-console-user", "--username", "nicolas", "--reset-password"],
        input="new horse battery staple\nnew horse battery staple\n",
    )
    assert result.exit_code == 0, result.output
    assert asyncio.run(accounts.check_credentials("nicolas", "new horse battery staple"))


def test_disable_flag(cli_storage):
    runner.invoke(
        cli, ["create-console-user", "--username", "nicolas"],
        input="correct horse battery\ncorrect horse battery\n",
    )
    result = runner.invoke(cli, ["create-console-user", "--username", "nicolas", "--disable"])
    assert result.exit_code == 0, result.output
    assert asyncio.run(accounts.get_account("nicolas")).disabled is True
    assert asyncio.run(accounts.check_credentials("nicolas", "correct horse battery")) is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_cli_console_user.py -q -p no:warnings
```
Expected: all four fail with exit code 2 (`No such command 'create-console-user'`).

- [ ] **Step 3: Add the command**

In `src/ad_seller/interfaces/cli/main.py`, after the `list_operator_keys` command (before the next `@app.command`), add:

```python
@app.command("create-console-user")
def create_console_user(
    username: str = typer.Option(..., "--username", "-u", help="Console login name"),
    reset_password: bool = typer.Option(
        False, "--reset-password", help="Set a new password for an existing account"
    ),
    disable: bool = typer.Option(False, "--disable", help="Disable an existing account"),
):
    """Create a console account, or reset its password, or disable it.

    Console accounts are managed only here, on the host — there is no
    account-management route. The password is prompted, never passed as an
    argument, and is stored as a scrypt hash.
    """
    from ..console import accounts
    from ...storage.factory import close_storage

    async def _run(action):
        try:
            return await action()
        finally:
            await close_storage()

    try:
        if disable:
            found = asyncio.run(_run(lambda: accounts.set_disabled(username, True)))
            if not found:
                console.print(f"[red]No console account named {username!r}[/red]")
                raise typer.Exit(1)
            console.print(f"Console account [cyan]{username}[/cyan] disabled")
            return

        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
        if reset_password:
            found = asyncio.run(_run(lambda: accounts.reset_password(username, password)))
            if not found:
                console.print(f"[red]No console account named {username!r}[/red]")
                raise typer.Exit(1)
            console.print(f"Password reset for [cyan]{username}[/cyan]")
            return

        account = asyncio.run(_run(lambda: accounts.create_account(username, password)))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    console.print(Panel("Console account created", title="Console"))
    console.print(f"Username: [cyan]{account.username}[/cyan]")
    console.print(f"Role:     {account.role}")
    console.print(
        "\nEnable the console with CONSOLE_ENABLED=true and CONSOLE_OPERATOR_API_KEY\n"
        "(see docs/guides/console.md), then sign in at /console/login."
    )
```

- [ ] **Step 4: Run to verify they pass**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_cli_console_user.py -q -p no:warnings
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/cli/main.py tests/unit/console/test_cli_console_user.py
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/cli/main.py tests/unit/console/test_cli_console_user.py
git add src/ad_seller/interfaces/cli/main.py tests/unit/console/test_cli_console_user.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: add ad-seller create-console-user"
```

---

## Task 6: Config, sessions, rate limit, and `current_operator`

**Files:**
- Create: `src/ad_seller/interfaces/console/config.py`
- Create: `src/ad_seller/interfaces/console/auth.py`
- Test: `tests/unit/console/test_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/console/test_auth.py
"""Sessions are opaque tokens in the store; current_operator is the only cookie reader."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport

from ad_seller.interfaces.console import auth
from ad_seller.interfaces.console.config import ConsoleConfig


async def test_session_round_trip(storage):
    token, expires_at = await auth.create_session("nicolas", "operator", ttl_hours=1)
    assert len(token) >= 40
    assert expires_at > datetime.now(timezone.utc) + timedelta(minutes=59)
    record = await storage.get(auth.SESSION_PREFIX + token)
    assert record["username"] == "nicolas"
    assert set(record) == {"username", "role", "created_at", "expires_at"}
    loaded = await auth.load_session(token)
    assert loaded["username"] == "nicolas"
    await auth.delete_session(token)
    assert await auth.load_session(token) is None
    assert await auth.load_session("nonsense") is None


async def test_failure_counters(storage):
    assert await auth.failures("nicolas", "10.0.0.1") == 0
    for _ in range(3):
        await auth.record_failure("nicolas", "10.0.0.1")
    assert await auth.failures("nicolas", "10.0.0.1") == 3
    assert await auth.failures("nicolas", "10.0.0.2") == 3  # per username
    assert await auth.failures("other", "10.0.0.1") == 3  # per address
    await auth.clear_failures("nicolas", "10.0.0.1")
    assert await auth.failures("nicolas", "10.0.0.1") == 0


async def test_concurrent_failures_are_all_counted(storage):
    """No read-modify-write: ten failures recorded at once are ten, not fewer."""
    import asyncio

    await asyncio.gather(*(auth.record_failure("nicolas", "10.0.0.1") for _ in range(10)))
    assert await auth.failures("nicolas", "10.0.0.1") == 10


async def test_console_keys_use_the_hybrid_backends_redis_prefixes(storage):
    from ad_seller.storage.hybrid_backend import _is_redis_key

    token, _ = await auth.create_session("nicolas", "operator", ttl_hours=1)
    await auth.record_failure("nicolas", "10.0.0.1")
    assert _is_redis_key(auth.SESSION_PREFIX + token)
    for key in await storage.keys("rate_limit:console:*"):
        assert _is_redis_key(key)


def _app_with_operator_route(config: ConsoleConfig) -> FastAPI:
    """A sub-application mounted at /console, as the real console is, so root_path is set."""
    sub = FastAPI()
    sub.state.console = auth.ConsoleState(config=config, api=None)

    @sub.get("/whoami")
    async def whoami(operator: auth.Operator = Depends(auth.current_operator)):
        return {"username": operator.username, "role": operator.role}

    app = FastAPI()
    app.mount("/console", sub)
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_no_cookie_redirects_page_requests(storage):
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    response = await _client(app).get("/console/whoami")
    assert response.status_code == 303
    assert response.headers["location"] == "/console/login?next=%2Fconsole%2Fwhoami"


async def test_no_cookie_tells_htmx_to_redirect(storage):
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    response = await _client(app).get("/console/whoami", headers={"HX-Request": "true"})
    assert response.status_code == 401
    assert response.headers["hx-redirect"] == "/console/login?next=%2Fconsole%2Fwhoami"


async def test_valid_cookie_resolves_operator(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas", "correct horse battery")
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    token, _ = await auth.create_session("nicolas", "operator", ttl_hours=1)
    response = await _client(app).get(
        "/console/whoami", cookies={auth.SESSION_COOKIE: token}
    )
    assert response.status_code == 200
    assert response.json() == {"username": "nicolas", "role": "operator"}


async def test_disabling_the_account_kills_an_issued_session(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas", "correct horse battery")
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    token, _ = await auth.create_session("nicolas", "operator", ttl_hours=1)
    client = _client(app)
    assert (await client.get("/console/whoami", cookies={auth.SESSION_COOKIE: token})).status_code == 200
    await accounts.set_disabled("nicolas", True)
    dead = await client.get("/console/whoami", cookies={auth.SESSION_COOKIE: token})
    assert dead.status_code == 303
    assert await auth.load_session(token) is None


async def test_password_reset_kills_an_issued_session(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas", "correct horse battery")
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    token, _ = await auth.create_session("nicolas", "operator", ttl_hours=1)
    await accounts.reset_password("nicolas", "new horse battery staple")
    dead = await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})
    assert dead.status_code == 303


async def test_deleted_account_kills_an_issued_session(storage):
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    token, _ = await auth.create_session("ghost", "operator", ttl_hours=1)
    dead = await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})
    assert dead.status_code == 303


def _sso_app(cidrs):
    config = ConsoleConfig(
        operator_api_key="k", trusted_identity_header="X-Forwarded-Email", trusted_proxy_cidrs=cidrs
    )
    return _app_with_operator_route(config)


async def test_sso_accepts_header_from_trusted_proxy(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas@example.com", "correct horse battery")
    app = _sso_app(["127.0.0.1/32"])  # httpx's ASGI transport reports client 127.0.0.1
    ok = await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "nicolas@example.com"})
    assert ok.status_code == 200
    assert ok.json()["username"] == "nicolas@example.com"


async def test_sso_rejects_header_from_untrusted_address(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas@example.com", "correct horse battery")
    app = _sso_app(["10.0.0.0/8"])
    spoof = await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "nicolas@example.com"})
    assert spoof.status_code == 403


async def test_sso_requires_header_and_ignores_cookies(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas@example.com", "correct horse battery")
    app = _sso_app(["127.0.0.1/32"])
    token, _ = await auth.create_session("nicolas@example.com", "operator", ttl_hours=1)
    # a valid password session is not a substitute for the header
    stale = await _client(app).get("/console/whoami", cookies={auth.SESSION_COOKIE: token})
    assert stale.status_code == 403
    missing = await _client(app).get("/console/whoami")
    assert missing.status_code == 403


async def test_sso_rejects_unknown_and_disabled_identities(storage):
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("gone@example.com", "correct horse battery")
    await accounts.set_disabled("gone@example.com", True)
    app = _sso_app(["127.0.0.1/32"])
    unknown = await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "stranger@example.com"})
    assert unknown.status_code == 403
    disabled = await _client(app).get("/console/whoami", headers={"X-Forwarded-Email": "gone@example.com"})
    assert disabled.status_code == 403


def test_safe_next_only_allows_paths_under_the_mount():
    assert auth.safe_next("/console/deals", "/console") == "/console/deals"
    assert auth.safe_next("/console//evil", "/console") == "/console/"
    assert auth.safe_next("https://evil.example/", "/console") == "/console/"
    assert auth.safe_next(None, "/console") == "/console/"
    assert auth.safe_next("/api/v1/deals", "/console") == "/console/"
    assert auth.safe_next("/agent/console/deals", "/agent/console") == "/agent/console/deals"


async def test_paths_follow_the_mount_prefix(storage):
    """Behind a proxy prefix the redirect and cookie path move with the mount."""
    from ad_seller.interfaces.console import accounts

    await accounts.create_account("nicolas", "correct horse battery")
    app = _app_with_operator_route(ConsoleConfig(operator_api_key="k"))
    outer = FastAPI()
    outer.mount("/agent", app)
    response = await _client(outer).get("/agent/console/whoami")
    assert response.status_code == 303
    assert response.headers["location"] == "/agent/console/login?next=%2Fagent%2Fconsole%2Fwhoami"
```

- [ ] **Step 2: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_auth.py -q -p no:warnings
```
Expected: `ModuleNotFoundError: No module named 'ad_seller.interfaces.console.auth'`.

- [ ] **Step 3: Implement config**

Create `src/ad_seller/interfaces/console/config.py`:

```python
"""Console configuration, built once from Settings or supplied directly by tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConsoleConfig:
    operator_api_key: Optional[str]
    session_ttl_hours: int = 12
    trusted_identity_header: str = ""
    trusted_proxy_cidrs: list[str] = field(default_factory=list)
    failure_delay_seconds: float = 0.3
    api_timeout_seconds: float = 2.0
    api_base_url: str = "http://console.local"  # only meaningful with a network transport

    @property
    def sso(self) -> bool:
        return bool(self.trusted_identity_header)

    @classmethod
    def from_settings(cls) -> "ConsoleConfig":
        from ad_seller.config.settings import get_settings

        settings = get_settings()
        cidrs = [c.strip() for c in settings.console_trusted_proxy_cidrs.split(",") if c.strip()]
        return cls(
            operator_api_key=settings.console_operator_api_key,
            session_ttl_hours=settings.console_session_ttl_hours,
            trusted_identity_header=settings.console_trusted_identity_header,
            trusted_proxy_cidrs=cidrs,
        )
```

- [ ] **Step 4: Implement auth**

Create `src/ad_seller/interfaces/console/auth.py`:

```python
"""Sessions, CSRF cookie, login rate limit, and the ``current_operator`` dependency.

``current_operator`` is the only code that reads the session cookie or the
trusted identity header. Screens depend on it and never learn how the person
logged in. A record never holds a key or a password.
"""

from __future__ import annotations

import ipaddress
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException, Request, Response

from .accounts import get_account, kv
from .config import ConsoleConfig

SESSION_COOKIE = "console_session"
CSRF_COOKIE = "console_csrf"
# The hybrid backend routes "session:" and "rate_limit:" keys to Redis (ephemeral,
# TTL-native) and everything else to Postgres. Using those prefixes puts console
# sessions and login failures where they belong without touching the router.
SESSION_PREFIX = "session:console:"
RATE_PREFIX = "rate_limit:console:"
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 600


def root(request: Request) -> str:
    """The mount prefix (``/console`` today, plus any proxy prefix); never hardcode it."""
    return request.scope.get("root_path", "").rstrip("/")


def console_root(request: Request) -> str:
    return root(request) + "/"


def login_path(request: Request) -> str:
    return root(request) + "/login"


@dataclass
class ConsoleState:
    """What the console sub-application carries on ``app.state.console``."""

    config: ConsoleConfig
    api: Any  # ConsoleApi; typed loosely so auth.py does not import client.py


@dataclass
class Operator:
    username: str
    role: str
    session_expires_at: Optional[datetime] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_session(username: str, role: str, ttl_hours: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    created = _now()
    expires_at = created + timedelta(hours=ttl_hours)
    await (await kv()).set(
        SESSION_PREFIX + token,
        {
            "username": username,
            "role": role,
            "created_at": created.isoformat(),
            "expires_at": expires_at.isoformat(),
        },
        ttl=ttl_hours * 3600,
    )
    return token, expires_at


async def load_session(token: str) -> Optional[dict[str, Any]]:
    record = await (await kv()).get(SESSION_PREFIX + token)
    if not record:
        return None
    if datetime.fromisoformat(record["expires_at"]) <= _now():
        return None
    return record


async def delete_session(token: str) -> None:
    await (await kv()).delete(SESSION_PREFIX + token)


def _rate_scopes(username: str, address: str) -> tuple[str, str]:
    return f"{RATE_PREFIX}user:{username}:", f"{RATE_PREFIX}addr:{address}:"


async def failures(username: str, address: str) -> int:
    """Failures in the window: one TTL key per failure, counted, never read-modify-written.

    Every backend's ``set`` with a TTL and ``keys`` with a prefix pattern are atomic
    on their own, so concurrent failures cannot lose each other and expiry is the
    store's, not ours.
    """
    storage = await kv()
    counts = [len(await storage.keys(scope + "*")) for scope in _rate_scopes(username, address)]
    return max(counts)


async def record_failure(username: str, address: str) -> None:
    storage = await kv()
    stamp = secrets.token_hex(8)
    for scope in _rate_scopes(username, address):
        await storage.set(scope + stamp, 1, ttl=RATE_LIMIT_WINDOW_SECONDS)


async def clear_failures(username: str, address: str) -> None:
    storage = await kv()
    for scope in _rate_scopes(username, address):
        for key in await storage.keys(scope + "*"):
            await storage.delete(key)


def safe_next(value: Optional[str], root_path: str) -> str:
    """Only relative paths under the console mount may be redirect targets."""
    home = root_path + "/"
    if value and value.startswith(home) and "//" not in value:
        return value
    return home


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request", "").lower() == "true"


def is_secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded == "https"


def login_url(request: Request) -> str:
    target = safe_next(request.url.path, root(request))
    return f"{login_path(request)}?next={quote(target, safe='')}"


def set_session_cookie(response: Response, request: Request, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_secure(request),
        path=root(request) or "/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path=root(request) or "/")


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def from_trusted_proxy(request: Request, cidrs: list[str]) -> bool:
    address = client_address(request)
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


async def _sso_operator(request: Request, config: ConsoleConfig) -> Operator:
    """SSO mode: the header is required on every request; cookies are never consulted."""
    if not from_trusted_proxy(request, config.trusted_proxy_cidrs):
        raise HTTPException(status_code=403, detail="Console requests must come through the identity proxy")
    identity = request.headers.get(config.trusted_identity_header)
    if not identity:
        raise HTTPException(status_code=403, detail="Identity header missing")
    account = await get_account(identity)
    if account is None or account.disabled:
        raise HTTPException(status_code=403, detail="No console account for this identity")
    return Operator(username=account.username, role=account.role)


async def current_operator(request: Request) -> Operator:
    state: ConsoleState = request.app.state.console
    if state.config.sso:
        return await _sso_operator(request, state.config)

    token = request.cookies.get(SESSION_COOKIE)
    session = await load_session(token) if token else None
    account = await get_account(session["username"]) if session else None
    if session is not None and (
        account is None
        or account.disabled
        or datetime.fromisoformat(session["created_at"])
        < datetime.fromisoformat(account.credentials_changed_at)
    ):
        # The account changed under the session (disabled, password reset, role change):
        # the session is dead, whatever its TTL says.
        await delete_session(token)
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

Note on the 303: FastAPI's default `HTTPException` handler returns the status and headers as given, so a browser follows `Location` while the JSON body is ignored. No custom exception handler is needed, which matters because the sub-application may be mounted after the root app has served requests.

- [ ] **Step 5: Run to verify they pass**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_auth.py -q -p no:warnings
```
Expected: `17 passed`.

- [ ] **Step 6: Revert check**

In `safe_next`, replace the body with `return value or home` and rerun: `test_safe_next_only_allows_paths_under_the_mount` must fail. Restore. Then in `current_operator`, drop the `is_htmx` branch: `test_no_cookie_tells_htmx_to_redirect` must fail. Restore. Then in `_sso_operator`, delete the `from_trusted_proxy` check: `test_sso_rejects_header_from_untrusted_address` must fail. Restore. Then in `current_operator`, delete the account reread block: the three `*_kills_an_issued_session` tests must fail. Restore. Then change `SESSION_PREFIX` back to `"console_session:"`: `test_console_keys_use_the_hybrid_backends_redis_prefixes` must fail. Restore.

- [ ] **Step 7: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/console tests/unit/console
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/console tests/unit/console
git add src/ad_seller/interfaces/console/config.py src/ad_seller/interfaces/console/auth.py tests/unit/console/test_auth.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console sessions, login rate limit, and the current_operator dependency"
```

---

## Task 7: The in-process API client

**Files:**
- Create: `src/ad_seller/interfaces/console/client.py`
- Modify: `tests/unit/console/conftest.py` (add `api_app` fixture)
- Test: `tests/unit/console/test_client.py`

- [ ] **Step 1: Add the API app fixture**

Append to `tests/unit/console/conftest.py`:

```python
from fastapi import FastAPI  # noqa: E402

from ad_seller.interfaces.api.routers import ALL_ROUTERS  # noqa: E402


@pytest.fixture
def api_app() -> FastAPI:
    """A fresh app carrying the real REST routers, so console tests never mutate the shared app."""
    app = FastAPI()
    for router in ALL_ROUTERS:
        app.include_router(router)
    return app
```

Move both new imports up to the import block at the top of the file (they are shown with `noqa` only to make the append unambiguous; in the file they belong with the other imports, without `noqa`).

- [ ] **Step 2: Write the failing tests**

```python
# tests/unit/console/test_client.py
"""ConsoleApi calls the real REST routes in-process with the console key."""

import asyncio

import httpx
import pytest

from ad_seller.auth.api_key_service import ApiKeyService
from ad_seller.interfaces.api import deps
from ad_seller.interfaces.console.client import ApiRejected, ApiUnavailable, ConsoleApi


def _api(app, key, **kwargs) -> ConsoleApi:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return ConsoleApi(transport, "http://console.local", key, **kwargs)


async def test_me_returns_console_key_info(api_app, console_key):
    key, key_id = console_key
    api = _api(api_app, key)
    me = await api.me(user="nicolas")
    assert me.key_id == key_id
    assert me.role == "operator"
    assert me.is_active is True


async def test_every_call_carries_key_and_user_header(api_app, console_key):
    key, _ = console_key
    seen = {}

    @api_app.middleware("http")
    async def capture(request, call_next):
        seen["authorization"] = request.headers.get("authorization")
        seen["user"] = request.headers.get("x-console-user")
        return await call_next(request)

    api = _api(api_app, key)
    await api.health(user="nicolas")
    assert seen["authorization"] == f"Bearer {key}"
    assert seen["user"] == "nicolas"


async def test_health_merges_root_and_health(api_app, console_key):
    key, _ = console_key
    health = await _api(api_app, key).health(user="nicolas")
    assert health.status == "healthy"
    assert health.name == "Ad Seller System API"
    assert health.version


async def test_inventory_sync_status_shape(api_app, console_key):
    key, _ = console_key
    status = await _api(api_app, key).inventory_sync_status(user="nicolas")
    assert status.enabled is False
    assert status.sync_count == 0


async def test_last_event_is_none_when_bus_is_empty(api_app, console_key):
    key, _ = console_key
    assert await _api(api_app, key).last_event(user="nicolas") is None


async def test_revoked_key_raises_rejected(api_app, storage, console_key):
    key, key_id = console_key
    await ApiKeyService(storage).revoke_key(key_id)
    with pytest.raises(ApiRejected) as exc:
        await _api(api_app, key).me(user="nicolas")
    assert exc.value.status == 401


async def test_server_error_raises_unavailable(api_app, console_key):
    key, _ = console_key

    def boom():
        raise RuntimeError("storage down")

    api_app.dependency_overrides[deps._require_api_key_record] = boom
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(api_app, key).me(user="nicolas")
    finally:
        api_app.dependency_overrides.clear()
    assert exc.value.status == 500
    assert key not in str(exc.value)


@pytest.mark.parametrize("status", [404, 409, 429, 500, 502, 503])
async def test_error_statuses_raise_unavailable_with_the_status(api_app, console_key, status):
    from fastapi import HTTPException

    key, _ = console_key

    def fail():
        raise HTTPException(status_code=status)

    api_app.dependency_overrides[deps._require_api_key_record] = fail
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(api_app, key).me(user="nicolas")
    finally:
        api_app.dependency_overrides.clear()
    assert exc.value.status == status


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_statuses_raise_rejected(api_app, console_key, status):
    from fastapi import HTTPException

    key, _ = console_key

    def fail():
        raise HTTPException(status_code=status)

    api_app.dependency_overrides[deps._require_api_key_record] = fail
    try:
        with pytest.raises(ApiRejected) as exc:
            await _api(api_app, key).me(user="nicolas")
    finally:
        api_app.dependency_overrides.clear()
    assert exc.value.status == status


@pytest.mark.parametrize("body", [[], None, "text", {"unexpected": 1}, {"events": None}, {"events": [{"no": "fields"}]}])
async def test_every_method_rejects_malformed_bodies(api_app, console_key, body, monkeypatch):
    key, _ = console_key
    api = _api(api_app, key)

    async def fake_get(path, user, params=None):
        return body

    monkeypatch.setattr(api, "_get", fake_get)
    for method in (api.me, api.health, api.inventory_sync_status, api.last_event):
        with pytest.raises(ApiUnavailable) as exc:
            await method(user="nicolas")
        assert "unexpected response shape" in str(exc.value)


async def test_timeout_raises_unavailable(api_app, console_key):
    key, _ = console_key

    async def slow():
        await asyncio.sleep(0.5)

    api_app.dependency_overrides[deps._require_api_key_record] = slow
    try:
        with pytest.raises(ApiUnavailable) as exc:
            await _api(api_app, key, timeout=0.05).me(user="nicolas")
    finally:
        api_app.dependency_overrides.clear()
    assert exc.value.status == 0
    assert "timeout" in str(exc.value)
```

- [ ] **Step 3: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_client.py -q -p no:warnings
```
Expected: `ModuleNotFoundError: No module named 'ad_seller.interfaces.console.client'`.

- [ ] **Step 4: Implement the client**

Create `src/ad_seller/interfaces/console/client.py`:

```python
"""In-process HTTP client from the console to the REST API.

Every call goes through the real REST routers via httpx's ASGI transport, so
the API's own auth and handlers run. Nothing outside this module imports httpx.
The ``X-Console-User`` header is display context for the API's logs: the API
authenticates the console key only and does not verify the header, so it must
never be treated as attribution (see the spec's growth path).
The ASGI transport runs the app inline, so the per-call bound is enforced with
``asyncio.wait_for`` rather than a socket timeout.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


class KeyInfo(BaseModel):
    """The subset of ApiKeyInfo the console shows. Unknown fields are ignored."""

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
    """The API refused the console key: 401 (invalid/revoked) or 403 (not an operator)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"API rejected the console key with status {status}")
        self.status = status


class ApiUnavailable(Exception):
    """The API could not answer: 5xx, timeout, or a body that is not JSON."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"API unavailable ({status}): {detail}")
        self.status = status
        self.detail = detail


class ConsoleApi:
    """Talks to the REST API over an injected httpx transport.

    Today the transport is ``httpx.ASGITransport(app=root_app)`` so calls stay
    in-process; a network deployment passes ``httpx.AsyncHTTPTransport()`` and
    the API's real base URL instead. Nothing else changes.
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        base_url: str,
        operator_api_key: str,
        timeout: float = 2.0,
    ) -> None:
        self._client = httpx.AsyncClient(transport=transport, base_url=base_url, follow_redirects=False)
        self._key = operator_api_key
        self._timeout = timeout

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, user: str, params: Optional[dict] = None) -> Any:
        headers = {"Authorization": f"Bearer {self._key}", "X-Console-User": user}
        try:
            response = await asyncio.wait_for(
                self._client.get(path, headers=headers, params=params), self._timeout
            )
        except asyncio.TimeoutError as exc:
            raise ApiUnavailable(0, f"timeout after {self._timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ApiUnavailable(0, type(exc).__name__) from exc
        if response.status_code in (401, 403):
            raise ApiRejected(response.status_code)
        if response.status_code >= 400:
            raise ApiUnavailable(response.status_code, "error status")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiUnavailable(response.status_code, "non-JSON body") from exc

    @staticmethod
    def _parse(model: type[M], body: Any) -> M:
        """A body the console does not understand degrades one card, never the page."""
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
        if events is None or not isinstance(events, list):
            raise ApiUnavailable(200, "unexpected response shape for events")
        if not events:
            return None
        parsed = [self._parse(EventSummary, e) for e in events]
        return max(parsed, key=lambda e: e.timestamp)
```

The in-process transport is built by `mount_console` as `httpx.ASGITransport(app=root_app, raise_app_exceptions=False)`: the flag turns an unhandled exception inside the API into a 500 response, which `_get` maps to `ApiUnavailable(500, ...)`; without it the exception would propagate into the console route instead.

- [ ] **Step 5: Run to verify they pass**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_client.py -q -p no:warnings
```
Expected: `22 passed`.

- [ ] **Step 6: Revert check**

Remove the `X-Console-User` header line and rerun: `test_every_call_carries_key_and_user_header` must fail. Restore. Then make `_parse` return `body` unchanged: `test_every_method_rejects_malformed_bodies` must fail. Restore.

- [ ] **Step 7: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/console tests/unit/console
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/console tests/unit/console
git add src/ad_seller/interfaces/console/client.py tests/unit/console/conftest.py tests/unit/console/test_client.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console API client calling the REST routes in-process"
```

---

## Task 8: Templates and static assets

**Files:**
- Create: `src/ad_seller/interfaces/console/templates/base.html`, `login.html`, `home.html`, `error.html`, `partials/health_cards.html`
- Create: `src/ad_seller/interfaces/console/static/console.css`, `static/htmx.min.js`
- Test: `tests/unit/console/test_static_assets.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/console/test_static_assets.py
"""The console ships its own assets: no CDN, no build step."""

from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[3] / "src" / "ad_seller" / "interfaces" / "console"


def test_htmx_is_vendored_and_pinned():
    htmx = CONSOLE / "static" / "htmx.min.js"
    assert htmx.exists()
    head = htmx.read_text(errors="ignore")[:400]
    assert "htmx" in head
    assert "2.0.4" in head


def test_templates_exist():
    for name in ("base.html", "login.html", "home.html", "error.html", "partials/health_cards.html"):
        assert (CONSOLE / "templates" / name).exists(), name


def test_templates_reference_no_external_hosts():
    for path in (CONSOLE / "templates").rglob("*.html"):
        text = path.read_text()
        assert "https://" not in text and "http://" not in text, path


def test_templates_never_hardcode_the_mount():
    for path in (CONSOLE / "templates").rglob("*.html"):
        assert "/console/" not in path.read_text(), path
```

- [ ] **Step 2: Run to verify it fails**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_static_assets.py -q -p no:warnings
```
Expected: 3 failures, files missing.

- [ ] **Step 3: Vendor HTMX**

```bash
mkdir -p src/ad_seller/interfaces/console/static src/ad_seller/interfaces/console/templates/partials
curl -fsSL https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js -o /tmp/htmx.min.js
shasum -a 256 /tmp/htmx.min.js
{ printf '/* htmx 2.0.4 — vendored from https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js — sha256 %s — BSD-2-Clause */\n' "$(shasum -a 256 /tmp/htmx.min.js | cut -d' ' -f1)"; cat /tmp/htmx.min.js; } > src/ad_seller/interfaces/console/static/htmx.min.js
head -c 300 src/ad_seller/interfaces/console/static/htmx.min.js
```
Expected: the header line with the version and the hash, followed by minified code.

- [ ] **Step 4: Write the stylesheet**

Create `src/ad_seller/interfaces/console/static/console.css`:

```css
/* IAB Tech Lab palette (sampled from the logo and site) plus semantic status colors. */
:root {
  --brand: #ee3126;
  --ink: #221f1f;
  --text: #3f3f3f;
  --text-2: #5d5d5d;
  --label: #7d7d7d;
  --line: #e4e4e4;
  --ground: #f7f6f6;
  --ok: #1f7a3f;
  --warn: #b7791f;
  --error: #b3261e;
  --error-bg: #fdecea;
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
.who { color: var(--text-2); }
.who b { color: var(--ink); }
.who form { display: inline; }
.who button { background: none; border: 0; color: var(--brand); cursor: pointer; font: inherit; text-decoration: underline; padding: 0; }

.body { display: flex; min-height: calc(100vh - 48px); }
.nav { width: 208px; border-right: 1px solid var(--line); background: var(--ground); padding: 16px 12px; }
.nav .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--label); padding: 4px 10px 10px; }
.nav a, .nav .off { display: flex; justify-content: space-between; align-items: center; padding: 9px 10px; border-radius: 4px; color: var(--text); text-decoration: none; }
.nav a.active { background: var(--brand); color: #fff; font-weight: 600; }
.nav .off { color: #bababa; }
.nav .off small { font-size: 10px; border: 1px solid #d5d5d5; border-radius: 8px; padding: 0 6px; }
.main { flex: 1; padding: 24px 28px; max-width: 1100px; }
h1 { margin: 0 0 16px; font-size: 20px; color: var(--ink); }

.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.card { border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
.card .t { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--label); margin-bottom: 6px; }
.card .v { font-size: 16px; font-weight: 600; color: var(--ink); }
.card .s { color: var(--text-2); margin-top: 4px; }
.ok { color: var(--ok); }
.warn { color: var(--warn); }
.error { color: var(--error); }
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

- [ ] **Step 5: Write the templates**

`src/ad_seller/interfaces/console/templates/base.html`:

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
    · <form method="post" action="{{ root }}/logout">
        <input type="hidden" name="csrf" value="{{ csrf }}">
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

`src/ad_seller/interfaces/console/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Sign in · Seller Agent Console{% endblock %}
{% block body %}
<div class="login">
  <form class="login-card" method="post" action="{{ root }}/login" id="login-form">
    <a class="wordmark" href="{{ root }}/login">iab<i>.</i><span>TECH LAB</span></a>
    <h1>Seller Agent Console</h1>
    <div class="help" style="margin-top:0">Sign in</div>
    <input type="hidden" name="csrf" value="{{ csrf }}">
    <input type="hidden" name="next" value="{{ next }}">
    <label for="username">Username</label>
    <input id="username" name="username" autocomplete="username" required autofocus>
    <label for="password">Password</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    {% if error %}<div class="alert" id="login-error">{{ error }}</div>{% endif %}
    <button class="btn" type="submit">Sign in</button>
    <div class="help">Accounts are created on the host with <code>ad-seller create-console-user</code>. When single sign-on is configured, this page is skipped.</div>
  </form>
</div>
{% endblock %}
```

`src/ad_seller/interfaces/console/templates/home.html`:

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

`src/ad_seller/interfaces/console/templates/partials/health_cards.html`:

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

`src/ad_seller/interfaces/console/templates/error.html`:

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

- [ ] **Step 6: Run to verify the asset tests pass**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_static_assets.py -q -p no:warnings
```
Expected: `4 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/ad_seller/interfaces/console/templates src/ad_seller/interfaces/console/static tests/unit/console/test_static_assets.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console templates, stylesheet, and vendored htmx"
```

---

## Task 9: Routes, mounting, login and logout

**Files:**
- Create: `src/ad_seller/interfaces/console/routes.py`
- Modify: `src/ad_seller/interfaces/console/__init__.py`
- Modify: `tests/unit/console/conftest.py` (add `console_app` and `client` fixtures, an HTML helper)
- Test: `tests/unit/console/test_login_routes.py`

- [ ] **Step 1: Add fixtures and the HTML helper**

Append to `tests/unit/console/conftest.py` (imports go to the top of the file):

```python
import httpx
from html.parser import HTMLParser
from httpx import ASGITransport

from ad_seller.interfaces.console import mount_console
from ad_seller.interfaces.console.config import ConsoleConfig


class _Index(HTMLParser):
    """Collects elements by id: id -> (attrs, text)."""

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
def console_config(console_key) -> ConsoleConfig:
    key, _ = console_key
    return ConsoleConfig(operator_api_key=key, failure_delay_seconds=0)


@pytest.fixture
def console_app(api_app, console_config):
    mount_console(api_app, console_config)
    return api_app


@pytest.fixture
def client(console_app):
    return httpx.AsyncClient(
        transport=ASGITransport(app=console_app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.fixture
async def account(storage):
    from ad_seller.interfaces.console import accounts

    return await accounts.create_account("nicolas", "correct horse battery")


async def login(client: httpx.AsyncClient, username="nicolas", password="correct horse battery"):
    page = await client.get("/console/login")
    csrf = page.cookies["console_csrf"]
    return await client.post(
        "/console/login",
        data={"username": username, "password": password, "csrf": csrf, "next": "/console/"},
    )
```

`html_index` and `login` are module-level helpers imported by the tests (`from tests.unit.console.conftest import html_index, login`).

- [ ] **Step 2: Write the failing tests**

```python
# tests/unit/console/test_login_routes.py
"""Login, logout, cookies, CSRF, rate limit, and the shell."""

import httpx
import pytest

from ad_seller.interfaces.console import auth
from tests.unit.console.conftest import html_index, login


async def test_console_is_mounted_and_static_served(client):
    css = await client.get("/console/static/console.css")
    assert css.status_code == 200
    assert "--brand: #ee3126" in css.text


async def test_login_page_sets_csrf_cookie(client):
    page = await client.get("/console/login")
    assert page.status_code == 200
    assert "console_csrf" in page.cookies
    form = html_index(page.text)
    assert form["login-form"]["attrs"]["action"] == "/console/login"
    assert "login-error" not in form


async def test_login_success_sets_session_cookie_and_redirects(client, account):
    response = await login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/console/"
    cookie = response.headers["set-cookie"]
    assert "console_session=" in cookie
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    assert "Path=/console" in cookie
    assert "Secure" not in cookie  # http in tests


async def test_session_cookie_is_secure_behind_https_proxy(client, account):
    page = await client.get("/console/login")
    csrf = page.cookies["console_csrf"]
    response = await client.post(
        "/console/login",
        data={"username": "nicolas", "password": "correct horse battery", "csrf": csrf, "next": "/console/"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert "Secure" in response.headers["set-cookie"]


async def test_wrong_password_is_generic_401(client, account):
    response = await login(client, password="wrong horse battery")
    assert response.status_code == 401
    assert html_index(response.text)["login-error"]["text"] == "Wrong username or password."
    assert "console_session" not in response.cookies


async def test_unknown_user_gets_the_same_message(client, account):
    response = await login(client, username="nobody")
    assert response.status_code == 401
    assert html_index(response.text)["login-error"]["text"] == "Wrong username or password."


async def test_missing_csrf_is_400(client, account):
    await client.get("/console/login")
    response = await client.post(
        "/console/login",
        data={"username": "nicolas", "password": "correct horse battery", "csrf": "bogus", "next": "/console/"},
    )
    assert response.status_code == 400


async def test_sixth_failure_is_rate_limited(client, account, storage):
    for _ in range(5):
        assert (await login(client, password="wrong horse battery")).status_code == 401
    response = await login(client, password="wrong horse battery")
    assert response.status_code == 429
    assert "Too many attempts" in html_index(response.text)["login-error"]["text"]
    # a correct password is also refused while limited
    assert (await login(client)).status_code == 429
    await auth.clear_failures("nicolas", "127.0.0.1")
    assert (await login(client)).status_code == 303


async def test_logout_deletes_session_and_clears_cookie(client, account, storage):
    await login(client)
    token = client.cookies["console_session"]
    assert await storage.get(auth.SESSION_PREFIX + token) is not None
    response = await client.post("/console/logout", data={"csrf": client.cookies["console_csrf"]})
    assert response.status_code == 303
    assert response.headers["location"] == "/console/login"
    assert await storage.get(auth.SESSION_PREFIX + token) is None
    assert 'console_session=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]


async def test_login_rotates_token(client, account):
    await login(client)
    first = client.cookies["console_session"]
    await login(client)
    assert client.cookies["console_session"] != first


async def test_login_never_logs_secrets(client, account, caplog):
    caplog.set_level("DEBUG")
    await login(client, password="wrong horse battery")
    await login(client)
    text = caplog.text
    assert "wrong horse battery" not in text
    assert "correct horse battery" not in text
    assert client.cookies["console_session"] not in text


async def test_password_endpoints_are_404_in_sso_mode(api_app, console_key, account):
    from ad_seller.interfaces.console import mount_console
    from ad_seller.interfaces.console.config import ConsoleConfig

    key, _ = console_key
    mount_console(
        api_app,
        ConsoleConfig(
            operator_api_key=key, trusted_identity_header="X-Forwarded-Email", trusted_proxy_cidrs=["127.0.0.1/32"]
        ),
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=api_app), base_url="http://test")
    assert (await client.get("/console/login")).status_code == 404
    post = await client.post(
        "/console/login", data={"username": "nicolas", "password": "correct horse battery", "csrf": "x"}
    )
    assert post.status_code == 404
    assert (await client.post("/console/logout", data={"csrf": "x"})).status_code == 404
```

- [ ] **Step 3: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_login_routes.py -q -p no:warnings
```
Expected: `ImportError: cannot import name 'mount_console'`.

- [ ] **Step 4: Implement routes**

Create `src/ad_seller/interfaces/console/routes.py`:

```python
"""Console pages: login, logout, the landing page, and the health partial."""

from __future__ import annotations

import asyncio
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import auth
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


def _render(request: Request, name: str, status_code: int = 200, **context: Any) -> HTMLResponse:
    context.setdefault("root", auth.root(request))
    context.setdefault("csrf", request.cookies.get(auth.CSRF_COOKIE, ""))
    context.setdefault("sso", _state(request).config.sso)
    return templates.TemplateResponse(request, name, context, status_code=status_code)


async def unexpected_error(request: Request, exc: Exception) -> HTMLResponse:
    """Registered on the sub-application for ``Exception``: every console route is covered.

    HTTPException keeps FastAPI's own handler (redirects, 401/403/404 stay what they are).
    Logs once with a request id; the page shows the id and nothing else.
    """
    request_id = uuid.uuid4().hex[:8]
    logger.exception("console request %s failed (request id %s)", request.url.path, request_id)
    return _render(request, "error.html", status_code=500, request_id=request_id, operator=None, nav=[])


def _login_page(request: Request, *, error: str | None, status_code: int, next_path: str) -> HTMLResponse:
    token = request.cookies.get(auth.CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = _render(request, "login.html", status_code=status_code, csrf=token, error=error, next=next_path)
    response.set_cookie(
        auth.CSRF_COOKIE, token, httponly=True, samesite="lax", secure=auth.is_secure(request), path=auth.root(request) or "/"
    )
    return response


def _csrf_ok(request: Request, submitted: str) -> bool:
    cookie = request.cookies.get(auth.CSRF_COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie, submitted)


def _password_login_enabled(request: Request) -> None:
    """In SSO mode the password endpoints do not exist: 404, never a redirect."""
    if _state(request).config.sso:
        raise HTTPException(status_code=404)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str | None = None) -> Any:
    _password_login_enabled(request)
    return _login_page(request, error=None, status_code=200, next_path=auth.safe_next(next, auth.root(request)))


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    csrf: str = Form(""),
    next: str = Form(""),
) -> Any:
    _password_login_enabled(request)
    config = _state(request).config
    next_path = auth.safe_next(next, auth.root(request))
    if not _csrf_ok(request, csrf):
        return _login_page(request, error="The form expired. Try again.", status_code=400, next_path=next_path)

    address = auth.client_address(request)
    if await auth.failures(username, address) >= auth.RATE_LIMIT_MAX:
        return _login_page(request, error=RATE_LIMITED_ERROR, status_code=429, next_path=next_path)

    account = await check_credentials(username, password)
    if account is None:
        await auth.record_failure(username, address)
        await asyncio.sleep(config.failure_delay_seconds)
        return _login_page(request, error=GENERIC_LOGIN_ERROR, status_code=401, next_path=next_path)

    await auth.clear_failures(username, address)
    token, _ = await auth.create_session(account.username, account.role, config.session_ttl_hours)
    response = RedirectResponse(next_path, status_code=303)
    auth.set_session_cookie(response, request, token, max_age=config.session_ttl_hours * 3600)
    logger.info("console login: %s", account.username)
    return response


@router.post("/logout")
async def logout(request: Request, csrf: str = Form("")) -> Any:
    _password_login_enabled(request)
    response = RedirectResponse(auth.login_path(request), status_code=303)
    if not _csrf_ok(request, csrf):
        return response
    token = request.cookies.get(auth.SESSION_COOKIE)
    if token:
        await auth.delete_session(token)
    auth.clear_session_cookie(response, request)
    return response
```

- [ ] **Step 5: Implement mounting**

Replace `src/ad_seller/interfaces/console/__init__.py` with:

```python
"""Operator console: a browser control room for the seller agent.

Mounted at ``/console`` on the API app when ``CONSOLE_ENABLED=true``.
Pages are server-rendered; every read goes through the REST API in-process
with one operator key held by the server (see docs/guides/console.md and
docs/superpowers/specs/2026-09-15-console-foundation-design.md).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .auth import ConsoleState
from .client import ApiRejected, ApiUnavailable, ConsoleApi
from .config import ConsoleConfig
from .routes import router, unexpected_error

logger = logging.getLogger(__name__)

_STATIC = Path(__file__).parent / "static"


def _build_sub_app() -> FastAPI:
    sub = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    sub.include_router(router)
    sub.mount("/static", StaticFiles(directory=str(_STATIC)), name="console_static")
    # Registered at build time, before any request, so it is part of the sub-app's
    # middleware stack. Starlette re-raises after sending the page, which is why the
    # test client is created with raise_app_exceptions=False and why uvicorn also logs it.
    sub.add_exception_handler(Exception, unexpected_error)
    return sub


def mount_console(root_app: FastAPI, config: Optional[ConsoleConfig] = None) -> ConsoleState:
    """Mount the console at /console. Idempotent: a second call refreshes config and client."""
    config = config or ConsoleConfig.from_settings()
    if not config.operator_api_key:
        raise RuntimeError(
            "CONSOLE_ENABLED=true requires CONSOLE_OPERATOR_API_KEY "
            "(mint one with: ad-seller create-operator-key --label console)"
        )
    if config.sso and not config.trusted_proxy_cidrs:
        raise RuntimeError(
            "CONSOLE_TRUSTED_IDENTITY_HEADER is set but CONSOLE_TRUSTED_PROXY_CIDRS is empty: "
            "SSO mode only trusts the header from the proxy's addresses"
        )
    sub = getattr(root_app.state, "console_app", None)
    if sub is None:
        sub = _build_sub_app()
        root_app.mount("/console", sub, name="console")
        root_app.state.console_app = sub
    transport = httpx.ASGITransport(app=root_app, raise_app_exceptions=False)
    state = ConsoleState(
        config=config,
        api=ConsoleApi(transport, config.api_base_url, config.operator_api_key, timeout=config.api_timeout_seconds),
    )
    sub.state.console = state
    return state


async def verify_console_key(root_app: FastAPI) -> None:
    """Startup check: the console key must be a valid operator key, or the app must not start."""
    sub = getattr(root_app.state, "console_app", None)
    if sub is None:
        return
    state: ConsoleState = sub.state.console
    try:
        me = await state.api.me(user="startup")
    except ApiRejected as exc:
        raise RuntimeError(
            "CONSOLE_OPERATOR_API_KEY was rejected by the API "
            f"(status {exc.status}): it must be a valid, active operator key"
        ) from exc
    except ApiUnavailable as exc:
        raise RuntimeError(f"console startup check could not reach the API: {exc.detail}") from exc
    if me.get("role") != "operator":
        raise RuntimeError("CONSOLE_OPERATOR_API_KEY is not an operator key")
    logger.info("console mounted at /console using key %s (%s)", me.get("key_id"), me.get("label"))
```

Because `current_operator` reads `request.app.state.console`, and inside a mounted sub-application `request.app` is the sub-application, the state is set on `sub.state`, while the ASGI transport targets `root_app` so the client's calls reach the REST routes. `__init__.py` is the only console module that knows the transport is in-process.

- [ ] **Step 6: Run to verify they pass**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_login_routes.py tests/unit/console -q -p no:warnings
```
Expected: all console tests pass (`test_login_routes.py`: 12 passed).

- [ ] **Step 7: Revert checks**

1. Remove the `_csrf_ok` check in `login_submit`: `test_missing_csrf_is_400` must fail. Restore.
2. Change `>= auth.RATE_LIMIT_MAX` to `> 100`: `test_sixth_failure_is_rate_limited` must fail. Restore.

- [ ] **Step 8: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/console tests/unit/console
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/console tests/unit/console
git add src/ad_seller/interfaces/console/__init__.py src/ad_seller/interfaces/console/routes.py tests/unit/console/conftest.py tests/unit/console/test_login_routes.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: mount the console at /console with login and logout"
```

---

## Task 10: Startup check, flag wiring, and the import rule

**Files:**
- Modify: `src/ad_seller/interfaces/api/main.py` (lifespan, and the end of the module)
- Test: `tests/unit/console/test_startup.py`, `tests/unit/console/test_import_rule.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/console/test_startup.py
"""The console refuses to start with a bad key, and is absent when the flag is off."""

import pytest
from fastapi import FastAPI

from ad_seller.auth.api_key_service import ApiKeyService
from ad_seller.interfaces.console import mount_console, verify_console_key
from ad_seller.interfaces.console.config import ConsoleConfig
from ad_seller.models.api_key import ApiKeyCreateRequest


async def test_missing_key_refuses_to_mount(api_app):
    with pytest.raises(RuntimeError, match="CONSOLE_OPERATOR_API_KEY"):
        mount_console(api_app, ConsoleConfig(operator_api_key=None))


async def test_sso_without_proxy_cidrs_refuses_to_mount(api_app, console_key):
    key, _ = console_key
    with pytest.raises(RuntimeError, match="CONSOLE_TRUSTED_PROXY_CIDRS"):
        mount_console(api_app, ConsoleConfig(operator_api_key=key, trusted_identity_header="X-Forwarded-Email"))


async def test_valid_operator_key_passes_startup(console_app):
    await verify_console_key(console_app)


async def test_revoked_key_fails_startup(console_app, storage, console_key):
    _, key_id = console_key
    await ApiKeyService(storage).revoke_key(key_id)
    with pytest.raises(RuntimeError, match="rejected"):
        await verify_console_key(console_app)


async def test_buyer_key_fails_startup(api_app, storage):
    buyer = await ApiKeyService(storage).create_key(
        ApiKeyCreateRequest(agency_id="agy-1", agency_name="Acme", label="acme")
    )
    mount_console(api_app, ConsoleConfig(operator_api_key=buyer.api_key))
    with pytest.raises(RuntimeError, match="rejected"):
        await verify_console_key(api_app)


async def test_verify_is_a_no_op_without_console():
    await verify_console_key(FastAPI())


def test_mount_is_idempotent(api_app, console_config):
    first = mount_console(api_app, console_config)
    second = mount_console(api_app, console_config)
    mounts = [r for r in api_app.routes if getattr(r, "path", "") == "/console"]
    assert len(mounts) == 1
    assert second is not first
    assert api_app.state.console_app.state.console is second


def test_shared_app_has_no_console_by_default():
    from ad_seller.interfaces.api.main import app

    assert not any(getattr(r, "path", "") == "/console" for r in app.routes)
```

```python
# tests/unit/console/test_import_rule.py
"""The console package only talks to the agent through the REST API.

It may import its own modules, FastAPI/Starlette, Jinja2, httpx, the settings
module, and the storage factory (for accounts and sessions). It never imports
services, crews, agents, engines, flows, tools, models, auth, or events, so
extracting it into its own service later is a base-URL change, not a rewrite.
"""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PACKAGE = REPO / "src" / "ad_seller" / "interfaces" / "console"
PACKAGE_NAME = "ad_seller.interfaces.console"

# Everything under ad_seller the console may import, by module prefix. Anything
# else under ad_seller is forbidden, whether imported absolutely or relatively.
ALLOWED = (
    PACKAGE_NAME,
    "ad_seller.config",
)
STORAGE = "ad_seller.storage.factory"  # allowed in accounts.py only


def _module_of(path: Path) -> str:
    rel = path.relative_to(REPO / "src").with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_of(path: Path) -> str:
    module = _module_of(path)
    return module if path.name == "__init__.py" else module.rsplit(".", 1)[0]


def _resolved_imports(path: Path):
    """Yield absolute module names, resolving relative imports against the file's package."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                yield node.module or ""
                continue
            base = _package_of(path).split(".")
            base = base[: len(base) - (node.level - 1)]
            yield ".".join(base + ([node.module] if node.module else []))


def test_console_imports_only_allowlisted_ad_seller_modules():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        for name in _resolved_imports(path):
            if not name.startswith("ad_seller"):
                continue
            allowed = ALLOWED + ((STORAGE,) if path.name == "accounts.py" else ())
            if not name.startswith(allowed):
                offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert offenders == []


def test_relative_imports_are_resolved_by_the_guard(tmp_path):
    """A `from ...services import x` inside the package must be caught, not skipped."""
    fake = PACKAGE / "_guard_probe.py"
    fake.write_text("from ...services import deal_service\n")
    try:
        names = list(_resolved_imports(fake))
    finally:
        fake.unlink()
    assert names == ["ad_seller.services"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_startup.py tests/unit/console/test_import_rule.py -q -p no:warnings
```
Expected: the import-rule tests pass already (the package is clean); `test_startup.py` passes except nothing yet fails. If everything passes, that is fine: `test_shared_app_has_no_console_by_default` and the wiring below are what Step 3 adds, and the revert check in Step 5 proves the tests bite.

- [ ] **Step 3: Wire the flag and the startup check into the API app**

In `src/ad_seller/interfaces/api/main.py`, inside `lifespan`, right after `start_sync_scheduler()`, add:

```python
    from ..console import verify_console_key

    await verify_console_key(application)
```

At the very end of `main.py`, after the `_mark_routes_changed` block, add:

```python
# =============================================================================
# Operator console (optional)
# =============================================================================

from ...config.settings import get_settings  # noqa: E402

if get_settings().console_enabled:
    from ..console import mount_console  # noqa: E402

    mount_console(app)
```

- [ ] **Step 4: Run the console tests and the drift tests**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console tests/unit/test_openapi_drift.py tests/unit/test_api_structure.py tests/unit/test_route_shadowing.py -q -p no:warnings
```
Expected: all pass. The OpenAPI document does not change because the console is not mounted with the flag off, and the sub-application has no OpenAPI of its own.

- [ ] **Step 5: Revert check**

In `verify_console_key`, replace the body with `return`: `test_revoked_key_fails_startup` and `test_buyer_key_fails_startup` must fail. Restore. In `mount_console`, remove the `if not config.operator_api_key` guard: `test_missing_key_refuses_to_mount` must fail. Restore.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/api/main.py tests/unit/console
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/api/main.py tests/unit/console
git add src/ad_seller/interfaces/api/main.py tests/unit/console/test_startup.py tests/unit/console/test_import_rule.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: mount the console behind CONSOLE_ENABLED and verify its key at startup"
```

This closes pull request 2: title `feat: operator console foundation (login, shell, sessions)`.

---

## Task 11: The landing page and the health partial

**Files:**
- Modify: `src/ad_seller/interfaces/console/routes.py` (add the cards, home, partial)
- Test: `tests/unit/console/test_home.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/console/test_home.py
"""The landing page: four cards from the real API, degrading one card at a time."""

import asyncio

from ad_seller.auth.api_key_service import ApiKeyService
from ad_seller.interfaces.api import deps
from tests.unit.console.conftest import html_index, login


async def test_home_requires_login(client):
    response = await client.get("/console/")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/console/login")


async def test_home_renders_shell_and_cards(client, account, console_key):
    _, key_id = console_key
    await login(client)
    page = await client.get("/console/")
    assert page.status_code == 200
    els = html_index(page.text)
    assert "nicolas" in els["who"]["text"]
    assert "active" in els["nav-setup"]["attrs"]["class"]
    assert els["nav-inbox"]["tag"] == "div" and "soon" in els["nav-inbox"]["text"]
    assert els["card-agent"]["attrs"]["data-state"] == "ok"
    assert "Healthy" in els["card-agent"]["text"]
    assert "Ad Seller System API" in els["card-agent"]["text"]
    assert 'href="/console/static/console.css"' in page.text  # derived from root_path, not typed
    assert els["card-access"]["attrs"]["data-state"] == "ok"
    assert "nicolas" in els["card-access"]["text"]
    assert key_id in els["card-access"]["text"]
    assert "console" in els["card-access"]["text"]
    assert els["card-sync"]["attrs"]["data-state"] == "ok"
    assert "Disabled" in els["card-sync"]["text"]
    assert els["card-events"]["attrs"]["data-state"] == "ok"
    # the event bus is a process-wide singleton, so earlier tests may have published
    assert "No events yet" in els["card-events"]["text"] or "Last event" in els["card-events"]["text"]
    assert 'hx-get="/console/partials/health"' in page.text
    assert 'hx-trigger="every 30s"' in page.text


async def test_partial_returns_cards_without_shell(client, account):
    await login(client)
    partial = await client.get("/console/partials/health", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "<html" not in partial.text
    assert "card-agent" in partial.text


async def test_partial_without_session_tells_htmx_to_redirect(client):
    partial = await client.get("/console/partials/health", headers={"HX-Request": "true"})
    assert partial.status_code == 401
    assert partial.headers["hx-redirect"].startswith("/console/login")


async def test_revoked_console_key_degrades_access_card_only(client, account, storage, console_key):
    _, key_id = console_key
    await login(client)
    await ApiKeyService(storage).revoke_key(key_id)
    page = await client.get("/console/")
    assert page.status_code == 200
    els = html_index(page.text)
    assert els["card-access"]["attrs"]["data-state"] == "rejected"
    assert "rejected" in els["card-access"]["text"].lower()
    # health and root need no key, so the agent card still renders
    assert els["card-agent"]["attrs"]["data-state"] == "ok"
    # the session survives: a second request is not redirected to login
    assert (await client.get("/console/")).status_code == 200


async def test_slow_route_degrades_its_card(client, console_app, account):
    await login(client)

    async def slow():
        await asyncio.sleep(0.5)

    console_app.dependency_overrides[deps._require_api_key_record] = slow
    console_app.state.console_app.state.console.api._timeout = 0.05
    try:
        page = await client.get("/console/")
    finally:
        console_app.dependency_overrides.clear()
    els = html_index(page.text)
    assert page.status_code == 200
    assert els["card-access"]["attrs"]["data-state"] == "unavailable"
    assert "timeout" in els["card-access"]["text"]
    assert els["card-agent"]["attrs"]["data-state"] == "ok"


async def test_malformed_api_body_degrades_one_card(client, console_app, account, monkeypatch):
    await login(client)
    api = console_app.state.console_app.state.console.api
    real_get = api._get

    async def get(path, user, params=None):
        return [] if path == "/health" else await real_get(path, user, params)

    monkeypatch.setattr(api, "_get", get)
    page = await client.get("/console/")
    els = html_index(page.text)
    assert page.status_code == 200
    assert els["card-agent"]["attrs"]["data-state"] == "unavailable"
    assert "unexpected response shape" in els["card-agent"]["text"]
    assert els["card-access"]["attrs"]["data-state"] == "ok"


async def test_unexpected_error_renders_error_page(client, console_app, account, caplog):
    await login(client)

    def boom():
        raise RuntimeError("template exploded")

    from ad_seller.interfaces.console import routes

    original = routes.build_cards
    routes.build_cards = boom
    try:
        page = await client.get("/console/")
    finally:
        routes.build_cards = original
    assert page.status_code == 500
    els = html_index(page.text)
    assert len(els["request-id"]["text"]) == 8
    assert "template exploded" not in page.text
    assert "template exploded" in caplog.text
    assert client.cookies["console_session"] not in caplog.text
```

- [ ] **Step 2: Run to verify they fail**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console/test_home.py -q -p no:warnings
```
Expected: `test_home_requires_login` passes (404 is not 303, so it fails too: `/console/` is not routed yet); the rest fail with 404.

- [ ] **Step 3: Implement the cards, home, and partial**

Append to `src/ad_seller/interfaces/console/routes.py`:

```python
def _card(slug: str, title: str, state: str, tone: str, value: str, detail: str) -> dict[str, str]:
    return {"slug": slug, "title": title, "state": state, "tone": tone, "value": value, "detail": detail}


def _degraded(slug: str, title: str, exc: Exception) -> dict[str, str]:
    if isinstance(exc, ApiRejected):
        reason = "console key rejected" if exc.status == 401 else "console key is not an operator key"
        return _card(slug, title, "rejected", "error", "Console key rejected", f"{reason} (HTTP {exc.status}); replace CONSOLE_OPERATOR_API_KEY on the host")
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
    return _card(
        "agent", "Agent", "ok", "ok" if healthy else "error", "Healthy" if healthy else result.status.title(),
        f"{result.name} {result.version} · checked {checked}",
    )


def _access_card(result: KeyInfo | Exception, operator: Operator) -> dict[str, str]:
    if isinstance(result, Exception):
        return _degraded("access", "Console access", result)
    if operator.session_expires_at is not None:
        left = operator.session_expires_at - datetime.now(timezone.utc)
        session = f"session {max(int(left.total_seconds() // 3600), 0)} h left"
    else:
        session = "signed in through the identity proxy"
    status = "active" if result.is_active else "revoked or expired"
    expiry = result.expires_at or "never"
    return _card(
        "access", "Console access", "ok", "ok" if result.is_active else "error",
        f"{operator.username} · {session}",
        f"API calls use key {result.label} ({result.key_id}), {status}, expires: {expiry}",
    )


def _sync_card(result: SyncStatus | Exception) -> dict[str, str]:
    if isinstance(result, Exception):
        return _degraded("sync", "Inventory sync", result)
    last = result.last_sync or "no sync yet"
    return _card(
        "sync", "Inventory sync", "ok", "ok" if result.enabled else "warn",
        "Enabled" if result.enabled else "Disabled",
        f"last sync: {last} · runs: {result.sync_count}",
    )


def _events_card(result: EventSummary | None | Exception) -> dict[str, str]:
    """Only what the API says: the console does not read the agent's settings."""
    if isinstance(result, Exception):
        return _degraded("events", "Event bus", result)
    if result is None:
        return _card("events", "Event bus", "ok", "warn", "No events yet", "the bus has published nothing this process can see")
    return _card("events", "Event bus", "ok", "ok", "Last event", f"{result.event_type} at {result.timestamp}")


async def build_cards(state: ConsoleState, operator: Operator) -> tuple[list[dict[str, str]], str]:
    api = state.api
    user = operator.username
    health, me, sync, event = await asyncio.gather(
        _call(api.health(user)), _call(api.me(user)), _call(api.inventory_sync_status(user)), _call(api.last_event(user))
    )
    checked = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    cards = [_agent_card(health, checked), _access_card(me, operator), _sync_card(sync), _events_card(event)]
    return cards, checked


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, operator: Operator = Depends(current_operator)) -> Any:
    cards, checked = await build_cards(_state(request), operator)
    return _render(request, "home.html", operator=operator, nav=_nav("setup"), cards=cards, checked_at=checked)


@router.get("/partials/health", response_class=HTMLResponse)
async def health_partial(request: Request, operator: Operator = Depends(current_operator)) -> Any:
    cards, checked = await build_cards(_state(request), operator)
    return _render(request, "partials/health_cards.html", cards=cards, checked_at=checked)
```

`build_cards` is looked up through the module at call time in `home` and `health_partial` (they call `build_cards(...)` as a module global), which is what lets the error-page test replace it.

- [ ] **Step 4: Run to verify they pass**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/console -q -p no:warnings
```
Expected: all console tests pass (`test_home.py`: 8 passed).

- [ ] **Step 5: Revert check**

In `_call`, remove the `except` clause: `test_revoked_console_key_degrades_access_card_only`, `test_slow_route_degrades_its_card`, and `test_malformed_api_body_degrades_one_card` must fail (they would render the error page instead of a degraded card). Restore. Then remove the `add_exception_handler` line in `_build_sub_app`: `test_unexpected_error_renders_error_page` must fail. Restore.

- [ ] **Step 6: Commit**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff format src/ad_seller/interfaces/console tests/unit/console
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ruff check src/ad_seller/interfaces/console tests/unit/console
git add src/ad_seller/interfaces/console/routes.py tests/unit/console/test_home.py
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "feat: console landing page with health, access, sync, and event cards"
```

---

## Task 12: Full-suite run and manual smoke test

**Files:** none changed unless the suite finds something.

- [ ] **Step 1: Full unit suite**

```bash
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit -q -p no:warnings --timeout=600
rm -f ad_seller.db data/audit_fallback.jsonl
```
Expected: all passed; the count is the previous total plus about 55 console tests. Any failure is fixed before moving on, never deselected.

- [ ] **Step 2: Manual smoke test**

```bash
export STORAGE_TYPE=sqlite DATABASE_URL="sqlite:///$(pwd)/smoke.db"
KEY=$(PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ad-seller create-operator-key --label console --quiet)
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync ad-seller create-console-user --username nicolas
CONSOLE_ENABLED=true CONSOLE_OPERATOR_API_KEY="$KEY" PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync uvicorn ad_seller.interfaces.api.main:app --port 8000
```
In a browser: `http://localhost:8000/console/` redirects to the login page; a wrong password shows the generic message; the right one lands on Setup and health with four cards; wait 30 seconds and confirm the "checked" time advances; sign out returns to login. Then stop the server and:

```bash
CONSOLE_ENABLED=true CONSOLE_OPERATOR_API_KEY=ask_live_bogus PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync uvicorn ad_seller.interfaces.api.main:app --port 8000
```
Expected: startup fails with `CONSOLE_OPERATOR_API_KEY was rejected by the API (status 401)`.

```bash
rm -f smoke.db
```

This closes pull request 3: title `feat: console landing page (Setup and health)`.

---

## Task 13: Guide, examples, changelog

**Files:**
- Create: `docs/guides/console.md`
- Modify: `mkdocs.yml` (nav), `.env.example`, `infra/docker/docker-compose.yml`, `CHANGELOG.md`

- [ ] **Step 1: Write the guide**

Create `docs/guides/console.md`:

```markdown
# Operator Console

The console is a browser control room for the people who supervise the seller agent. It is off by default and adds nothing to the API when disabled.

## Enable it

1. Mint an operator key for the console. The key stays on the server and is never sent to a browser:

   ```bash
   ad-seller create-operator-key --label console
   ```

2. Set two variables and restart:

   ```bash
   CONSOLE_ENABLED=true
   CONSOLE_OPERATOR_API_KEY=<the key from step 1>
   ```

   The app refuses to start if the key is missing, invalid, revoked, or not an operator key.

3. Create an account. Accounts are managed only on the host; there is no account route:

   ```bash
   ad-seller create-console-user --username nicolas
   ad-seller create-console-user --username nicolas --reset-password
   ad-seller create-console-user --username nicolas --disable
   ```

   Passwords are prompted, must be at least 12 characters, and are stored as scrypt hashes.

4. Open `/console/` and sign in.

## What the console does

Every page reads through the REST API with the console key, and adds an `X-Console-User` header naming the signed-in person. Sessions are opaque tokens stored server-side with a TTL (`CONSOLE_SESSION_TTL_HOURS`, default 12). Five failed logins per username or client address in ten minutes are refused for ten minutes.

Revoking the console key ends all console access at once; the landing page shows the rejected key so an operator can see why.

## Single sign-on

If an identity-aware proxy (for example oauth2-proxy) sits in front of the agent and sets a verified identity header, name that header:

```bash
CONSOLE_TRUSTED_IDENTITY_HEADER=X-Forwarded-Email
CONSOLE_TRUSTED_PROXY_CIDRS=10.0.1.0/24
```

In this mode the header is required on every console request, the password login and logout endpoints are switched off (they answer 404), and cookies are never consulted. The header is trusted only when the request's client address is inside `CONSOLE_TRUSTED_PROXY_CIDRS`; a request from any other address gets 403, and the app refuses to start if the header is configured without the networks. Create accounts with the email as the username. The proxy must strip the header from incoming requests, and the agent must not be reachable except through it.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `CONSOLE_ENABLED` | `false` | mount the console at `/console` |
| `CONSOLE_OPERATOR_API_KEY` | none | operator key the console uses for API calls |
| `CONSOLE_SESSION_TTL_HOURS` | `12` | session lifetime |
| `CONSOLE_TRUSTED_IDENTITY_HEADER` | empty | when set, SSO mode |
| `CONSOLE_TRUSTED_PROXY_CIDRS` | empty | networks the identity header is trusted from; required in SSO mode |
```

- [ ] **Step 2: Add the guide to the nav and the examples**

In `mkdocs.yml`, after the line `- Configuration: guides/configuration.md`, add:

```yaml
      - Operator Console: guides/console.md
```

In `.env.example`, after the `API_KEY_DEFAULT_EXPIRY_DAYS` comment block, add:

```bash

# =============================================================================
# Operator Console (docs/guides/console.md)
# =============================================================================
# CONSOLE_ENABLED=true
# CONSOLE_OPERATOR_API_KEY=            # ad-seller create-operator-key --label console
# CONSOLE_SESSION_TTL_HOURS=12
# CONSOLE_TRUSTED_IDENTITY_HEADER=     # e.g. X-Forwarded-Email behind an identity-aware proxy
# CONSOLE_TRUSTED_PROXY_CIDRS=         # networks the header is trusted from, e.g. 10.0.1.0/24
```

In `infra/docker/docker-compose.yml`, in the `app` service `environment` block after `REDIS_URL`, add:

```yaml
      # Operator console (docs/guides/console.md); set the key in ../../.env
      # CONSOLE_ENABLED: "true"
```

- [ ] **Step 3: CHANGELOG**

Under `## [Unreleased]` → `### Added`, add after the `me` route bullet:

```markdown
- Operator console at `/console` (off by default, `CONSOLE_ENABLED=true`):
  username and password login with server-side sessions, an
  `ad-seller create-console-user` command, and a Setup and health landing
  page that reads through the REST API with a server-held operator key.
```

- [ ] **Step 4: Build the docs and run the docs tests**

```bash
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync mkdocs build --strict 2>&1 | tail -3
rm -f ad_seller.db data/audit_fallback.jsonl
PYTHONPATH=src UV_PROJECT_ENVIRONMENT=../sellerdemo/.venv uv run --no-sync pytest tests/unit/test_docs_inventory_drift.py tests/unit/test_openapi_drift.py -q -p no:warnings
```
Expected: the build completes (if `mkdocs` is not installed in the shared environment, skip the build and say so in the PR body); both drift tests pass.

- [ ] **Step 5: Commit**

```bash
git add docs/guides/console.md mkdocs.yml .env.example infra/docker/docker-compose.yml CHANGELOG.md
git -c user.name="numaras" -c user.email="nicolas.umaras@sigma.software" commit -m "docs: operator console guide and configuration examples"
```

This closes pull request 4: title `docs: operator console guide`.

---

## Self-review against the spec

- Spec §3 package layout: Tasks 4, 6, 7, 8, 9 create every listed file; `config.py` is an addition to the spec's list (the spec put config inside `auth.py`; a separate file keeps `auth.py` from importing settings).
- Spec §3 import rule: Task 10 `test_import_rule.py`, allowlist-based and resolving relative imports, with the storage seam confined to `accounts.py` (`auth.py` reaches storage only through `accounts.kv`).
- Spec §3 `me` route: Tasks 1 and 2.
- Spec §4 accounts, login, sessions, `current_operator`, console key: Tasks 4, 5, 6, 9, 10. Rate limit, generic message, fixed delay, CSRF, cookie flags, rotation, logout: Task 9 tests.
- Spec §5 pages and palette: Task 8 templates and CSS, Task 11 cards.
- Spec §6 client: Task 7, including the two-second bound and no redirects.
- Spec §7 error handling: Task 7 (client errors), Task 9 (`guarded`, redirects, 429), Task 10 (startup refusal), Task 11 (degraded cards, error page, logs without secrets).
- Spec §8 testing: real SQLite, real API, boundary-forced failures, HTML by id, security tests, structural tests, revert checks: every task.
- Spec §9 configuration, deployment, documentation: Tasks 3, 13.
- Spec §10 delivery: PR boundaries marked after Tasks 2, 10, 12, 13.
- Not in this plan, by spec §12: real screens, roles, per-user keys, proxy container, attribution backend change, logo image, dark theme.
