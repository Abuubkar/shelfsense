"""Showing money: one format, mirrored exactly by apps/web (src/lib/money.ts, tested against
contracts/fixtures/money.json). Integer arithmetic on minor units throughout: never a float (docs/adr/0003)."""

# ISO 4217 minor-unit exponents for the currencies we expect; anything else is assumed to have cents.
EXPONENTS = {"JPY": 0, "KRW": 0, "BHD": 3, "KWD": 3, "OMR": 3}
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def format_money(amount_minor: int, currency: str) -> str:
    """'$1,234.56', '¥1,235', '-€12.00', or 'KWD 1,234.567' for currencies without a symbol here."""
    exponent = EXPONENTS.get(currency, 2)
    sign, units = ("-" if amount_minor < 0 else ""), abs(amount_minor)
    whole, fraction = divmod(units, 10**exponent)
    number = f"{whole:,}" + (f".{fraction:0{exponent}d}" if exponent else "")
    symbol = SYMBOLS.get(currency)
    return f"{sign}{symbol}{number}" if symbol else f"{sign}{currency} {number}"
