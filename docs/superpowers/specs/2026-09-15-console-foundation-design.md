# Seller console: Foundation design

Date: 2026-09-15, revised 2026-09-16 (separate service; second review round applied)
Status: revised after two review rounds; the console runs as its own service in its own repository and container. Awaiting colleague review of the second revision.
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
- **Per-user operator keys encrypted under passwords**: better API attribution, but key material at rest, more cryptography written by us, and a recovery problem. The Foundation carries only unverified display context in the header; verifiable attribution is a growth-path item.
- **SSO first**: strongest security, but requires an identity provider the publisher already runs.

## 3. Repository, package, and runtime

The console is a separate repository, `seller-console`, with its own `pyproject.toml`, tests, CI, Dockerfile, and releases. It is a small FastAPI application served by uvicorn on port 8080.

```
seller-console/
  pyproject.toml           package seller_console; runtime deps: fastapi, uvicorn, jinja2, python-multipart, httpx, aiosqlite, pydantic-settings
  Dockerfile               python:3.12-slim + uv, non-root, HEALTHCHECK on /healthz
  compose.yml              the console next to the pinned agent, Postgres, and Redis; the agent is built from git at AGENT_VERSION (full SHA)
  compose.proxy.yml        production overlay: a TLS proxy in front, the console port not published
  agent.env.example        variables the agent reads; console.env.example: variables the console reads. Never one shared file
  scripts/smoke.sh         the compose smoke, asserting every step; run by CI
  contract/
    openapi.json           the agent's OpenAPI document at the pinned agent version (vendored)
    AGENT_VERSION          the agent commit or tag the console is built and tested against
  src/seller_console/
    __init__.py
    main.py                create_app(config) and the uvicorn entry point; lifespan runs the startup key check
    config.py              ConsoleConfig from environment variables
    store.py               the console's own key-value store (SQLite via aiosqlite): get, versioned set and compare-and-set, TTL, delete, keys by prefix, purge
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

The app is served at the root of its own origin. Behind a proxy prefix, `CONSOLE_ROOT_PATH` is passed to FastAPI as `root_path`, and templates, redirects, and cookie paths derive from it, so the console also works under `/console` without change. The development compose binds the port to loopback only; production exposes the console solely through the proxy overlay.

The CLI is `seller-console create-user`, with `--username`, a password prompt, `--reset-password`, and `--disable`. It runs inside the console container against the console's own store.

### Dependency on the agent

The runtime package never imports the agent. A test walks the package's imports and fails on any `ad_seller` module. The agent exists for the console only as:

- the vendored `contract/openapi.json` and `AGENT_VERSION`, which say which agent the console was built against, and
- a development-only dependency on the agent package at that same version, installed from git into the test environment, so the tests run the console against the real agent app in-process.

A drift test regenerates the OpenAPI document from the pinned agent package and compares it with the vendored copy, so the two cannot silently diverge. The document is the shape contract only where the agent declares response models; the routes the console reads gain explicit response models as an agent enabler (below), and until every consumed route has one, the console-owned models plus the in-process tests against the pinned agent are what define the body contract. Bumping the agent version is one commit that updates the pin in its three places (`AGENT_VERSION`, the dev dependency, the compose build context, always the full 40-character SHA), the vendored document, and whatever the diff demands.

### Agent enablers

One small agent PR carries what the console needs from the API:

- `GET /auth/api-keys/me` returns the calling key's metadata (`ApiKeyInfo`, declared as its response model, no secret) for any valid key. Without it the only way to learn "who am I" is to list every key and match a twelve-character prefix that starts with a fixed string.
- Response models on the routes the console reads: `GET /`, `GET /health`, `GET /api/v1/inventory-sync/status`, and `GET /events`, so the OpenAPI document states their shapes instead of `{}`.
- `GET /events` returns the newest events: the storage bus sorts by timestamp before applying the limit, so "last event" is the last event.

These are the first entries in the console's minimum agent version. Whether they open upstream is the repository owner's decision, reaffirmed on 2026-09-15.

## 4. Accounts, sessions, and the console key

### The store

The console keeps accounts, sessions, CSRF nonces, and rate-limit records in its own store, a SQLite file on a volume (`CONSOLE_DB_URL`; the image sets `sqlite:////data/console.db` for the `/data` volume, the development default is a relative path). The interface is the agent's generic one plus versioning: `get`, `get_versioned`, `set` with an optional TTL (every write increments a version), `set_if_version` (compare-and-set: the write happens only if the stored version is the expected one), `delete`, `keys` by prefix pattern, and `purge_expired`. Expired keys are invisible to `get` and `keys`; purge runs at startup and on every login attempt. Every read-modify-write in the console goes through compare-and-set, so the CLI and the server, which use separate connections, cannot overwrite each other's changes. A Redis implementation of the same interface is the follow-up for running more than one console instance.

