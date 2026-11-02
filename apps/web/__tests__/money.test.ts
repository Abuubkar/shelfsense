import fixtures from "../../../contracts/fixtures/money.json";
import { formatMoney } from "@/lib/money";

// contracts/fixtures/money.json is written by the API's own formatter (scripts/write_money_fixtures.py), so the
// storefront and the API show every amount the same way, beyond 2^53 included.
describe("formatMoney", () => {
  it.each(fixtures)("$amount_minor $currency → $expected", ({ amount_minor, currency, expected }) => {
    expect(formatMoney({ amount_minor: BigInt(amount_minor), currency })).toBe(expected);
  });
});
