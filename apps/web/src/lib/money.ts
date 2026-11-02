// Showing money exactly as the API does (apps/api/src/shelfsense_api/money.py), checked against
// contracts/fixtures/money.json. Integer arithmetic on minor units: never a float (docs/adr/0003).

const EXPONENTS: Record<string, number> = { JPY: 0, KRW: 0, BHD: 3, KWD: 3, OMR: 3 };
const SYMBOLS: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", JPY: "¥" };

export type Money = { amount_minor: number | bigint | string; currency: string };

/** "$1,234.56", "¥1,235", "-€12.00", or "KWD 1,234.567" for currencies without a symbol here. */
export function formatMoney({ amount_minor, currency }: Money): string {
  const exponent = EXPONENTS[currency] ?? 2;
  const minor = BigInt(amount_minor);
  const sign = minor < 0n ? "-" : "";
  const units = minor < 0n ? -minor : minor;
  const scale = 10n ** BigInt(exponent);
  const whole = (units / scale).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const fraction = exponent ? "." + (units % scale).toString().padStart(exponent, "0") : "";
  const symbol = SYMBOLS[currency];
  return symbol ? `${sign}${symbol}${whole}${fraction}` : `${sign}${currency} ${whole}${fraction}`;
}
