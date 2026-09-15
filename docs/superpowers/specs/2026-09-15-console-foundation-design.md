# Seller console: Foundation design

Date: 2026-09-15
Status: approved in design review, awaiting colleague review
Scope: WBS rows 1.2 to 1.6 of the seller console plan (scaffold, API client, test harness, login, application shell), plus a landing page that seeds row 4.3 (Setup and health).

## 1. Purpose

The seller agent negotiates prices and mints deal IDs with delegated authority. The people who delegated that authority need a place to see what the agent decided, take the decisions only a human can take, and adjust what the agent may do. The console is that place. It is a control room for the agent's operators, not an ad operations product.

The Foundation is the smallest deliverable that lets a person log in from a browser, see the agent's state, and gives every later screen a shell, a data path, and a test harness to build on.

## 2. Decisions and why

| Decision | Choice | Why |
|---|---|---|
| Frontend stack | Server-rendered Jinja2 pages with HTMX partials, inside FastAPI | The agent is Python only. One language, one test runner, one container. No Node in CI or Docker. |
| Where the console lives | A package `src/ad_seller/interfaces/console/`, mounted at `/console` behind a flag | Sibling of the existing `api`, `chat`, and `cli` interfaces. Optional by default. |
| How the console reads data | Through the REST API, in-process, with an operator key on every call | The API stays the only contract. Every gap the console hits is an API gap. Extraction into a separate service later is a base URL change. |
| Who logs in | Console accounts with username and password, created on the host by CLI | Every publisher can run it on day one. No identity provider required. |
| What the API sees | One operator key held by the server, labelled `console`, plus an `X-Console-User` header naming the person | Keys never reach the browser. Revoking one key ends all console access. The header puts the person on the wire from the first commit. |
| Single sign-on | A configured trusted identity header replaces the password check when set | Publishers with SSO put a proxy in front. Nothing in the screens changes. |
| Colors | IAB Tech Lab brand: red `#EE3126`, black `#221F1F`, the site's grey ladder | Sampled from the logo and site. Status colors are semantic, not brand. |

### Alternatives considered

- **Vite plus React**: fastest to generate, but adds Node to the Docker build and CI of a Python-only repo and eats Foundation time on toolchain.
- **Static HTML with ES modules, no build**: no Node, but no way to test the JavaScript.
- **Console calling the service layer directly**: fewer moving parts, but re-implements the operator gate and wire mapping, and hides API gaps.
- **Separate console service**: cleanest separation, but a second container, cross-origin cookies, and a network hop before the first screen exists. Kept as the extraction path, not the starting point.
- **Operator API key as the login credential**: simplest, but pastes a powerful key into a browser form and gives no per-person identity.
- **Per-user operator keys encrypted under passwords**: better API attribution, but key material at rest, more cryptography written by us, and a recovery problem. Attribution is done through the header instead.
- **SSO first**: strongest security, but requires an identity provider the publisher already runs.

## 3. Package layout and mounting

```
src/ad_seller/interfaces/console/
  __init__.py        mount_console(app) and nothing else public
  routes.py          one APIRouter, every path under /console
  auth.py            current_operator dependency, session store, account checks
  client.py          ConsoleApi: in-process HTTP client to the REST API
  templates/
    base.html        shell: top bar, sidebar, content block
    login.html
    home.html        landing page (Setup and health seed)
    partials/        HTMX fragments, e.g. health_cards.html
  static/
    htmx.min.js      vendored, pinned version noted in the file header
    console.css
```

`mount_console(app)` is called at the end of `src/ad_seller/interfaces/api/main.py`, guarded by `settings.console_enabled`. It registers the router and the static mount. With the flag off the app has no console routes, no static mount, and no console imports at request time.

The CLI gains `ad-seller create-console-user`, next to the existing `create-operator-key` command, with `--username`, a password prompt, and `--disable` to disable an account.

### Import rule

The console package imports from: its own modules, FastAPI and Starlette, Jinja2, httpx, `ad_seller.config`, and one adapter in `auth.py` that wraps the generic key-value storage interface (`get`, `set`, `delete`, TTL). It never imports `ad_seller.services`, `crews`, `agents`, `engines`, `flows`, `tools`, or `models`. Wire shapes come from API JSON. A unit test enforces this by walking the package's import statements. The rule is what keeps the extraction path open by construction.

### New API route

