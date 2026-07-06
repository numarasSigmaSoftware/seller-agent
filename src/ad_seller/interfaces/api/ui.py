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

    <section class="workflow-board" aria-label="Seller workflows">
      <div class="workflow-head">
        <div>
          <p class="eyebrow">Workflow</p>
          <h2>Seller Operations</h2>
        </div>
        <div id="workflow-tabs" class="workflow-tabs" role="tablist" aria-label="Seller workflow areas"></div>
      </div>
      <div class="workflow-layout">
        <section class="workflow-summary" aria-label="Workflow summary">
          <div>
            <span class="label">Area</span>
            <h3 id="workflow-title">-</h3>
          </div>
          <p id="workflow-description">-</p>
          <dl id="workflow-metrics"></dl>
        </section>
        <section class="workflow-actions" aria-label="Workflow actions">
          <div class="panel-head compact">
            <h3>Actions</h3>
            <span id="workflow-count">0 routes</span>
          </div>
          <div id="workflow-action-list" class="workflow-action-list"></div>
        </section>
      </div>
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

h3 {
  margin: 0;
  font-size: 16px;
  letter-spacing: 0;
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
.workflow-board,
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

.workflow-board {
  margin-top: 16px;
}

.workflow-head {
  display: grid;
  grid-template-columns: minmax(180px, 260px) minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
  border-bottom: 1px solid var(--line);
}

.workflow-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.workflow-tab,
.action-button {
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.workflow-tab[aria-selected="true"] {
  border-color: var(--accent);
  background: #ccfbf1;
  color: var(--accent-strong);
}

.workflow-layout {
  display: grid;
  grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
}

.workflow-summary {
  display: grid;
  gap: 16px;
  align-content: start;
  padding-right: 16px;
  border-right: 1px solid var(--line);
}

.workflow-summary p {
  margin: 0;
  color: var(--muted);
  line-height: 1.5;
}

dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

dt {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

dd {
  margin: 2px 0 0;
  font-weight: 800;
}

.workflow-actions {
  min-width: 0;
}

.compact {
  padding: 0 0 12px;
  border-bottom: 0;
}

#workflow-count {
  color: var(--muted);
  font-weight: 700;
}

.workflow-action-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.action-button {
  display: grid;
  gap: 4px;
  min-height: 86px;
  text-align: left;
}

.action-button:hover,
.action-button:focus-visible {
  border-color: var(--accent);
  background: #f0fdfa;
}

.action-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-path {
  overflow-wrap: anywhere;
  color: var(--muted);
  font: 12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
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
  .workflow-head,
  .workflow-layout,
  .workspace,
  .request-line {
    grid-template-columns: 1fr;
  }

  .workflow-summary {
    padding-right: 0;
    border-right: 0;
    border-bottom: 1px solid var(--line);
    padding-bottom: 16px;
  }

  .workflow-action-list {
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
  workflowKey: "media-kit",
};

const methodOrder = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const workflows = [
  {
    key: "media-kit",
    label: "Media Kit",
    description: "Publish inventory positioning, public packages, and buyer-facing search entry points.",
    tags: ["Media Kit"],
    paths: ["/media-kit", "/media-kit/packages", "/media-kit/search"],
  },
  {
    key: "packages",
    label: "Packages",
    description: "Manage package catalog records, assemble custom bundles, and sync inventory-backed offerings.",
    tags: ["Packages"],
    paths: ["/packages", "/packages/assemble", "/packages/sync"],
  },
  {
    key: "pricing",
    label: "Pricing",
    description: "Quote product pricing, inspect rate cards, and update seller rate-card controls.",
    tags: ["Pricing", "Quotes"],
    paths: ["/pricing", "/api/v1/rate-card", "/api/v1/quotes"],
  },
  {
    key: "deals",
    label: "Deals",
    description: "Create deals, export or push them to platforms, and inspect buyer or SSP delivery state.",
    tags: ["Deals", "Deal Booking", "Bulk Operations"],
    paths: ["/deals", "/api/v1/deals", "/api/v1/deals/export", "/api/v1/deals/push"],
  },
  {
    key: "orders",
    label: "Orders",
    description: "Track booked orders through lifecycle transitions, history, reporting, and audit records.",
    tags: ["Orders", "Change Requests", "Audit"],
    paths: ["/api/v1/orders", "/api/v1/change-requests"],
  },
  {
    key: "approvals",
    label: "Approvals",
    description: "Review pending human approvals, decision actions, and paused workflow resumes.",
    tags: ["Approvals"],
    paths: ["/approvals"],
  },
  {
    key: "operations",
    label: "Operations",
    description: "Monitor health, events, inventory sync, supply-chain details, and agent registry state.",
    tags: ["Core", "Events", "Supply Chain", "Agent Registry"],
    paths: ["/health", "/events", "/api/v1/inventory-sync/status", "/api/v1/supply-chain"],
  },
];

const workflowTemplates = {
  "POST /pricing": {
    product_id: "premium_video",
    buyer_tier: "public",
    agency_id: "",
    advertiser_id: "",
    volume: 1000000,
  },
  "POST /media-kit/search": {
    query: "premium video for auto intenders",
    audience_segments: ["auto_intenders"],
    max_results: 5,
  },
  "POST /packages/assemble": {
    buyer_id: "buyer-123",
    objectives: ["awareness"],
    budget: 25000,
    constraints: {},
  },
  "POST /api/v1/quotes": {
    buyer_id: "buyer-123",
    product_id: "premium_video",
    budget: 50000,
    flight_start: "2026-08-01",
    flight_end: "2026-08-31",
  },
  "POST /api/v1/orders": {
    deal_id: "deal-123",
    buyer_id: "buyer-123",
    order_name: "August premium video",
  },
  "POST /api/v1/change-requests": {
    order_id: "order-123",
    requested_by: "seller",
    change_type: "budget",
    details: {},
  },
};

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
  const method = operation.__method;
  const path = operation.__path;
  const template = workflowTemplates[`${method} ${path}`];
  if (template) {
    return pretty(template);
  }
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

function workflowEndpoints(workflow) {
  return state.endpoints.filter((endpoint) => {
    const exactPath = workflow.paths.includes(endpoint.path);
    const familyPath = workflow.paths.some((path) => endpoint.path.startsWith(`${path}/`));
    const tagged = endpoint.tags.some((tag) => workflow.tags.includes(tag));
    return exactPath || familyPath || tagged;
  });
}

function renderWorkflowTabs() {
  const tabs = $("workflow-tabs");
  tabs.innerHTML = "";
  for (const workflow of workflows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "workflow-tab";
    button.id = `workflow-tab-${workflow.key}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", workflow.key === state.workflowKey ? "true" : "false");
    button.textContent = workflow.label;
    button.addEventListener("click", () => {
      state.workflowKey = workflow.key;
      renderWorkflow();
    });
    tabs.appendChild(button);
  }
}

function renderWorkflow() {
  renderWorkflowTabs();
  const workflow = workflows.find((item) => item.key === state.workflowKey) || workflows[0];
  const endpoints = workflowEndpoints(workflow);
  $("workflow-title").textContent = workflow.label;
  $("workflow-description").textContent = workflow.description;
  $("workflow-count").textContent = `${endpoints.length} routes`;
  $("workflow-metrics").innerHTML = `
    <div><dt>Read routes</dt><dd>${endpoints.filter((endpoint) => endpoint.method === "GET").length}</dd></div>
    <div><dt>Write routes</dt><dd>${endpoints.filter((endpoint) => endpoint.method !== "GET").length}</dd></div>
    <div><dt>Primary tag</dt><dd>${workflow.tags[0]}</dd></div>
    <div><dt>Explorer</dt><dd>Connected</dd></div>
  `;

  const list = $("workflow-action-list");
  list.innerHTML = "";
  for (const endpoint of endpoints.slice(0, 8)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "action-button";
    button.innerHTML = `
      <span class="method ${endpoint.method.toLowerCase()}">${endpoint.method}</span>
      <span class="action-title">${endpoint.title}</span>
      <span class="action-path">${endpoint.path}</span>
    `;
    button.addEventListener("click", () => {
      selectEndpoint(endpoint);
      $("request-path").focus();
    });
    list.appendChild(button);
  }
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
        operation: {...operation, __method: method.toUpperCase(), __path: path},
      }))
  )).sort((a, b) => a.path.localeCompare(b.path) || methodOrder.indexOf(a.method) - methodOrder.indexOf(b.method));
  renderEndpoints();
  renderWorkflow();
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
