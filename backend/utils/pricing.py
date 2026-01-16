import re


def parse_price(price_str: str) -> float | None:
    """
    Parse a price string into a float value.

    Handles formats like "$10.99", "10.99", "$1,234.56", "EUR 10.99", etc.
    Returns None if the price cannot be parsed.
    """
    if not price_str or price_str == "Price not found":
        return None

    cleaned = price_str.replace(",", "")
    match = re.search(r"\d+\.?\d*", cleaned)
    if match:
        return float(match.group())
    return None


def format_price(price: float | None) -> str:
    """Format a price float as a display string with dollar sign."""
    if price is None:
        return "Price not found"
    return f"${price:.2f}"