`GET /auth/api-keys/me` returns the calling key's metadata (`ApiKeyInfo`, no secret) for any valid key. Without it the only way to learn "who am I" is to list every key and match a twelve-character prefix that starts with a fixed string. This route is delivered as its own commit and its own upstream PR.

## 4. Accounts, sessions, and the console key

### Accounts

Record `console_user:<username>` in the key-value store:

```
{ "username": str, "password_hash": str, "salt": str, "role": "operator",
  "disabled": bool, "created_at": iso8601, "last_login_at": iso8601 | null }
```

Passwords are hashed with `hashlib.scrypt` (standard library; n=2**14, r=8, p=1, 16-byte random salt) and compared with `hmac.compare_digest`. Minimum length twelve characters, enforced by the CLI. Passwords are never logged. `role` is fixed to `operator` in the Foundation and exists so later roles need no migration.

Accounts are created, reset, and disabled only through the CLI on the host. There are no account management routes.

### Login

`GET /console/login` renders the form and sets a pre-login cookie with a random CSRF value. `POST /console/login` requires the form field to equal the cookie value, then:

1. Rate limit check: at most five failures per username and per client address in ten minutes, tracked in the store with a ten-minute TTL. Exceeded gives 429 and a message with the wait time.
2. Account lookup and hash comparison, always taking the same code path so timing does not reveal whether the username exists.
3. Failure: one generic message for wrong username, wrong password, and disabled account, after a fixed 300 ms delay.
4. Success: create a session, set the cookie, redirect to the requested path or `/console/`.

### Sessions

Record `console_session:<token>` with `{ "username", "role", "created_at" }`, written with the store's TTL set to `console_session_ttl_hours` (default 12). The token is `secrets.token_urlsafe(32)`. The cookie `console_session` holds only the token and is HTTP-only, SameSite Lax, path `/console`, and Secure when the request scheme is https. A new token is issued on every login. Logout deletes the record and clears the cookie.

The record never holds a key or a password.

### current_operator

The only place that knows about cookies and headers. Returns `Operator(username, role)`.

- If `console_trusted_identity_header` is set and present on the request: look up the account by that value; missing account gives 403 with a plain page. No cookie is involved and the login routes redirect to `/console/`.
- Otherwise read the cookie, load the session, and return the operator. Missing or expired session: redirect to `/console/login?next=<path>` for page requests; for HTMX requests (header `HX-Request`), respond 401 with `HX-Redirect` set to the login URL.

Every console route depends on it except login, logout, and static files.

### The console key

`console_operator_api_key` is read once at mount time. At application startup (the existing lifespan, since mounting happens at import time and cannot await), the console calls the `me` route in-process with it and fails startup, with one clear log line, if the key is missing, invalid, or not an operator key. The key is used on every API call and never stored anywhere else. Revoking it through the API ends all console access; sessions remain but every page shows the rejected-key state until the key is replaced.

## 5. Pages

Both pages use the shell from the v2 wireframes: a left sidebar with the six screens (Inbox, Orders, Deals, Negotiation, Catalog, Setup), count badges where the screen exists, unbuilt screens rendered disabled with a "soon" tag. The top bar shows the console name, the signed-in username, and sign out.

### Login `/console/login`

One card: username, password, generic error strip, sign-in button, and a help line naming the CLI command. When the trusted identity header is configured the page redirects to `/console/`.

### Landing `/console/`

Title "Setup and health", Setup active in the sidebar. Four cards:

| Card | Source routes | Shows |
|---|---|---|
| Agent | `GET /health`, `GET /` | health status, API name and version, time of check |
| Console access | `GET /auth/api-keys/me` | username, session time left, console key label, id, active or revoked, expiry |
| Inventory sync | `GET /api/v1/inventory-sync/status` | enabled or disabled, last run, watermark when present |
| Event bus | `GET /events?limit=1` | enabled state from settings, last event type and age |

The cards live in a partial, `GET /console/partials/health`, which HTMX polls every 30 seconds (`hx-trigger="every 30s"`). The page has no JavaScript of its own.

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

The wordmark is rendered as text. Whether the console ships the IAB logo image is a maintainer decision when the console goes upstream; the template keeps the logo slot as one include so it can be swapped.

## 6. API client and data flow

`client.py` defines `ConsoleApi`, built once in `mount_console` with the app and the console key. It uses `httpx.AsyncClient` with `ASGITransport(app=app)`, so a call goes through the real REST router in-process: same dependencies, same handlers, same JSON, no socket. Every request carries `Authorization: Bearer <console key>` and `X-Console-User: <username>`.

