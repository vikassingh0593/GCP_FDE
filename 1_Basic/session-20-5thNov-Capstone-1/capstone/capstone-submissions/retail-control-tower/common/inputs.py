"""Input checks shared by every tool in both services: one definition of a valid ID.

The model fills tool arguments, so every argument is untrusted. Each tool
checks its inputs here before any query runs: a malformed ID becomes an
invalid_argument result (the model can correct it), never a query.

Numbers from the model can arrive as 40, 40.0 or "40" (function-call
arguments travel as JSON), so positive_int() accepts all three and nothing else.
"""

from __future__ import annotations

import re
from typing import Any

ORDER_ID = re.compile(r"^ORD-\d{5}$")
WAREHOUSE_ID = re.compile(r"^WH-[A-Z]{3}-\d{2}$")
SKU = re.compile(r"^SKU-\d{5}$")
CHANGE_ID = re.compile(r"^CHG-\d{4}$")
# EV-<kind>-<key>-<6 hex>; keys contain hyphens and slashes (EV-INV-WH-BLR-01/SKU-74512-3f9a1c).
EVIDENCE_ID = re.compile(r"EV-[A-Z]{2,4}-\S+?-[0-9a-f]{6}(?![0-9A-Za-z])")


def clean_id(value: Any) -> str:
    """Trimmed, upper-case ID text ('ord-78421 ' -> 'ORD-78421'); the pattern check comes after."""
    return str(value or "").strip().upper()


def positive_int(value: Any, *, maximum: int | None = None) -> int | None:
    """40, 40.0 or '40' -> 40. Anything else (0, -1, 2.5, 'forty', True) -> None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0 or not number.is_integer():
        return None
    number = int(number)
    return min(number, maximum) if maximum else number