### Accounts

Record `console_user:<username>`:

```
{ "username": str, "password_hash": "scrypt$17$8$1$<salt hex>$<hash hex>", "role": "operator",
  "disabled": bool, "credential_version": int, "created_at": iso8601,
  "last_login_at": iso8601 | null, "credentials_changed_at": iso8601 }
```

`credential_version` starts at 1 and is incremented by every disable, enable, password reset, and later role change; `credentials_changed_at` records when. Sessions carry the exact version they were issued under and are valid only while it equals the account's (below). Every account write is a compare-and-set on the record's store version, retried on conflict; a login that finds the account changed while it was hashing refuses rather than writing a stale record back.

Passwords are hashed with `hashlib.scrypt` from the standard library at the OWASP minimum, N=2^17, r=8, p=1, with a 16-byte random salt, and compared with `hmac.compare_digest`. Hashing runs in a worker thread under a semaphore of four, so it never blocks the event loop and a burst of logins cannot exhaust memory (each hash needs 128 MiB). The stored string is self-describing (`scrypt$17$8$1$salt$hash`), so when the parameters are raised later, an account hashed with weaker ones is verified and rehashed in place on its next successful login, with no migration and without invalidating its sessions. Minimum length twelve characters, enforced by the CLI. Passwords are never logged. `role` is fixed to `operator` in the Foundation and exists so later roles need no migration.

Accounts are created, reset, and disabled only through the CLI. There are no account management routes.

### Login

CSRF is one policy, not per-route checks, and it is the synchronizer-token pattern, not a cookie-to-form comparison: every page the console renders stores a fresh random token in the store (`csrf:<token>`, one hour TTL, bound to the signed-in username or to "anonymous" before login) and embeds it in its forms; a single `require_csrf` dependency on every unsafe route (POST, PUT, PATCH, DELETE, enforced by a structural test) consumes the token, requires that its binding matches the current session (or anonymous for login), and also rejects any request whose `Origin` (or, failing that, `Referer`) names another origin. A token that was never issued, was already used, or belongs to another session gives 400. `POST /login` then:

1. Reserve an attempt: the attempt is recorded first, as its own ten-minute key under `rate_limit:` for the username and for the client address, and the count of live keys is read afterwards. Because recording precedes admission, concurrent attempts cannot all pass the boundary. More than five live attempts in either scope gives 429 with the wait time.
2. Account lookup and hash comparison, always taking the same code path so timing does not reveal whether the username exists.
3. Failure: one generic message for wrong username, wrong password, and disabled account, after a fixed 300 ms delay. The attempt record stays.
4. Success: this attempt's own records are released and the username's failure keys are cleared; the client address's budget is left alone, so a success from one address never resets what other attempts from it have spent. Then create a session, set the cookie, redirect to the requested path or `/`.

### Sessions

Record `session:<token>` with `{ "username", "role", "credential_version", "created_at", "expires_at" }`, written with the store's TTL set to `CONSOLE_SESSION_TTL_HOURS` (default 12). The token is `secrets.token_urlsafe(32)`. The cookie `console_session` holds only the token and is HTTP-only, SameSite Lax, path from `root_path` or `/`, and Secure when the request arrived over https, directly or as reported by `X-Forwarded-Proto`. A new token is issued on every login. Logout deletes the record and clears the cookie.

The record never holds a key or a password.

A session is only a pointer to an account, not a snapshot of it. On every request `current_operator` rereads the account: a missing or disabled account, or a `credential_version` that no longer equals the one the session was issued under, kills the session on the spot. Equality on an exact version, not a timestamp comparison, means a session issued in the same instant as a reset cannot survive it. Disabling an account or resetting its password therefore ends its sessions immediately, not at the TTL. The same mechanism carries future role changes.