Foundation methods: `me()`, `health()` (health plus root, for the version), `inventory_sync_status()`, `last_event()`. Each returns the parsed JSON body as a dict, or raises `ApiUnavailable(status, detail)` for 5xx, timeouts, and non-JSON bodies, and `ApiRejected(status)` for 401 and 403. Nothing outside `client.py` imports httpx.

Client rules: never follow redirects; two-second timeout per call; no retries (the poll is the retry).

Page request flow:

1. Browser requests `/console/`; `current_operator` resolves the session.
2. The route calls the client methods it needs, concurrently with `asyncio.gather` where they are independent.
3. The route renders the template with the dicts. Templates use only what the API returned.
4. HTMX polls the partial route, which reuses the same template fragment without the shell.

## 7. Error handling

| Condition | Behaviour |
|---|---|
| API 401 on the console key | Console access card shows "console key rejected" in the error color; other cards render; page is 200. Sessions are kept. |
| API 403 on the console key | Same, with "console key is not an operator key". |
| API 5xx, timeout, non-JSON | That card shows "unavailable", the status, and the time; the next poll retries. Never a stack trace. |
| Session missing or expired | Redirect to login with `next`; `HX-Redirect` for HTMX requests. |
| Login failure | Generic message, fixed delay. Rate limit exceeded: 429 with the wait time. |
| Console misconfigured at startup | The startup check logs one line and raises; the app does not start with the console enabled but unusable. Flag off: none of this runs. |
| Unexpected exception in a console route | A router-level handler renders a plain error page with a request id and logs the traceback. Log lines never contain the console key, a session token, or a password; a test checks this. |

## 8. Testing

All tests are pytest under `tests/unit/console/`, using the FastAPI TestClient against the real app with the console flag on. No browser automation.

- **Real storage.** SQLite backend on a temporary path. Accounts are created through the CLI function.
- **Real API.** The in-process client hits the real routes. The console key is minted in the test through the API key service.
- **Failures forced at the boundary.** Revoked key by revoking it through the API. Timeouts and 5xx by overriding one route's dependency to sleep or raise.
- **HTML assertions** through a small helper on the standard library HTML parser, finding elements by id and data attributes only.
- **Security tests**: cookie flags; token rotation on login; logout deletes the record; CSRF token required; rate limit trips on the sixth failure and clears after the TTL; no secret substring in logs captured on login and error paths.
- **Structural tests**: the import rule; the OpenAPI drift test extended by the `me` route.
- **Revert checks.** Each implementation task names the test that goes red when its change is reverted.

## 9. Configuration, deployment, documentation

Settings (environment names in capitals):

| Setting | Default | Meaning |
|---|---|---|
| `console_enabled` | `false` | mount the console |
| `console_operator_api_key` | none | required when enabled |
| `console_session_ttl_hours` | `12` | session lifetime |
| `console_trusted_identity_header` | empty | when set, SSO mode: this header names the user |

No signing secret is needed: session tokens are random and the CSRF check is a cookie-to-form comparison.

Deployment does not change. Same image, same compose file; the two new variables appear commented out in the compose example. HTMX is vendored, so no build step and no CDN.

Documentation: a new guide `docs/guides/console.md` (enable, mint the console key, create a user, SSO header), a row for the `me` route in the endpoints reference, a regenerated `docs/api/openapi.json`, and CHANGELOG entries under Unreleased.

## 10. Delivery

Small pull requests into `ui/dev` on the fork, each green on its own:

1. `GET /auth/api-keys/me` with test and docs. Also opened upstream.
2. Console package: flag, client, accounts, CLI command, login, logout, empty shell.
3. Landing page cards and the polling partial.
4. Guide and compose example.

## 11. Growth path

- **Attribution in the API**: a backend change records `X-Console-User` on audit and order events when the caller is an operator key. Same shape as trusting a proxy header, so one change covers both.
- **Roles**: the account `role` field gains values and routes check it; the API still sees one key.
- **Per-user keys**: only if the API itself must enforce roles; added behind `current_operator` without touching screens.
- **SSO**: set the trusted header and put a proxy in front; the account records become the profile table keyed by the header value.
- **Extraction**: the console only speaks HTTP to the API, so moving it to its own service is a base URL change plus a session store.

## 12. Out of scope for the Foundation

Every real screen; roles beyond `operator`; per-user API keys; the proxy container; the backend attribution change; the IAB logo image; a dark theme.
