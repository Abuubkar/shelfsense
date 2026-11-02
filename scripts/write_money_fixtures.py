"""Write contracts/fixtures/money.json: amounts and how money.format_money shows them. apps/web's money test reads
it, so the storefront and the API format money identically. Run by `make codegen`."""

import json
from pathlib import Path

from shelfsense_api.money import format_money

CASES = [(0, "USD"), (5, "USD"), (1999, "USD"), (123456, "USD"), (100000000, "USD"), (-1250, "EUR"), (1235, "JPY"),
         (999, "GBP"), (1234567, "KWD"), (4200, "CHF"), (900719925474099312, "USD")]  # the last exceeds 2^53

OUT = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "money.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps([{"amount_minor": a, "currency": c, "expected": format_money(a, c)} for a, c in CASES],
                              indent=2, ensure_ascii=False) + "\n")
    print(OUT)
