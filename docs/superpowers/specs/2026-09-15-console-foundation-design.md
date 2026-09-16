# Seller console: Foundation design

Date: 2026-09-15, revised 2026-09-16 (separate service)
Status: revised after the first review round; the console now runs as its own service in its own repository and container. Awaiting colleague review of the revision.
Scope: WBS rows 1.2 to 1.6 of the seller console plan (scaffold, API client, test harness, login, application shell), plus a landing page that seeds row 4.3 (Setup and health).

Revision note: the first version placed the console inside the agent's repository as a sub-application mounted at `/console`. This version moves it to a separate repository and container that talks to the agent only over its REST API. Everything the review settled about login, sessions, the console key, SSO, typed responses, error handling, CSRF, rate limiting, and the browser decision is unchanged; sections 2, 3, 6, 7, 8, 9, 10, and 11 change to reflect the new placement.

## 1. Purpose

The seller agent negotiates prices and mints deal IDs with delegated authority. The people who delegated that authority need a place to see what the agent decided, take the decisions only a human can take, and adjust what the agent may do. The console is that place. It is a control room for the agent's operators, not an ad operations product.

The Foundation is the smallest deliverable that lets a person log in from a browser, see the agent's state, and gives every later screen a shell, a data path, and a test harness to build on.

## 2. Decisions and why

| Decision | Choice | Why |
|---|---|---|
| Frontend stack | Server-rendered Jinja2 pages with HTMX partials, in a FastAPI app | Same language and test runner as the agent, so the team and the tests carry over. No Node toolchain. |
| Where the console lives | Its own repository, `seller-console`, and its own container, next to the agent's in the same compose stack | No UI code ever needs a pull request to the agent's repository. The console has its own release cadence and CI. The agent is untouched except for small API enablers. |
| How the console reads data | Through the agent's REST API over the network, with an operator key on every call | The API is the only contract, pinned by the agent's OpenAPI document. Every gap the console hits is an API gap and becomes an upstream enabler. |
| Who logs in | Console accounts with username and password, created on the host by CLI | Every publisher can run it on day one. No identity provider required. |
| What the API sees | One operator key held by the console server, labelled `console`, plus an `X-Console-User` header naming the person | Keys never reach the browser. Revoking one key ends all console access. The header is display context for logs, chosen by the caller and not verified by the API; it is not attribution. |
| Single sign-on | A configured trusted identity header, accepted only from configured proxy networks, replaces the password login when set | Publishers with SSO put a proxy in front. In that mode the header is required on every request, cookies are never consulted, and the password endpoints are off. Nothing in the screens changes. |
| Colors | IAB Tech Lab brand: red `#EE3126`, black `#221F1F`, the site's grey ladder | Sampled from the logo and site. Status colors are semantic, not brand. |

### Alternatives considered

- **Console inside the agent's repository** (the first version of this spec): one container and in-process API calls, but UI code in the agent's repository and release, which the project does not want, and a mount that the agent has to carry.
- **Static TypeScript app with no backend**: the fullest decoupling, but the browser would have to hold the operator key, or the agent's API would have to learn to log people in first. Kept as a later option; the API-owned login it needs is recorded in the growth path.
- **Vite plus React server app**: viable in a separate repository, but a second language and a rewrite of the reviewed design for no gain the Foundation needs.
- **Static HTML with ES modules, no build**: no way to test the JavaScript.
- **Console calling the agent's service layer directly**: impossible from a separate process, and undesirable anyway: it would bypass the API's auth and hide API gaps.
- **Operator API key as the login credential**: simplest, but pastes a powerful key into a browser form and gives no per-person identity.
- **Per-user operator keys encrypted under passwords**: better API attribution, but key material at rest, more cryptography written by us, and a recovery problem. Attribution is done through the header instead.
- **SSO first**: strongest security, but requires an identity provider the publisher already runs.

## 3. Repository, package, and runtime

