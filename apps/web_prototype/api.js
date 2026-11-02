// PROTOTYPE: thin helpers over the real API (proxied at /api). Throwaway.
export async function search({ q = "", filters = {}, cursor = null, pageSize = 24, debug = false, parse = true } = {}) {
  const p = new URLSearchParams({ q, page_size: pageSize, debug, parse });
  for (const [k, vs] of Object.entries(filters)) for (const v of [].concat(vs ?? [])) if (v !== "" && v != null) p.append(k, v);
  if (cursor) p.set("cursor", cursor);
  const r = await fetch(`/api/v1/search?${p}`);
  if (!r.ok) throw new Error(`search ${r.status}: ${await r.text()}`);
  return r.json();
}
export async function product(id) {
  const r = await fetch(`/api/v1/products/${id}`);
  if (!r.ok) throw new Error(`product ${r.status}`);
  return r.json();
}
export const money = (m) => new Intl.NumberFormat("en-US", { style: "currency", currency: m.currency }).format(m.amount_minor / 100);
export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
// Evidence offsets are Unicode code points: index Array.from(text), not text itself.
export function highlight(text, spans) {
  const chars = Array.from(text ?? "");
  let out = "", at = 0;
  for (const [s, e] of [...spans].sort((a, b) => a[0] - b[0])) {
    out += esc(chars.slice(at, s).join("")) + "<mark>" + esc(chars.slice(s, e).join("")) + "</mark>";
    at = e;
  }
  return out + esc(chars.slice(at).join(""));
}
export function parsedSummary(qp) {
  if (!qp) return [];
  const f = qp.filters, out = [];
  if (f.gender) out.push({ key: "gender", label: f.gender });
  for (const c of f.colors) out.push({ key: "colors", value: c, label: c });
  for (const c of f.exclude_colors) out.push({ key: "exclude_colors", value: c, label: `not ${c}` });
  for (const m of f.materials) out.push({ key: "materials", value: m, label: m });
  for (const m of f.exclude_materials) out.push({ key: "exclude_materials", value: m, label: `no ${m}` });
  if (f.size) out.push({ key: "size", label: `size ${f.size.system === "alpha" ? "" : f.size.system + " "}${f.size.value}` });
  if (f.price_min != null || f.price_max != null) {
    const d = (v) => `$${(v / 100).toFixed(0)}`;
    out.push({ key: "price", label: f.price_min != null && f.price_max != null ? `${d(f.price_min)}–${d(f.price_max)}` : f.price_max != null ? `under ${d(f.price_max)}` : `over ${d(f.price_min)}`, relaxed: qp.price_relaxed });
  }
  return out;
}
export const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