### current_operator

The only place that knows about cookies and headers. Returns `Operator(username, role)`.

- SSO mode (`CONSOLE_TRUSTED_IDENTITY_HEADER` set): the request's client address must be inside `CONSOLE_TRUSTED_PROXY_CIDRS`, else 403; the header must be present, else 403; the account it names must exist and be enabled, else 403. Cookies are never consulted in this mode, so a password session cannot substitute for the header, and the login and logout endpoints answer 404. The app refuses to start in SSO mode without the proxy networks. The console container must not be reachable except through the proxy.
- Password mode: read the cookie, load the session, reread the account, require the session's `credential_version` to equal the account's, and return the operator with the account's current role. Missing or expired session, or a session invalidated by an account change: redirect to `/login?next=<path>` for page requests; for HTMX requests (header `HX-Request`), respond 401 with `HX-Redirect` set to the login URL.

Every console route depends on it except login, logout, `/healthz`, and static files.

### The console key

`CONSOLE_OPERATOR_API_KEY`, or the file named by `CONSOLE_OPERATOR_API_KEY_FILE` (a mounted secret, which wins when both are set), is read once at startup. The app's lifespan calls the agent's `me` route with it before serving and fails startup, with one clear log line, if the key is invalid or not an operator key. Because the agent may still be starting when the console starts, the check retries for `CONSOLE_STARTUP_TIMEOUT_SECONDS` (default 60) while the agent is unreachable, then fails; the compose file also orders the console after the agent's health check. The key is used on every API call and never stored anywhere else. Revoking it through the API ends all console access; sessions remain but every page shows the rejected-key state until the key is replaced. The key is a full operator key: a compromise of the console yields operator power on the agent. The compose network, the proxy, and the key's own revocability are the Foundation's mitigations; a read-scoped service credential is the growth-path enabler that removes the overprivilege (section 11).

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

`client.py` defines `ConsoleApi`, built once at startup with an httpx transport, the agent's base URL, and the console key. It owns one long-lived `httpx.AsyncClient` over that transport, created with the app and closed once in the app's lifespan; httpx closes a supplied transport when a client closes, so a client per call would close the shared transport after the first request. Concurrent calls share the one client, which is what it is for. In production the transport is `httpx.AsyncHTTPTransport` and the base URL is `SELLER_AGENT_URL` (in the compose stack, `http://app:8000`). In tests the transport is `httpx.ASGITransport` over the pinned agent app, so the same client code runs against the real routes in-process. Only `create_app` knows which. Every request carries `Authorization: Bearer <console key>` and `X-Console-User: <username>`.

Foundation methods: `me()`, `health()` (health plus root, for the version), `inventory_sync_status()`, `last_event()` (the agent returns events newest first once the ordering enabler lands; the console still takes the maximum timestamp of what it receives, so it is correct against both agent versions). Each validates the JSON body into a console-owned model (`KeyInfo`, `Health`, `SyncStatus`, `EventSummary`; unknown fields ignored) and returns it, or raises `ApiUnavailable(status, detail)` for any status outside 200 to 299 other than 401 and 403 (redirects included: the client never follows them and never parses them), for connection errors, timeouts, non-JSON bodies, and bodies that do not fit the model, and `ApiRejected(status)` for 401 and 403. A changed or malformed field therefore degrades one card and can never reach a template. Nothing outside `client.py` imports httpx.

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
| Login failure | Generic message, fixed delay; the attempt stays recorded. Rate limit exceeded: 429 with the wait time. Account changed while the login was hashing: refused with the generic message. |
| CSRF token missing, used, bound to another session, or cross-origin request | 400. |
| Console misconfigured at startup | Missing key (and no key file), missing store path, or SSO header without proxy networks: `create_app` raises before serving. Key rejected by the agent: the lifespan raises after the retry window and the container exits non-zero, which compose reports. |
| Unexpected exception in a console route | One exception handler registered on the app at build time renders a plain error page with a request id and logs the traceback; `HTTPException` keeps its normal handling. Log lines never contain the console key, a session token, or a password; a test checks this. |

`GET /healthz` answers 200 with the app version once the startup check has passed; it is the container's health check and needs no session.

## 8. Testing

All tests are pytest under `tests/`, using the FastAPI TestClient against the console app.