The console is a separate repository, `seller-console`, with its own `pyproject.toml`, tests, CI, Dockerfile, and releases. It is a small FastAPI application served by uvicorn on port 8080.

```
seller-console/
  pyproject.toml           package seller_console; runtime deps: fastapi, uvicorn, jinja2, python-multipart, httpx, aiosqlite, pydantic-settings
  Dockerfile               python:3.12-slim + uv, non-root, HEALTHCHECK on /healthz
  compose.console.yml      the console service, to be layered on the agent's compose stack
  contract/
    openapi.json           the agent's OpenAPI document at the pinned agent version (vendored)
    AGENT_VERSION          the agent commit or tag the console is built and tested against
  src/seller_console/
    __init__.py
    main.py                create_app(config) and the uvicorn entry point; lifespan runs the startup key check
    config.py              ConsoleConfig from environment variables
    store.py               the console's own key-value store (SQLite via aiosqlite): get, set with TTL, delete, keys by prefix
    accounts.py            password hashing, account records, credential check; the only module touching the store for accounts
    auth.py                sessions, CSRF cookie, login rate limit, current_operator dependency
    client.py              ConsoleApi: HTTP client to the agent's REST API over an injected transport, typed responses
    routes.py              login, logout, landing page, health partial, rendering, the exception handler
    cli.py                 seller-console create-user
    templates/
      base.html            shell: top bar, sidebar, content block
      login.html
      home.html            landing page (Setup and health seed)
      error.html           unexpected-error page with a request id
      partials/            HTMX fragments, e.g. health_cards.html
    static/
      htmx.min.js          vendored, pinned version and hash noted in the file header
      console.css
  tests/
```

The app is served at the root of its own origin. Templates, redirects, and cookie paths still derive from `root_path`, so the console also works under a proxy prefix such as `/console` without change.

The CLI is `seller-console create-user`, with `--username`, a password prompt, `--reset-password`, and `--disable`. It runs inside the console container against the console's own store.

### Dependency on the agent

The runtime package never imports the agent. A test walks the package's imports and fails on any `ad_seller` module. The agent exists for the console only as:

- the vendored `contract/openapi.json` and `AGENT_VERSION`, which say which agent the console was built against, and
- a development-only dependency on the agent package at that same version, installed from git into the test environment, so the tests run the console against the real agent app in-process.

A drift test regenerates the OpenAPI document from the pinned agent package and compares it with the vendored copy, so the two cannot silently diverge. Bumping the agent version is one commit that updates both files and whatever the diff demands.

### New API route

`GET /auth/api-keys/me` returns the calling key's metadata (`ApiKeyInfo`, no secret) for any valid key. Without it the only way to learn "who am I" is to list every key and match a twelve-character prefix that starts with a fixed string. This is an enabler on the agent, delivered as its own upstream PR, and the first entry in the console's minimum agent version.

## 4. Accounts, sessions, and the console key

### The store

The console keeps accounts, sessions, and rate-limit records in its own store, a SQLite file on a volume by default (`CONSOLE_DB_URL`, default `sqlite:///data/console.db`), with the generic interface the agent's storage also has: `get`, `set` with an optional TTL, `delete`, and `keys` by prefix pattern. Expired keys are invisible to `get` and `keys`. A Redis implementation of the same interface is the follow-up for running more than one console instance.

### Accounts

Record `console_user:<username>`:

```
{ "username": str, "password_hash": "scrypt$17$8$1$<salt hex>$<hash hex>", "role": "operator",
  "disabled": bool, "created_at": iso8601, "last_login_at": iso8601 | null,
  "credentials_changed_at": iso8601 }
```

`credentials_changed_at` is bumped by every disable, password reset, and later role change. It is what revokes sessions (below).

