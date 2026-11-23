"""
Tredence GCP FDE Program
Modules 13-14 | Hands-on 0.1 | Shared Utilities

Purpose
-------
Provide a single place for:
- Vertex AI / Gemini client construction.
- Model configuration.
- Deterministic mock enterprise data.
- Small read-only functions exposed as Gemini tools.

The data is intentionally local. The lab is about function-calling mechanics,
not database connectivity.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types


# ---------------------------------------------------------------------------
# Deterministic lab data
# ---------------------------------------------------------------------------
# Keeping the data in memory makes tool behavior predictable during teaching.
ORDERS = {
    "ORD-1001": {
        "order_id": "ORD-1001",
        "customer_id": "CUST-101",
        "sku": "SKU-LAPTOP-14",
        "status": "SHIPPED",
        "amount": 125000,
    },
    "ORD-1002": {
        "order_id": "ORD-1002",
        "customer_id": "CUST-102",
        "sku": "SKU-MONITOR-27",
        "status": "PROCESSING",
        "amount": 32000,
    },
}

CUSTOMERS = {
    "CUST-101": {
        "customer_id": "CUST-101",
        "name": "Aster Retail",
        "tier": "GOLD",
    },
    "CUST-102": {
        "customer_id": "CUST-102",
        "name": "Nova Foods",
        "tier": "STANDARD",
    },
}

INVENTORY = {
    "SKU-LAPTOP-14": {
        "sku": "SKU-LAPTOP-14",
        "available": 7,
    },
    "SKU-MONITOR-27": {
        "sku": "SKU-MONITOR-27",
        "available": 0,
    },
}


# ---------------------------------------------------------------------------
# Gemini / Vertex configuration
# ---------------------------------------------------------------------------
def client() -> genai.Client:
    """Create a Vertex-backed Google Gen AI client.

    Environment configuration is deliberately externalized so the same code can
    run against different Tredence training projects without source changes.
    """
    return genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        http_options=types.HttpOptions(api_version="v1"),
    )


def model_id() -> str:
    """Return the configured Gemini model identifier."""
    return os.getenv("MODEL_ID", "gemini-2.5-flash")


# ---------------------------------------------------------------------------
# Model-callable read tools
# ---------------------------------------------------------------------------
def get_order(order_id: str) -> dict:
    """Get one order by exact order ID. This operation is read-only."""
    order = ORDERS.get(order_id.upper())

    if order is None:
        return {
            "status": "error",
            "code": "ORDER_NOT_FOUND",
            "message": f"Order {order_id} does not exist.",
            "retryable": False,
        }

    return {
        "status": "success",
        "data": order,
    }


def get_customer(customer_id: str) -> dict:
    """Get one customer by exact customer ID. This operation is read-only."""
    customer = CUSTOMERS.get(customer_id.upper())

    if customer is None:
        return {
            "status": "error",
            "code": "CUSTOMER_NOT_FOUND",
            "message": f"Customer {customer_id} does not exist.",
            "retryable": False,
        }

    return {
        "status": "success",
        "data": customer,
    }


def get_inventory(sku: str) -> dict:
    """Get current inventory for one exact SKU. This operation is read-only."""
    inventory = INVENTORY.get(sku.upper())

    if inventory is None:
        return {
            "status": "error",
            "code": "SKU_NOT_FOUND",
            "message": f"SKU {sku} does not exist.",
            "retryable": False,
        }

    return {
        "status": "success",
        "data": inventory,
    }
