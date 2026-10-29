"""Data models and mock customer store for the MCP server."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CustomerOverview(BaseModel):
    customer_id: str
    name: str
    tier: str
    account_status: str
    current_balance_usd: float
    current_transaction_limit_usd: float
    email: str


class TransactionRecord(BaseModel):
    transaction_id: str
    customer_id: str
    date: str
    amount_usd: float
    merchant: str
    status: str


class WireTransferResult(BaseModel):
    transfer_id: str
    customer_id: str
    recipient_name: str
    recipient_account: str
    amount_usd: float
    status: str
    timestamp: str
    memo: Optional[str] = None



# In-memory mock customer database
MOCK_CUSTOMERS: Dict[str, CustomerOverview] = {
    "CUST-1001": CustomerOverview(
        customer_id="CUST-1001",
        name="Jane Doe",
        tier="Premier",
        account_status="ACTIVE",
        current_balance_usd=4520.50,
        current_transaction_limit_usd=5000.00,
        email="jane.doe@example.com",
    ),
    "CUST-1002": CustomerOverview(
        customer_id="CUST-1002",
        name="Acme Corp (Rep: John Smith)",
        tier="Enterprise",
        account_status="ACTIVE",
        current_balance_usd=128450.00,
        current_transaction_limit_usd=20000.00,
        email="finance@acmecorp.example.com",
    ),
    "CUST-1003": CustomerOverview(
        customer_id="CUST-1003",
        name="Suspended Account (Alex Vance)",
        tier="Standard",
        account_status="SUSPENDED_LEGAL_HOLD",
        current_balance_usd=14.20,
        current_transaction_limit_usd=500.00,
        email="alex.vance@example.com",
    ),
}


MOCK_TRANSACTIONS: Dict[str, List[TransactionRecord]] = {
    "CUST-1001": [
        TransactionRecord(
            transaction_id="TXN-9011",
            customer_id="CUST-1001",
            date="2026-09-08",
            amount_usd=145.20,
            merchant="Organic Market",
            status="SETTLED",
        ),
        TransactionRecord(
            transaction_id="TXN-9012",
            customer_id="CUST-1001",
            date="2026-09-09",
            amount_usd=1200.00,
            merchant="Aero Travel Agency",
            status="SETTLED",
        ),
    ],
    "CUST-1002": [
        TransactionRecord(
            transaction_id="TXN-8010",
            customer_id="CUST-1002",
            date="2026-09-07",
            amount_usd=15400.00,
            merchant="Cloud Infrastructure Services",
            status="SETTLED",
        ),
    ],
    "CUST-1003": [
        TransactionRecord(
            transaction_id="TXN-7001",
            customer_id="CUST-1003",
            date="2026-09-01",
            amount_usd=500.00,
            merchant="Suspicious Crypto Exchange",
            status="HELD_FOR_REVIEW",
        ),
    ],
}
