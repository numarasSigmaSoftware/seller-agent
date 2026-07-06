"""Seller-owned browser UI and API explorer routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from starlette.routing import Route

_UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ad Seller System</title>
  <link rel="stylesheet" href="/ui/assets/app.css">
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Seller Console</p>
      <h1>Ad Seller System</h1>
    </div>
    <nav aria-label="Primary">
      <a href="/docs">Docs</a>
      <a href="/openapi.json">OpenAPI</a>
      <a href="/health">Health</a>
    </nav>
  </header>

  <main>
    <section class="overview" aria-label="Overview">
      <article>
        <span class="label">Health</span>
        <strong id="health-status">Checking</strong>
      </article>
      <article>
        <span class="label">Version</span>
        <strong id="api-version">-</strong>
      </article>
      <article>
        <span class="label">Endpoints</span>
        <strong id="endpoint-count">-</strong>
      </article>
      <article>
        <span class="label">Updated</span>
        <strong id="overview-time">-</strong>
      </article>
    </section>

    <section class="workspace" aria-label="API Explorer">
      <aside class="endpoint-panel">
        <div class="panel-head">
          <h2>API Explorer</h2>
          <input id="endpoint-filter" type="search" placeholder="Filter endpoints" aria-label="Filter endpoints">
        </div>
        <div id="endpoint-list" class="endpoint-list" aria-live="polite"></div>
      </aside>

      <section class="request-panel" aria-label="Request">
        <form id="request-form">
          <div class="request-line">
            <select id="request-method" aria-label="HTTP method"></select>
            <input id="request-path" aria-label="Request path" spellcheck="false">
            <button type="submit">Send</button>
          </div>
          <label>
            <span>Authorization</span>
            <input id="request-auth" placeholder="Bearer token or API key" autocomplete="off">
          </label>
          <label>
            <span>Request JSON</span>
            <textarea id="request-body" spellcheck="false" rows="10"></textarea>
          </label>
        </form>
        <div class="response-head">
          <h2>Response</h2>
          <span id="response-status">Idle</span>
        </div>
        <pre id="response-body">{}</pre>
      </section>
    </section>
  </main>

  <script src="/ui/assets/app.js"></script>
</body>
</html>
"""


_UI_CSS = """
:root {
  color-scheme: light;
  --ink: #172026;
  --muted: #5f6972;
  --line: #d7dde2;
  --surface: #ffffff;
  --band: #f5f7f8;
  --accent: #0f766e;
  --accent-strong: #115e59;
  --warn: #9a3412;
  --info: #1d4ed8;
  --shadow: 0 10px 30px rgba(23, 32, 38, 0.08);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: var(--band);
  color: var(--ink);
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 96px;
  padding: 20px clamp(18px, 4vw, 48px);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}

.eyebrow,
.label,
label span {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: clamp(28px, 4vw, 42px);
  line-height: 1.05;
}

h2 {
  font-size: 18px;
}

nav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

nav a,
button,
.endpoint-button {
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
}

nav a {
  padding: 9px 12px;
}

button {
  padding: 0 18px;
  background: var(--accent);
  border-color: var(--accent);
  color: #ffffff;
}

button:hover,
button:focus-visible {
  background: var(--accent-strong);
}

main {
  width: min(1440px, 100%);
  margin: 0 auto;
  padding: 18px clamp(14px, 3vw, 32px) 32px;
}

.overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.overview article,
.endpoint-panel,
.request-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}

.overview article {
  min-height: 88px;
  padding: 18px;
}

.overview strong {
  display: block;
  overflow-wrap: anywhere;
  font-size: 22px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.endpoint-panel,
.request-panel {
  min-height: 620px;
}

.panel-head,
.response-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid var(--line);
}

input,
select,
textarea,
pre {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #fbfcfd;
  color: var(--ink);
  font: 14px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

input,
select {
  min-height: 42px;
  padding: 0 12px;
}

textarea {
  resize: vertical;
  padding: 12px;
}

#endpoint-filter {
  max-width: 220px;
  font-family: inherit;
}

.endpoint-list {
  display: grid;
  gap: 8px;
  max-height: 558px;
  overflow: auto;
  padding: 12px;
}

.endpoint-button {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  min-height: 48px;
  padding: 10px;
  text-align: left;
}

.endpoint-button[aria-pressed="true"] {
  border-color: var(--accent);
  background: #ecfdf5;
}

.method {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 58px;
  min-height: 26px;
  border-radius: 4px;
  background: #e0f2fe;
  color: var(--info);
  font-size: 12px;
  font-weight: 800;
}

.method.post,
.method.put,
.method.delete {
  background: #ffedd5;
  color: var(--warn);
}

.endpoint-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 700;
}

.endpoint-path {
  overflow-wrap: anywhere;
  color: var(--muted);
  font-size: 12px;
}

.request-panel {
  padding-bottom: 16px;
}

form {
  display: grid;
  gap: 14px;
  padding: 16px;
}

.request-line {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) 104px;
  gap: 10px;
}

pre {
  min-height: 240px;
  max-height: 420px;
  overflow: auto;
  margin: 16px;
  padding: 16px;
  white-space: pre-wrap;
}

#response-status {
  min-width: 92px;
  text-align: right;
  color: var(--muted);
  font-weight: 700;
}

@media (max-width: 920px) {
  .topbar,
  .panel-head,
  .response-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .overview,
  .workspace,
  .request-line {
    grid-template-columns: 1fr;
  }

  #endpoint-filter {
    max-width: none;
  }
}
"""


