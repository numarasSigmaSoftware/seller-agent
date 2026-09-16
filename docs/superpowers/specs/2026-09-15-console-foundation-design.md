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
| How the console reads data | Through the REST API over an injected HTTP transport, in-process today, with an operator key on every call | The API stays the only contract. Every gap the console hits is an API gap. Extraction into a separate service later swaps the transport and the base URL; paths and cookies already follow the mount prefix. |
| Who logs in | Console accounts with username and password, created on the host by CLI | Every publisher can run it on day one. No identity provider required. |
| What the API sees | One operator key held by the server, labelled `console`, plus an `X-Console-User` header naming the person | Keys never reach the browser. Revoking one key ends all console access. The header is display context for logs, chosen by the caller and not verified by the API; it is not attribution. |
| Single sign-on | A configured trusted identity header, accepted only from configured proxy networks, replaces the password login when set | Publishers with SSO put a proxy in front. In that mode the header is required on every request, cookies are never consulted, and the password endpoints are off. Nothing in the screens changes. |
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

The console package imports from: its own modules, FastAPI and Starlette, Jinja2, httpx, `ad_seller.config`, and one seam in `accounts.py` that wraps the generic key-value storage interface (`get`, `set`, `delete`, `keys`, TTL). Every other `ad_seller` module is forbidden: `services`, `crews`, `agents`, `engines`, `flows`, `tools`, `models`, `auth`, `events`, and the API package. Wire shapes come from API JSON validated into console-owned models. A unit test enforces this as an allowlist, resolving relative imports to absolute names so `from ...services import x` is caught. The rule is what keeps the extraction path open by construction.

Paths are never hardcoded: templates, redirects, and cookie paths derive from the mount's `root_path`, so the console works under `/console` and under a proxy prefix such as `/agent/console` without change.

### New API route

`GET /auth/api-keys/me` returns the calling key's metadata (`ApiKeyInfo`, no secret) for any valid key. Without it the only way to learn "who am I" is to list every key and match a twelve-character prefix that starts with a fixed string. This route is delivered as its own commit and its own upstream PR.

## 4. Accounts, sessions, and the console key

### Accounts

Record `console_user:<username>` in the key-value store:

```
{ "username": str, "password_hash": "scrypt$17$8$1$<salt hex>$<hash hex>", "role": "operator",
  "disabled": bool, "created_at": iso8601, "last_login_at": iso8601 | null,
  "credentials_changed_at": iso8601 }
```

`credentials_changed_at` is bumped by every disable, password reset, and later role change. It is what revokes sessions (below).

Passwords are hashed with `hashlib.scrypt` from the standard library at the OWASP minimum, N=2^17, r=8, p=1, with a 16-byte random salt, and compared with `hmac.compare_digest`. The stored string is self-describing (`scrypt$17$8$1$salt$hash`), so when the parameters are raised later, an account hashed with weaker ones is verified and rehashed in place on its next successful login, with no migration and without invalidating its sessions. Minimum length twelve characters, enforced by the CLI. Passwords are never logged. `role` is fixed to `operator` in the Foundation and exists so later roles need no migration.

Accounts are created, reset, and disabled only through the CLI on the host. There are no account management routes.

### Login

CSRF is one policy, not per-route checks: every page the console renders issues (or re-issues) an HTTP-only `console_csrf` cookie and embeds the same random value in its forms, in password and SSO mode alike; a single `require_csrf` dependency on every POST route compares the form field with the cookie in constant time and answers 400 otherwise, and a test asserts every POST route carries it. `POST /console/login` then:

1. Rate limit check: at most five failures per username and per client address in ten minutes. Each failure is its own key with a ten-minute TTL under the `rate_limit:` prefix, and the count is the number of live keys, so concurrent failures are never lost to a read-modify-write and expiry belongs to the store. Exceeded gives 429 and a message with the wait time.
2. Account lookup and hash comparison, always taking the same code path so timing does not reveal whether the username exists.
3. Failure: one generic message for wrong username, wrong password, and disabled account, after a fixed 300 ms delay.
4. Success: create a session, set the cookie, redirect to the requested path or `/console/`.

### Sessions

Record `session:console:<token>` with `{ "username", "role", "created_at", "expires_at" }`, written with the store's TTL set to `console_session_ttl_hours` (default 12). The `session:` and `rate_limit:` prefixes are the ones the hybrid backend already routes to Redis, so on that backend console sessions and failure counters land in the ephemeral store without a change to the router. The token is `secrets.token_urlsafe(32)`. The cookie `console_session` holds only the token and is HTTP-only, SameSite Lax, path `/console`, and Secure when the request scheme is https. A new token is issued on every login. Logout deletes the record and clears the cookie.

The record never holds a key or a password.

A session is only a pointer to an account, not a snapshot of it. On every request `current_operator` rereads the account: a missing or disabled account, or a session created before the account's `credentials_changed_at`, kills the session on the spot. Disabling an account or resetting its password therefore ends its sessions immediately, not at the TTL. The same mechanism carries future role changes.

### current_operator

The only place that knows about cookies and headers. Returns `Operator(username, role)`.

- SSO mode (`console_trusted_identity_header` set): the request's client address must be inside `console_trusted_proxy_cidrs`, else 403; the header must be present, else 403; the account it names must exist and be enabled, else 403. Cookies are never consulted in this mode, so a password session cannot substitute for the header, and the login and logout endpoints answer 404. The app refuses to start in SSO mode without the proxy networks.
- Password mode: read the cookie, load the session, reread the account, and return the operator with the account's current role. Missing or expired session, or a session invalidated by an account change: redirect to `/console/login?next=<path>` for page requests; for HTMX requests (header `HX-Request`), respond 401 with `HX-Redirect` set to the login URL.

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
| Event bus | `GET /events` | last event type and time, or "no events yet"; only what the API returns, never local settings |

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

