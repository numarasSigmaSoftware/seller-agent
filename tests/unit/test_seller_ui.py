import httpx
import pytest
from httpx import ASGITransport

from ad_seller.interfaces.api.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_seller_ui_shell_serves_explorer(client):
    async with client as c:
        resp = await c.get("/ui")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Ad Seller System" in resp.text
    assert "API Explorer" in resp.text
    assert "Seller Operations" in resp.text
    assert "Seller workflow areas" in resp.text
    assert "/ui/assets/app.css" in resp.text
    assert "/ui/assets/app.js" in resp.text


@pytest.mark.parametrize("path", ["/overview", "/ui/overview"])
async def test_seller_overview_reports_health_and_routes(client, path):
    async with client as c:
        resp = await c.get(path)

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Ad Seller System API"
    assert body["status"] == "healthy"
    assert body["ui_url"] == "/ui"
    assert body["health_url"] == "/health"
    assert body["openapi_url"] == "/openapi.json"
    assert body["endpoint_count"] > 0
    assert any(route["path"] == "/health" and "GET" in route["methods"] for route in body["routes"])


async def test_seller_ui_assets_are_served(client):
    async with client as c:
        css_resp = await c.get("/ui/assets/app.css")
        js_resp = await c.get("/ui/assets/app.js")

    assert css_resp.status_code == 200
    assert "text/css" in css_resp.headers["content-type"]
    assert ".workspace" in css_resp.text
    assert js_resp.status_code == 200
    assert "application/javascript" in js_resp.headers["content-type"]
    assert "loadOpenApi" in js_resp.text
    assert "Media Kit" in js_resp.text
    assert "Packages" in js_resp.text
    assert "Pricing" in js_resp.text
    assert "Deals" in js_resp.text
    assert "Orders" in js_resp.text
    assert "Approvals" in js_resp.text
    assert "Operations" in js_resp.text
    assert "workflowTemplates" in js_resp.text
