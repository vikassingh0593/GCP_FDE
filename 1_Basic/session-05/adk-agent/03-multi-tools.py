from datetime import datetime, timezone
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from common.model_factory import build_model

load_dotenv()



def lookup_price(product: str) -> dict:
    """Look up the demo price for a product name."""
    catalog = {"laptop": 999.0, "monitor": 299.0, "keyboard": 89.0}
    price = catalog.get(product.strip().lower())
    return {"product": product, "price_usd": price, "found": price is not None}

def calculate_discount(price: float, percent: float) -> dict:
    """Calculate final price after a percentage discount."""
    final = price * (1 - percent / 100)
    return {"original": price, "discount_percent": percent, "final": round(final, 2)}


# Return current UTC time as a simple third tool.
def current_utc_time() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


agent = LlmAgent(
    name = "Multi Tools Agent",
    model = build_model(),
    description = "An agent that can look up product prices, calculate discounts, and return the time",
    instructions = "You are a helpful assistant that can look up product prices, calculate discounts, and return the time",
    tools = [lookup_price, calculate_discount, current_utc_time]
)