`client.py` defines `ConsoleApi`, built once in `mount_console` with an httpx transport, a base URL, and the console key. Today the transport is `ASGITransport(app=app)`, so a call goes through the real REST router in-process: same dependencies, same handlers, same JSON, no socket. A network deployment passes an HTTP transport and the API's URL; only `mount_console` knows which. Every request carries `Authorization: Bearer <console key>` and `X-Console-User: <username>`.

Foundation methods: `me()`, `health()` (health plus root, for the version), `inventory_sync_status()`, `last_event()`. Each validates the JSON body into a console-owned model (`KeyInfo`, `Health`, `SyncStatus`, `EventSummary`; unknown fields ignored) and returns it, or raises `ApiUnavailable(status, detail)` for any non-2xx status other than 401 and 403, for timeouts, for non-JSON bodies, and for bodies that do not fit the model, and `ApiRejected(status)` for 401 and 403. A changed or malformed field therefore degrades one card and can never reach a template. Nothing outside `client.py` imports httpx.

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
| API 4xx other than 401/403, 5xx, timeout, non-JSON, or a body that does not fit the console's model | That card shows "unavailable", the status, and the reason; the next poll retries. Never a stack trace. |
| Session missing or expired | Redirect to login with `next`; `HX-Redirect` for HTMX requests. |
| Login failure | Generic message, fixed delay. Rate limit exceeded: 429 with the wait time. |
| Console misconfigured at startup | The startup check logs one line and raises; the app does not start with the console enabled but unusable. Flag off: none of this runs. |
| Unexpected exception in a console route | One exception handler registered on the console sub-application at build time renders a plain error page with a request id and logs the traceback; `HTTPException` keeps its normal handling. Log lines never contain the console key, a session token, or a password; a test checks this. |

## 8. Testing

All tests are pytest under `tests/unit/console/`, using the FastAPI TestClient against the real app with the console flag on. No browser automation.

- **Real storage.** SQLite backend on a temporary path. Accounts are created through the CLI function.
- **Real API.** The in-process client hits the real routes. The console key is minted in the test through the API key service.
- **Failures forced at the boundary.** Revoked key by revoking it through the API. Timeouts and 5xx by overriding one route's dependency to sleep or raise.
- **HTML assertions** through a small helper on the standard library HTML parser, finding elements by id and data attributes only.
- **Security tests**: cookie flags; token rotation on login; logout deletes the record; CSRF token required; rate limit trips on the sixth failure and clears after the TTL; no secret substring in logs captured on login and error paths.
- **Structural tests**: the import rule; the OpenAPI drift test extended by the `me` route.
- **Revert checks.** Each implementation task names the test that goes red when its change is reverted.
- **Not covered in the Foundation.** The console tests run on SQLite. Running the session and rate-limit tests against the Redis and Postgres backends of the hybrid store needs those services in the test run and is a follow-up alongside the existing integration suite.

## 9. Configuration, deployment, documentation

Settings (environment names in capitals):

| Setting | Default | Meaning |
|---|---|---|
| `console_enabled` | `false` | mount the console |
| `console_operator_api_key` | none | required when enabled |
| `console_session_ttl_hours` | `12` | session lifetime |
| `console_trusted_identity_header` | empty | when set, SSO mode: this header names the user, required on every request |
| `console_trusted_proxy_cidrs` | empty | networks the header is trusted from; required in SSO mode |

No signing secret is needed: session tokens are random and the CSRF check is a cookie-to-form comparison enforced by one dependency on every POST route.

Deployment does not change. Same image, same compose file; the two new variables appear commented out in the compose example. HTMX is vendored, so no build step and no CDN.

Documentation: a new guide `docs/guides/console.md` (enable, mint the console key, create a user, SSO header), a row for the `me` route in the endpoints reference, a regenerated `docs/api/openapi.json`, and CHANGELOG entries under Unreleased.

## 10. Delivery

Small pull requests into `ui/dev` on the fork, each green on its own:

1. `GET /auth/api-keys/me` with test and docs. Also opened upstream.
2. Console package: flag, client, accounts, CLI command, login, logout, empty shell.
3. Landing page cards and the polling partial.
4. Guide and compose example.

## 11. Growth path

- **Attribution in the API**: `X-Console-User` is context, not attribution, because whoever holds any operator key can set it. Before the console performs mutations, before audit records name a person, and before roles are enforced, the API must receive something it can verify: either a per-user delegated credential, or an actor assertion signed with a secret bound to the console key and checked by the API. The API, not the console's routes, enforces authorization at that point. Recording the bare header on audit events is acceptable only as a "claimed by" field next to the key id that actually authenticated.
- **Roles**: the account `role` field gains values and routes check it; a role change bumps `credentials_changed_at`, so open sessions pick it up at once. The API still sees one key.
- **Per-user keys**: only if the API itself must enforce roles; added behind `current_operator` without touching screens.
- **SSO**: set the trusted header and the proxy networks and put a proxy in front; the account records become the profile table keyed by the header value. A later step replaces the bare header with a signed, audience-bound assertion from the proxy (for example the JWT oauth2-proxy can forward), verified against the identity provider's keys; that needs a JWT library and an identity-provider contract, so it is not in the Foundation.
- **Extraction**: the console only speaks HTTP to the API through an injected transport, its paths follow the mount, and it reads no agent settings for page content, so moving it to its own service is a transport and base URL change plus a session store.

## 12. Out of scope for the Foundation

Every real screen; roles beyond `operator`; per-user API keys; the proxy container; the backend attribution change; the IAB logo image; a dark theme.