Browser automation is intentionally deferred from the Foundation. Server-side tests verify the HTMX attributes, the partial response, asset serving, and the HX-Redirect behaviour. Before the landing-page PR merges, a manual smoke test must confirm login, the 30-second DOM refresh, the session-expiry redirect, and logout. Browser automation is added before the first mutating or multi-step HTMX workflow.

- **Real store.** The console's SQLite store on a temporary path. Accounts are created through the CLI function. Races are tested with two store connections and controlled barriers: a disable during a login's hashing must not be undone, a reset during a login must not issue a surviving session, and ten concurrent login attempts must all count.
- **Real agent.** The pinned agent package is a development dependency; tests build the agent's app, mint a real operator key through its key service, and give the console client an `ASGITransport` over it. No route of the agent is mocked.
- **Failures forced at the boundary.** Revoked key by revoking it through the agent's API. Timeouts and 5xx by overriding one agent route's dependency to sleep or raise. Agent unreachable by pointing the client at a transport that refuses connections.
- **HTML assertions** through a small helper on the standard library HTML parser, finding elements by id and data attributes only.
- **Security tests**: cookie flags; token rotation on login; logout deletes the record; CSRF token required, single-use, session-bound, and every unsafe method covered; cross-origin requests refused; rate limit trips on the sixth attempt, survives a success from the same address, and clears after the TTL; SSO spoofing from an untrusted address, missing header, stale cookie, unknown and disabled identity; sessions die on disable and password reset; no secret substring in logs captured on login and error paths.
- **Structural tests**: the runtime package imports nothing from the agent; the vendored OpenAPI document matches the pinned agent and the three copies of the pin agree; every POST, PUT, PATCH, and DELETE route carries the CSRF dependency; the vendored HTMX file matches a digest pinned in the repository, obtained independently of the download.
- **Wiring tests**: `create_app` refuses bad configuration; the lifespan is entered the way a server enters it, through Starlette's `TestClient` context on the built app, with a valid key and with a revoked key; the startup retry gives up after the timeout when the agent is unreachable; the API client is closed exactly once, at shutdown, never per call.
- **Beyond unit tests, before each PR merges**: CI in the console repository runs the unit tests, builds the image, and runs `scripts/smoke.sh`, which starts the pinned agent and the console together and asserts, with exit codes rather than printed values, that a bad key stops the console, a good one serves the login page and the health endpoint, and the rendered compose environment gives no service another service's secrets. The agent-side enabler PRs get the agent's full CI on the fork, which requires the fork's workflow trigger to include `ui/dev`.
- **Revert checks.** Each implementation task names the test that goes red when its change is reverted.
- **Not covered in the Foundation.** A Redis store and multi-instance behaviour.
- **Ordering.** The container, compose stack, and smoke land before the landing page, so the manual browser check has a stack to run on when it is required.

## 9. Configuration, deployment, documentation

Environment variables of the console container:

| Variable | Default | Meaning |
|---|---|---|
| `SELLER_AGENT_URL` | none, required | base URL of the agent's API, e.g. `http://app:8000` |
| `CONSOLE_OPERATOR_API_KEY` | none | operator key the console uses for every API call; required unless the file variable is set |
| `CONSOLE_OPERATOR_API_KEY_FILE` | empty | path of a mounted secret holding the key; wins over the variable |
| `CONSOLE_DB_URL` | `sqlite:///data/console.db` (image: `sqlite:////data/console.db`) | the console's own store; the image mounts `/data` as a volume |
| `CONSOLE_ROOT_PATH` | empty | mount prefix when served behind a proxy prefix, e.g. `/console` |
| `CONSOLE_SESSION_TTL_HOURS` | `12` | session lifetime |
| `CONSOLE_TRUSTED_IDENTITY_HEADER` | empty | when set, SSO mode: this header names the user, required on every request |
| `CONSOLE_TRUSTED_PROXY_CIDRS` | empty | networks the header is trusted from; required in SSO mode |
| `CONSOLE_STARTUP_TIMEOUT_SECONDS` | `60` | how long to wait for the agent at startup before failing |

No signing secret is needed: session tokens are random and the CSRF check is a cookie-to-form comparison enforced by one dependency on every POST route.

