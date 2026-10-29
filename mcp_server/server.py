"""Customer & Policy Demo MCP Server.

Provides tools for customer account lookup, transaction history, wire transfer execution,
and fraud prevention escalations. Deployed as a stateless Streamable HTTP service
on Google Cloud Run and intercepted by Agent Gateway with Semantic Governance.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List
import uuid

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.models import (
    MOCK_CUSTOMERS,
    MOCK_TRANSACTIONS,
    CustomerOverview,
    TransactionRecord,
    WireTransferResult,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Initialize FastMCP Server
mcp = FastMCP(
    name="customer-policy-mcp-service",
    instructions=(
        "Production MCP service for customer banking operations. "
        "Exposes customer overview, transactions, and wire transfer execution."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    stateless_http=True,
)


@mcp.tool()
async def get_customer_overview(customer_id: str) -> Dict[str, Any]:
    """Retrieve standard account overview and balance for a customer.

    Args:
        customer_id: Unique customer identifier (e.g., 'CUST-1001')
    """
    logger.info(f"Tool executed: get_customer_overview for {customer_id}")
    customer = MOCK_CUSTOMERS.get(customer_id)
    if not customer:
        raise ValueError(f"Customer '{customer_id}' not found in database.")
    return customer.model_dump()


@mcp.tool()
async def list_customer_transactions(customer_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Retrieve recent transaction history for a customer.

    Args:
        customer_id: Unique customer identifier (e.g., 'CUST-1001')
        limit: Maximum number of transactions to return (default: 5)
    """
    logger.info(f"Tool executed: list_customer_transactions for {customer_id} (limit={limit})")
    txns = MOCK_TRANSACTIONS.get(customer_id, [])
    return [txn.model_dump() for txn in txns[:limit]]


@mcp.tool()
async def initiate_wire_transfer(
    customer_id: str,
    recipient_name: str,
    recipient_account: str,
    amount_usd: float,
    memo: str = "Standard wire transfer",
) -> Dict[str, Any]:
    """Execute an outbound high-value wire transfer from customer funds.

    Note: In production with Semantic Governance enabled, this tool will be evaluated
    against enterprise fraud and coercion policies. It will be DENIED if there are indicators
    of extortion, elder fraud, third-party coaching, imposter scams, or artificial urgency.

    Args:
        customer_id: Unique customer identifier (e.g., 'CUST-1001')
        recipient_name: Full legal or commercial name of the receiving party
        recipient_account: Destination routing/IBAN or account number
        amount_usd: Total wire amount in USD (must be positive)
        memo: Purpose or reference memo for the wire transfer
    """
    logger.info(
        f"Tool executed: initiate_wire_transfer for {customer_id} -> ${amount_usd} "
        f"to '{recipient_name}' (acct: {recipient_account})"
    )
    customer = MOCK_CUSTOMERS.get(customer_id)
    if not customer:
        raise ValueError(f"Customer '{customer_id}' not found.")

    if amount_usd <= 0:
        raise ValueError("Wire transfer amount must be greater than $0.00.")

    if customer.current_balance_usd < amount_usd:
        raise ValueError(
            f"Insufficient funds: Customer balance is ${customer.current_balance_usd:,.2f}, "
            f"requested wire is ${amount_usd:,.2f}."
        )

    customer.current_balance_usd -= float(amount_usd)

    transfer_id = f"WIRE-{uuid.uuid4().hex[:8].upper()}"
    result = WireTransferResult(
        transfer_id=transfer_id,
        customer_id=customer_id,
        recipient_name=recipient_name,
        recipient_account=recipient_account,
        amount_usd=amount_usd,
        status="EXECUTED",
        timestamp=datetime.now(timezone.utc).isoformat(),
        memo=memo,
    )
    return result.model_dump()




# Create underlying ASGI application
async def health_check(request):
    return JSONResponse(
        {
            "status": "healthy",
            "service": "customer-policy-mcp-service",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def create_app() -> Starlette:
    """Build the production Starlette app combining FastMCP Streamable HTTP with health routes."""
    mcp_app = mcp.streamable_http_app()
    # Add health check routes
    mcp_app.routes.insert(0, Route("/", health_check, methods=["GET"]))
    mcp_app.routes.insert(0, Route("/healthz", health_check, methods=["GET"]))
    return mcp_app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
