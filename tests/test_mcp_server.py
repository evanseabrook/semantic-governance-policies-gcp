"""Unit tests for the MCP server tools and health endpoints."""

import pytest
from starlette.testclient import TestClient

from mcp_server.server import (
    app,
    get_customer_overview,
    initiate_wire_transfer,
    list_customer_transactions,
)


@pytest.mark.asyncio
async def test_get_customer_overview_success():
    result = await get_customer_overview("CUST-1001")
    assert result["customer_id"] == "CUST-1001"
    assert result["name"] == "Jane Doe"
    assert result["account_status"] == "ACTIVE"
    assert result["current_balance_usd"] > 0


@pytest.mark.asyncio
async def test_get_customer_overview_not_found():
    with pytest.raises(ValueError, match="not found"):
        await get_customer_overview("CUST-NONEXISTENT")


@pytest.mark.asyncio
async def test_list_customer_transactions():
    txns = await list_customer_transactions("CUST-1001", limit=2)
    assert len(txns) <= 2
    assert all("transaction_id" in t for t in txns)


@pytest.mark.asyncio
async def test_initiate_wire_transfer_success():
    overview_before = await get_customer_overview("CUST-1001")
    initial_balance = overview_before["current_balance_usd"]

    wire_amount = 500.00
    res = await initiate_wire_transfer(
        customer_id="CUST-1001",
        recipient_name="Apex Roofing LLC",
        recipient_account="ROOF-998877",
        amount_usd=wire_amount,
        memo="Invoice #INV-2041 warehouse repairs",
    )
    assert res["status"] == "EXECUTED"
    assert res["amount_usd"] == wire_amount
    assert res["transfer_id"].startswith("WIRE-")

    overview_after = await get_customer_overview("CUST-1001")
    assert overview_after["current_balance_usd"] == initial_balance - wire_amount


@pytest.mark.asyncio
async def test_initiate_wire_transfer_insufficient_funds():
    with pytest.raises(ValueError, match="Insufficient funds"):
        await initiate_wire_transfer(
            customer_id="CUST-1003",
            recipient_name="Unicorn Ventures",
            recipient_account="UNI-1234",
            amount_usd=50000.00,
        )


def test_health_check_endpoint():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "customer-policy-mcp-service"


@pytest.mark.asyncio
async def test_extract_tool_specs_and_register_dry_run():
    from mcp_server.register import extract_tool_specs, register_mcp_server

    tool_specs = await extract_tool_specs()
    assert len(tool_specs) == 3
    tool_names = [t["name"] for t in tool_specs]
    assert "initiate_wire_transfer" in tool_names
    assert "get_customer_overview" in tool_names
    assert "list_customer_transactions" in tool_names

    result = register_mcp_server(
        project_id="test-project",
        location="us-central1",
        service_id="test-service",
        display_name="Test MCP Server",
        description="Test description",
        mcp_endpoint_url="https://example.com/mcp",
        tool_specs=tool_specs,
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["payload"]["displayName"] == "Test MCP Server"
    assert len(result["payload"]["mcpServerSpec"]["content"]["tools"]) == 3