Deployment: one image, `seller-console`, built from the console repository with a non-editable install so the copied environment is self-contained. The repository's `compose.yml` is a complete stack: the agent built from its git repository at `AGENT_VERSION` (full SHA; a test checks the three copies agree), Postgres, Redis, and the `console` service, which depends on the agent being healthy, mounts a volume at `/data`, and publishes port 8080 on loopback only. Each service reads its own file: `agent.env` for the agent's provider keys and settings, `console.env` for the console's; no file is shared, and the smoke test renders the compose configuration to prove no service sees another's secrets. For production, `compose.proxy.yml` adds a TLS-terminating proxy and removes the published console port, so the console is reachable only through the proxy. `docker compose up -d --build` runs the stack; onboarding an operator is `docker compose exec console seller-console create-user --username <name>`. To add the console to an existing agent stack instead, only the `console` service and its volume are copied into that stack's compose file. The agent's own compose file and image do not change.

Documentation lives in the console repository: a README covering enabling, minting the console key on the agent (`ad-seller create-operator-key --label console`), creating a user, the SSO header, and bumping the agent version. The agent's repository receives only the documentation that belongs to its enabler routes.

## 10. Delivery

Agent side, on the fork's `ui/dev` (with the fork's CI trigger widened to `ui/dev` first, fork-only):

1. `GET /auth/api-keys/me` with its response model, response models on the four routes the console reads, newest-first event listing, tests, and regenerated docs. Opening it upstream is the repository owner's decision, reaffirmed on 2026-09-15.

Console, as small pull requests in the console repository, each green on its own:

0. Repository scaffold: package, CI workflow, vendored contract at the pinned agent version, drift and import tests.
2. Store, accounts, CLI, sessions, login, logout, empty shell, startup check.
3. Container image, compose stack, proxy overlay, README, and the checked smoke script wired into CI.
4. Landing page cards and the polling partial, with the manual browser check on the stack from 3.

The fork's `ui/dev` branch remains the integration branch for agent-side enablers only.

## 11. Growth path

- **A read-scoped service credential**: the console holds a full operator key today, so a compromise of a read-only console yields every operator mutation on the agent. The enabler is a scope on agent API keys (for example `read`), enforced in the operator dependency and settable from the key CLI; the console then runs on a read-scoped key and widens the scope per screen as mutations arrive. A verifiable actor assertion does not remove this overprivilege; only scoping does.
- **Attribution in the API**: `X-Console-User` is context, not attribution, because whoever holds any operator key can set it. Before the console performs mutations, before audit records name a person, and before roles are enforced, the API must receive something it can verify: either a per-user delegated credential, or an actor assertion signed with a secret bound to the console key and checked by the API. The API, not the console's routes, enforces authorization at that point. Recording the bare header on audit events is acceptable only as a "claimed by" field next to the key id that actually authenticated.
- **Roles**: the account `role` field gains values and routes check it; a role change bumps `credentials_changed_at`, so open sessions pick it up at once. The API still sees one key.
- **Per-user keys**: only if the API itself must enforce roles; added behind `current_operator` without touching screens.
- **SSO**: set the trusted header and the proxy networks and put a proxy in front of the console; the account records become the profile table keyed by the header value. A later step replaces the bare header with a signed, audience-bound assertion from the proxy (for example the JWT oauth2-proxy can forward), verified against the identity provider's keys; that needs a JWT library and an identity-provider contract, so it is not in the Foundation.
- **Live updates**: an operator-gated event stream route on the agent, subscribing to its event bus, replaces the poll; the console adds a relay route and the HTMX SSE extension. Web Push for closed browsers needs a sender that consumes the same stream.
- **Multiple console instances**: a Redis implementation of the store interface; nothing else changes.
- **A client-side app**: possible once the agent's API owns login (session cookies or tokens, per-user accounts, CSRF, rate limiting on the browser path). Until then the console server is the only safe holder of the key.

## 12. Out of scope for the Foundation

Every real screen; roles beyond `operator`; per-user API keys; the proxy container; the backend attribution change; the event stream; the IAB logo image; a dark theme; a published agent image (the compose smoke builds the agent from the pinned checkout).

## 13. Implementation plan

The plan in `docs/superpowers/plans/2026-09-15-console-foundation.md` is revised for this placement: fifteen tasks across the two repositories, with the agent-side `me` route unchanged and every behaviour and test from the review round carried over.