Passwords are hashed with `hashlib.scrypt` from the standard library at the OWASP minimum, N=2^17, r=8, p=1, with a 16-byte random salt, and compared with `hmac.compare_digest`. The stored string is self-describing (`scrypt$17$8$1$salt$hash`), so when the parameters are raised later, an account hashed with weaker ones is verified and rehashed in place on its next successful login, with no migration and without invalidating its sessions. Minimum length twelve characters, enforced by the CLI. Passwords are never logged. `role` is fixed to `operator` in the Foundation and exists so later roles need no migration.

Accounts are created, reset, and disabled only through the CLI. There are no account management routes.

### Login

CSRF is one policy, not per-route checks: every page the console renders issues (or re-issues) an HTTP-only `console_csrf` cookie and embeds the same random value in its forms, in password and SSO mode alike; a single `require_csrf` dependency on every POST route compares the form field with the cookie in constant time and answers 400 otherwise, and a test asserts every POST route carries it. `POST /login` then:

1. Rate limit check: at most five failures per username and per client address in ten minutes. Each failure is its own key with a ten-minute TTL under `rate_limit:`, and the count is the number of live keys, so concurrent failures are never lost to a read-modify-write and expiry belongs to the store. Exceeded gives 429 and a message with the wait time.
2. Account lookup and hash comparison, always taking the same code path so timing does not reveal whether the username exists.
3. Failure: one generic message for wrong username, wrong password, and disabled account, after a fixed 300 ms delay.
4. Success: create a session, set the cookie, redirect to the requested path or `/`.

### Sessions

Record `session:<token>` with `{ "username", "role", "created_at", "expires_at" }`, written with the store's TTL set to `CONSOLE_SESSION_TTL_HOURS` (default 12). The token is `secrets.token_urlsafe(32)`. The cookie `console_session` holds only the token and is HTTP-only, SameSite Lax, path from `root_path` or `/`, and Secure when the request arrived over https, directly or as reported by `X-Forwarded-Proto`. A new token is issued on every login. Logout deletes the record and clears the cookie.

The record never holds a key or a password.

A session is only a pointer to an account, not a snapshot of it. On every request `current_operator` rereads the account: a missing or disabled account, or a session created before the account's `credentials_changed_at`, kills the session on the spot. Disabling an account or resetting its password therefore ends its sessions immediately, not at the TTL. The same mechanism carries future role changes.

### current_operator

The only place that knows about cookies and headers. Returns `Operator(username, role)`.

- SSO mode (`CONSOLE_TRUSTED_IDENTITY_HEADER` set): the request's client address must be inside `CONSOLE_TRUSTED_PROXY_CIDRS`, else 403; the header must be present, else 403; the account it names must exist and be enabled, else 403. Cookies are never consulted in this mode, so a password session cannot substitute for the header, and the login and logout endpoints answer 404. The app refuses to start in SSO mode without the proxy networks. The console container must not be reachable except through the proxy.
- Password mode: read the cookie, load the session, reread the account, and return the operator with the account's current role. Missing or expired session, or a session invalidated by an account change: redirect to `/login?next=<path>` for page requests; for HTMX requests (header `HX-Request`), respond 401 with `HX-Redirect` set to the login URL.

Every console route depends on it except login, logout, `/healthz`, and static files.

### The console key

`CONSOLE_OPERATOR_API_KEY` is read once at startup. The app's lifespan calls the agent's `me` route with it before serving and fails startup, with one clear log line, if the key is invalid or not an operator key. Because the agent may still be starting when the console starts, the check retries for `CONSOLE_STARTUP_TIMEOUT_SECONDS` (default 60) while the agent is unreachable, then fails; the compose file also orders the console after the agent's health check. The key is used on every API call and never stored anywhere else. Revoking it through the API ends all console access; sessions remain but every page shows the rejected-key state until the key is replaced.

## 5. Pages

Both pages use the shell from the v2 wireframes: a left sidebar with the six screens (Inbox, Orders, Deals, Negotiation, Catalog, Setup), count badges where the screen exists, unbuilt screens rendered disabled with a "soon" tag. The top bar shows the console name, the signed-in username, and sign out.