_UI_JS = """
const state = {
  endpoints: [],
  selectedKey: "",
};

const methodOrder = ["GET", "POST", "PUT", "PATCH", "DELETE"];

function $(id) {
  return document.getElementById(id);
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function setResponse(status, body) {
  $("response-status").textContent = status;
  $("response-body").textContent = typeof body === "string" ? body : pretty(body);
}

function operationTitle(operation, method, path) {
  return operation.summary || operation.operationId || `${method} ${path}`;
}

function requestTemplate(operation) {
  const schema = operation.requestBody?.content?.["application/json"]?.schema;
  if (!schema || !schema.properties) {
    return "";
  }
  const body = {};
  for (const [key, value] of Object.entries(schema.properties)) {
    if (value.default !== undefined) {
      body[key] = value.default;
    } else if (value.type === "number" || value.type === "integer") {
      body[key] = 0;
    } else if (value.type === "boolean") {
      body[key] = false;
    } else if (value.type === "array") {
      body[key] = [];
    } else if (value.type === "object") {
      body[key] = {};
    } else {
      body[key] = "";
    }
  }
  return pretty(body);
}

function normalizePath(path) {
  return path.replaceAll("{", ":").replaceAll("}", "");
}

function selectEndpoint(endpoint) {
  state.selectedKey = endpoint.key;
  $("request-method").value = endpoint.method;
  $("request-path").value = normalizePath(endpoint.path);
  $("request-body").value = requestTemplate(endpoint.operation);
  renderEndpoints();
}

function renderEndpoints() {
  const filter = $("endpoint-filter").value.trim().toLowerCase();
  const list = $("endpoint-list");
  list.innerHTML = "";
  const visible = state.endpoints.filter((endpoint) => {
    const haystack = `${endpoint.method} ${endpoint.path} ${endpoint.title} ${endpoint.tags.join(" ")}`.toLowerCase();
    return !filter || haystack.includes(filter);
  });

  for (const endpoint of visible) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "endpoint-button";
    button.setAttribute("aria-pressed", endpoint.key === state.selectedKey ? "true" : "false");
    button.innerHTML = `
      <span class="method ${endpoint.method.toLowerCase()}">${endpoint.method}</span>
      <span>
        <span class="endpoint-title">${endpoint.title}</span>
        <span class="endpoint-path">${endpoint.path}</span>
      </span>
    `;
    button.addEventListener("click", () => selectEndpoint(endpoint));
    list.appendChild(button);
  }

  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "endpoint-path";
    empty.textContent = "No endpoints";
    list.appendChild(empty);
  }
}

async function loadOverview() {
  const [healthResponse, overviewResponse] = await Promise.all([
    fetch("/health"),
    fetch("/ui/overview"),
  ]);
  const health = await healthResponse.json();
  const overview = await overviewResponse.json();
  $("health-status").textContent = health.status || "unknown";
  $("api-version").textContent = overview.version;
  $("endpoint-count").textContent = String(overview.endpoint_count);
  $("overview-time").textContent = new Date(overview.generated_at).toLocaleTimeString();
}

async function loadOpenApi() {
  const response = await fetch("/openapi.json");
  const schema = await response.json();
  $("request-method").innerHTML = methodOrder.map((method) => `<option>${method}</option>`).join("");
  state.endpoints = Object.entries(schema.paths || {}).flatMap(([path, operations]) => (
    Object.entries(operations)
      .filter(([method]) => methodOrder.includes(method.toUpperCase()))
      .map(([method, operation]) => ({
        key: `${method.toUpperCase()} ${path}`,
        method: method.toUpperCase(),
        path,
        title: operationTitle(operation, method.toUpperCase(), path),
        tags: operation.tags || [],
        operation,
      }))
  )).sort((a, b) => a.path.localeCompare(b.path) || methodOrder.indexOf(a.method) - methodOrder.indexOf(b.method));
  renderEndpoints();
  const firstGet = state.endpoints.find((endpoint) => endpoint.method === "GET" && endpoint.path === "/health")
    || state.endpoints.find((endpoint) => endpoint.method === "GET")
    || state.endpoints[0];
  if (firstGet) {
    selectEndpoint(firstGet);
  }
}

async function submitRequest(event) {
  event.preventDefault();
  const method = $("request-method").value;
  const path = $("request-path").value || "/";
  const headers = {};
  const auth = $("request-auth").value.trim();
  const bodyText = $("request-body").value.trim();
  const options = { method, headers };

  if (auth) {
    headers.Authorization = auth.toLowerCase().startsWith("bearer ") ? auth : `Bearer ${auth}`;
  }
  if (method !== "GET" && method !== "DELETE" && bodyText) {
    headers["Content-Type"] = "application/json";
    try {
      options.body = JSON.stringify(JSON.parse(bodyText));
    } catch (error) {
      setResponse("Invalid JSON", error.message);
      return;
    }
  }

  setResponse("Sending", {});
  try {
    const response = await fetch(path, options);
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    setResponse(`${response.status} ${response.statusText}`, body);
  } catch (error) {
    setResponse("Network error", error.message);
  }
}

window.addEventListener("DOMContentLoaded", async () => {
  $("endpoint-filter").addEventListener("input", renderEndpoints);
  $("request-form").addEventListener("submit", submitRequest);
  await Promise.all([loadOverview(), loadOpenApi()]);
});
"""


