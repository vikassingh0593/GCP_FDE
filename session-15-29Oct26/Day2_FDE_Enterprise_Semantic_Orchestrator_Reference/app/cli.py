"""Participant CLI for the reference orchestrator."""

from __future__ import annotations
import argparse, json
from pathlib import Path
from app.orchestrator import Investigation

DATA = Path(__file__).resolve().parents[1] / "data"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("order_id", nargs="?")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    orders = json.loads((DATA / "orders.json").read_text(encoding="utf-8"))
    if args.list:
        for order_id, item in orders.items():
            print(order_id, "-", item["status"])
        return

    if not args.order_id:
        parser.error("Provide ORDER_ID or use --list.")
    if args.order_id not in orders:
        parser.error(f"Unknown order: {args.order_id}")

    Investigation(args.order_id).run()

if __name__ == "__main__":
    main()