### Login `/login`

One card: username, password, generic error strip, sign-in button, and a help line naming the CLI command. In SSO mode the route answers 404.

### Landing `/`

Title "Setup and health", Setup active in the sidebar. Four cards:

| Card | Source routes on the agent | Shows |
|---|---|---|
| Agent | `GET /health`, `GET /` | health status, API name and version, time of check |
| Console access | `GET /auth/api-keys/me` | username, session time left, console key label, id, active or revoked, expiry |
| Inventory sync | `GET /api/v1/inventory-sync/status` | enabled or disabled, last run, watermark when present |
| Event bus | `GET /events` | last event type and time, or "no events yet"; only what the API returns, never local settings |

The cards live in a partial, `GET /partials/health`, which HTMX polls every 30 seconds (`hx-trigger="every 30s"`). The page has no JavaScript of its own. The agent's event stream, when it exists, replaces the timer with an event trigger and adds a relay route; the cards do not change.

### Palette

| Token | Value | Use |
|---|---|---|
| brand red | `#EE3126` | active sidebar item, primary button |
| brand black | `#221F1F` | headings |
| text | `#3F3F3F` | body |
| text secondary | `#5D5D5D` | secondary text |
| label | `#7D7D7D` | uppercase labels, input borders |
| line | `#E4E4E4` | borders |
| ground | `#F7F6F6` | sidebar, page background |
| ok | `#1F7A3F` | healthy, enabled |
| warning | `#B7791F` | disabled, stale |
| error | `#B3261E` | errors, rejected key |

The wordmark is rendered as text. Whether the console ships the IAB logo image is a decision to take with IAB Tech Lab; the template keeps the logo slot as one include so it can be swapped.

## 6. API client and data flow

`client.py` defines `ConsoleApi`, built once at startup with an httpx transport, the agent's base URL, and the console key. It owns no connection: each call opens and closes its own httpx client, so there is nothing to leak and nothing to close at shutdown. In production the transport is `httpx.AsyncHTTPTransport` and the base URL is `SELLER_AGENT_URL` (in the compose stack, `http://app:8000`). In tests the transport is `httpx.ASGITransport` over the pinned agent app, so the same client code runs against the real routes in-process. Only `create_app` knows which. Every request carries `Authorization: Bearer <console key>` and `X-Console-User: <username>`.

Foundation methods: `me()`, `health()` (health plus root, for the version), `inventory_sync_status()`, `last_event()`. Each validates the JSON body into a console-owned model (`KeyInfo`, `Health`, `SyncStatus`, `EventSummary`; unknown fields ignored) and returns it, or raises `ApiUnavailable(status, detail)` for any non-2xx status other than 401 and 403, for connection errors, timeouts, non-JSON bodies, and bodies that do not fit the model, and `ApiRejected(status)` for 401 and 403. A changed or malformed field therefore degrades one card and can never reach a template. Nothing outside `client.py` imports httpx.

Client rules: never follow redirects; two-second bound per call, enforced with `asyncio.wait_for` so it holds for both transports; no retries (the poll is the retry). TLS to the agent is whatever `SELLER_AGENT_URL` says; inside the compose network it is plain HTTP on the private network.

Page request flow:

1. Browser requests `/`; `current_operator` resolves the session.
2. The route calls the client methods it needs, concurrently with `asyncio.gather` where they are independent.
3. The route renders the template with the typed models. Templates use only what the API returned.
4. HTMX polls the partial route, which reuses the same template fragment without the shell.

## 7. Error handling

