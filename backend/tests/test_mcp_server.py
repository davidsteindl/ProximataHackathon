import json

import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app import mcp_server
from test_cad_pipeline import ENTRIES, upload
from test_rules import initialized, ingest, inspection_claim


@pytest.fixture
def api_transport(initialized, monkeypatch):
    real_client = httpx.AsyncClient
    requests = []

    def handle(request):
        requests.append(request)
        response = initialized.request(request.method, str(request.url), headers=dict(request.headers), content=request.content)
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)

    def factory(**kwargs):
        if kwargs.get("base_url") == "http://api:8000":
            kwargs["transport"] = httpx.MockTransport(handle)
        return real_client(**kwargs)

    monkeypatch.setenv("API_BASE_URL", "http://api:8000")
    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", factory)
    return requests


def protocol_run(scenario):
    async def run():
        server = mcp_server.create_server()
        app = server.streamable_http_app()
        async with server.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as transport:
                async with streamable_http_client("http://mcp/mcp", http_client=transport) as (read, write, _):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        await scenario(client)

    anyio.run(run)


def test_generic_mcp_client_discovers_tools_and_answers_3b(initialized, api_transport):
    evidence_id = inspection_claim(initialized)
    ingest(initialized)

    async def scenario(client):
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == {
            "list_zones", "get_zone_status", "list_flags", "get_flag", "get_timeline",
            "search_record", "get_zone_plan", "get_plan_diff", "create_proposal",
        }
        assert all(tool.description and tool.outputSchema for tool in tools)
        assert all(tool.annotations.readOnlyHint for tool in tools if tool.name != "create_proposal")
        status = await client.call_tool("get_zone_status", {"zone_id": "3B"})
        assert not status.isError
        data = status.structuredContent
        assert data["zone"]["id"] == "3B"
        assert any(task["id"] == "drywall-F3" for task in data["tasks"])
        assert data["open_flags"][0]["evaluation"] == "unknown"
        assert next(item for item in data["evidence"] if item["id"] == evidence_id)["review_status"] == "unconfirmed"
        assert data["source_refs"]
        flags = (await client.call_tool("list_flags", {})).structuredContent["flags"]
        flag = (await client.call_tool("get_flag", {"flag_id": flags[0]["id"]})).structuredContent["flag"]
        assert flag["sources"] and flag["audit"]
        text = json.dumps(flag)
        assert "sender_id" not in text and "source_key" not in text and "external_id" not in text
        assert "email" not in text and "notifications" not in text
        timeline = (await client.call_tool("get_timeline", {"zone_id": "3B"})).structuredContent
        assert timeline["entries"] and all(item["source_refs"] for item in timeline["entries"])
        search = (await client.call_tool("search_record", {"query": evidence_id})).structuredContent
        assert any(item["record"].get("review_status") == "unconfirmed" for item in search["entries"])
        assert (await client.call_tool("list_zones", {})).structuredContent["zones"]

    protocol_run(scenario)
    assert api_transport and all(request.headers["X-SiteMind-Client"] == "mcp" for request in api_transport)
    assert all(request.method == "GET" for request in api_transport)


def test_mcp_proposals_cannot_change_flags_or_evidence(initialized, api_transport):
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    before = {path: initialized.get(path).json() for path in ("/flags", "/evidence", "/tasks", "/outbox")}

    async def scenario(client):
        arguments = {"flag_id": flag["id"], "action": "Postpone drywall", "rationale": "Await confirmed inspection proof"}
        result = await client.call_tool("create_proposal", arguments)
        assert not result.isError and result.structuredContent["status"] == "proposed"
        assert result.structuredContent["source_refs"]
        for name in ("confirm_evidence", "reject_evidence", "close_flag", "approve_proposal", "execute_action"):
            assert (await client.call_tool(name, {})).isError
        assert (await client.call_tool("get_zone_status", {"zone_id": "../seed/import"})).isError
        assert (await client.call_tool("get_timeline", {"from_time": "2026-11-14T00:00:00"})).isError
        assert (await client.call_tool("search_record", {"query": "3B", "limit": 1000})).isError

    protocol_run(scenario)
    assert {path: initialized.get(path).json() for path in before} == before
    assert [request.url.path for request in api_transport if request.method == "POST"] == ["/agent/proposals"]


def test_mcp_geometry_and_diff_use_existing_api(initialized, api_transport):
    for entry in ENTRIES[2:4]:
        assert upload(initialized, entry).status_code == 200

    async def scenario(client):
        geometry = await client.call_tool("get_zone_plan", {"zone_id": "3B", "revision_id": "A-103-D"})
        assert not geometry.isError
        assert geometry.structuredContent["geometry"][0]["revision_id"] == "A-103-D"
        assert "revision:A-103-D" in geometry.structuredContent["source_refs"]
        diff = await client.call_tool("get_plan_diff", {"revision_id": "A-103-D"})
        assert not diff.isError
        assert diff.structuredContent["diff"]["affected_zone_ids"] == ["3B"]
        assert diff.structuredContent["source_refs"] == ["revision:A-103-C", "revision:A-103-D"]
        assert (await client.call_tool("get_plan_diff", {"revision_id": "A-103-C"})).isError
        assert (await client.call_tool("get_zone_status", {"zone_id": "missing"})).isError

    protocol_run(scenario)


def test_transport_errors_do_not_invent_an_answer(monkeypatch):
    real_client = httpx.AsyncClient

    def fail(request):
        raise httpx.ConnectError("secret infrastructure details", request=request)

    def factory(**kwargs):
        if "transport" not in kwargs:
            kwargs["transport"] = httpx.MockTransport(fail)
        return real_client(**kwargs)

    monkeypatch.setattr(mcp_server.httpx, "AsyncClient", factory)

    async def scenario(client):
        result = await client.call_tool("get_zone_status", {"zone_id": "3B"})
        assert result.isError
        assert "no clearance inferred" in result.content[0].text
        assert "secret" not in result.content[0].text

    protocol_run(scenario)
