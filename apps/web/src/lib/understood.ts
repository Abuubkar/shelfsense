import type { QueryParse } from "./api";
import { formatMoney } from "./money";

/** The filters read out of the query, as short labels ("women", "under $120", "size US 8"). */
export function understood(parse?: QueryParse | null): { label: string; relaxed?: boolean }[] {
  if (!parse) return [];
  const f = parse.filters, out: { label: string; relaxed?: boolean }[] = [];
  if (f.gender) out.push({ label: f.gender });
  f.colors.forEach((c) => out.push({ label: c }));
  f.exclude_colors.forEach((c) => out.push({ label: `not ${c}` }));
  f.materials.forEach((m) => out.push({ label: m }));
  f.exclude_materials.forEach((m) => out.push({ label: `no ${m}` }));
  if (f.size) out.push({ label: `size ${f.size.system === "alpha" ? "" : f.size.system + " "}${f.size.value}` });
  const usd = (v: number) => formatMoney({ amount_minor: v, currency: "USD" }).replace(/\.00$/, "");
  if (f.price_min != null && f.price_max != null) out.push({ label: `${usd(f.price_min)}–${usd(f.price_max)}`, relaxed: parse.price_relaxed });
  else if (f.price_max != null) out.push({ label: `under ${usd(f.price_max)}`, relaxed: parse.price_relaxed });
  else if (f.price_min != null) out.push({ label: `over ${usd(f.price_min)}`, relaxed: parse.price_relaxed });
  return out;
}