| Condition | Behaviour |
|---|---|
| API 401 on the console key | Console access card shows "console key rejected" in the error color; other cards render; page is 200. Sessions are kept. |
| API 403 on the console key | Same, with "console key is not an operator key". |
| Agent unreachable (connection refused, DNS, TLS) | Every card shows "unavailable, agent unreachable"; the page is 200 and the next poll retries. Login still works, because it needs only the console's own store. |
| API 4xx other than 401/403, 5xx, timeout, non-JSON, or a body that does not fit the console's model | That card shows "unavailable", the status, and the reason; the next poll retries. Never a stack trace. |
| Session missing or expired | Redirect to login with `next`; `HX-Redirect` for HTMX requests. |
| Login failure | Generic message, fixed delay. Rate limit exceeded: 429 with the wait time. |
| Console misconfigured at startup | Missing key, missing store path, or SSO header without proxy networks: `create_app` raises before serving. Key rejected by the agent: the lifespan raises after the retry window and the container exits non-zero, which compose reports. |
| Unexpected exception in a console route | One exception handler registered on the app at build time renders a plain error page with a request id and logs the traceback; `HTTPException` keeps its normal handling. Log lines never contain the console key, a session token, or a password; a test checks this. |

`GET /healthz` answers 200 with the app version once the startup check has passed; it is the container's health check and needs no session.

## 8. Testing

All tests are pytest under `tests/`, using the FastAPI TestClient against the console app.

Browser automation is intentionally deferred from the Foundation. Server-side tests verify the HTMX attributes, the partial response, asset serving, and the HX-Redirect behaviour. Before the landing-page PR merges, a manual smoke test must confirm login, the 30-second DOM refresh, the session-expiry redirect, and logout. Browser automation is added before the first mutating or multi-step HTMX workflow.

- **Real store.** The console's SQLite store on a temporary path. Accounts are created through the CLI function.
- **Real agent.** The pinned agent package is a development dependency; tests build the agent's app, mint a real operator key through its key service, and give the console client an `ASGITransport` over it. No route of the agent is mocked.
- **Failures forced at the boundary.** Revoked key by revoking it through the agent's API. Timeouts and 5xx by overriding one agent route's dependency to sleep or raise. Agent unreachable by pointing the client at a transport that refuses connections.
- **HTML assertions** through a small helper on the standard library HTML parser, finding elements by id and data attributes only.
- **Security tests**: cookie flags; token rotation on login; logout deletes the record; CSRF token required; rate limit trips on the sixth failure and clears after the TTL; SSO spoofing from an untrusted address, missing header, stale cookie, unknown and disabled identity; sessions die on disable and password reset; no secret substring in logs captured on login and error paths.
- **Structural tests**: the runtime package imports nothing from the agent; the vendored OpenAPI document matches the pinned agent; every POST route carries the CSRF dependency.
- **Wiring tests**: `create_app` refuses bad configuration; the real lifespan is entered with a valid key and with a revoked key; the startup retry gives up after the timeout when the agent is unreachable.
- **Beyond unit tests, before each PR merges**: a container build; a compose smoke that starts the pinned agent and the console together, must refuse a bad key, and must serve the login page with a good one; and CI on the PR itself in the console repository.
- **Revert checks.** Each implementation task names the test that goes red when its change is reverted.
- **Not covered in the Foundation.** A Redis store and multi-instance behaviour.

## 9. Configuration, deployment, documentation

Environment variables of the console container:

| Variable | Default | Meaning |
|---|---|---|
| `SELLER_AGENT_URL` | none, required | base URL of the agent's API, e.g. `http://app:8000` |
| `CONSOLE_OPERATOR_API_KEY` | none, required | operator key the console uses for every API call |
| `CONSOLE_DB_URL` | `sqlite:///data/console.db` | the console's own store; mount `/data` as a volume |
| `CONSOLE_SESSION_TTL_HOURS` | `12` | session lifetime |
| `CONSOLE_TRUSTED_IDENTITY_HEADER` | empty | when set, SSO mode: this header names the user, required on every request |
| `CONSOLE_TRUSTED_PROXY_CIDRS` | empty | networks the header is trusted from; required in SSO mode |
| `CONSOLE_STARTUP_TIMEOUT_SECONDS` | `60` | how long to wait for the agent at startup before failing |