def _iter_api_routes(app: FastAPI) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for route in app.routes:
        if not isinstance(route, Route):
            continue
        methods = sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        routes.append(
            {
                "path": route.path,
                "name": route.name,
                "methods": methods,
            }
        )
    return sorted(routes, key=lambda item: (item["path"], item["methods"]))


def _build_overview(app: FastAPI) -> dict[str, Any]:
    routes = _iter_api_routes(app)
    return {
        "name": app.title,
        "version": app.version,
        "status": "healthy",
        "ui_url": "/ui",
        "docs_url": app.docs_url,
        "openapi_url": app.openapi_url,
        "health_url": "/health",
        "endpoint_count": sum(len(route["methods"]) for route in routes),
        "routes": routes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def register_seller_ui(app: FastAPI) -> None:
    """Register the seller console and explorer routes on the provided app."""

    @app.get("/overview", tags=["Core"])
    @app.get("/ui/overview", tags=["Core"])
    async def seller_overview():
        return _build_overview(app)

    @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
    async def seller_ui():
        return HTMLResponse(_UI_HTML)

    @app.get("/ui/assets/app.css", include_in_schema=False)
    async def seller_ui_css():
        return Response(_UI_CSS, media_type="text/css")

    @app.get("/ui/assets/app.js", include_in_schema=False)
    async def seller_ui_js():
        return Response(_UI_JS, media_type="application/javascript")