No signing secret is needed: session tokens are random and the CSRF check is a cookie-to-form comparison enforced by one dependency on every POST route.

Deployment: one image, `seller-console`, built from the console repository. `compose.console.yml` adds a `console` service to the agent's stack: it depends on the agent's service being healthy, mounts a volume at `/data`, exposes port 8080, and reads the variables above from `.env`. Running the stack is `docker compose -f infra/docker/docker-compose.yml -f compose.console.yml up -d` from a checkout that has both files, and the console README shows it. Onboarding an operator is `docker compose exec console seller-console create-user --username <name>`. The agent's own compose file and image do not change.

Documentation lives in the console repository: a README covering enabling, minting the console key on the agent (`ad-seller create-operator-key --label console`), creating a user, the SSO header, and bumping the agent version. The agent's repository receives only the documentation that belongs to its enabler routes.

## 10. Delivery

Agent enablers, as small pull requests into `ui/dev` on the fork and then upstream, each green on its own:

1. `GET /auth/api-keys/me` with test and docs.

Console, as small pull requests in the console repository, each green on its own:

0. Repository scaffold: package, CI workflow, Dockerfile, vendored contract at the pinned agent version, drift and import tests.
2. Store, accounts, CLI, sessions, login, logout, empty shell.
3. Landing page cards and the polling partial.
4. Compose file, README, and the compose smoke test.

The fork's `ui/dev` branch remains the integration branch for agent-side enablers only.

## 11. Growth path

- **Attribution in the API**: `X-Console-User` is context, not attribution, because whoever holds any operator key can set it. Before the console performs mutations, before audit records name a person, and before roles are enforced, the API must receive something it can verify: either a per-user delegated credential, or an actor assertion signed with a secret bound to the console key and checked by the API. The API, not the console's routes, enforces authorization at that point. Recording the bare header on audit events is acceptable only as a "claimed by" field next to the key id that actually authenticated.
- **Roles**: the account `role` field gains values and routes check it; a role change bumps `credentials_changed_at`, so open sessions pick it up at once. The API still sees one key.
- **Per-user keys**: only if the API itself must enforce roles; added behind `current_operator` without touching screens.
- **SSO**: set the trusted header and the proxy networks and put a proxy in front of the console; the account records become the profile table keyed by the header value. A later step replaces the bare header with a signed, audience-bound assertion from the proxy (for example the JWT oauth2-proxy can forward), verified against the identity provider's keys; that needs a JWT library and an identity-provider contract, so it is not in the Foundation.
- **Live updates**: an operator-gated event stream route on the agent, subscribing to its event bus, replaces the poll; the console adds a relay route and the HTMX SSE extension. Web Push for closed browsers needs a sender that consumes the same stream.
- **Multiple console instances**: a Redis implementation of the store interface; nothing else changes.
- **A client-side app**: possible once the agent's API owns login (session cookies or tokens, per-user accounts, CSRF, rate limiting on the browser path). Until then the console server is the only safe holder of the key.

## 12. Out of scope for the Foundation

Every real screen; roles beyond `operator`; per-user API keys; the proxy container; the backend attribution change; the event stream; the IAB logo image; a dark theme; a published agent image (the compose smoke builds the agent from the pinned checkout).

## 13. Implementation plan impact

The plan in `docs/superpowers/plans/2026-09-15-console-foundation.md` was written for the in-repository placement and needs a revision before execution. What changes: the package path and name; the store module replaces the agent's storage seam; `create_app` and its own lifespan replace `mount_console` and the agent's lifespan wiring; the settings move from the agent's `Settings` to the console's own; the transport is `AsyncHTTPTransport` in production and `ASGITransport` over the pinned agent package in tests; Task 0 becomes the console repository scaffold and CI; the agent-side `me` route task is unchanged; the compose and smoke tasks target the console's compose file. What stays: every test and behaviour from the review round.
