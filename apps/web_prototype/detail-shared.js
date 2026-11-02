// PROTOTYPE: data helpers the detail designs share (not layout: each design lays itself out). Throwaway.
import { esc, highlight, search } from "./api.js";

export const SWATCH = { black: "#222", white: "#f4f4f0", gray: "#9a9a96", brown: "#7a5232", beige: "#d9c7a3", red: "#c8312f", pink: "#e98cb2", orange: "#ec7a26", yellow: "#efc63a", green: "#3f8f4e", blue: "#2f6fd0", navy: "#1f2f5c", purple: "#7c4bb3", gold: "#c9a227", silver: "#c3c7cc", multicolor: "linear-gradient(135deg,#e54,#fc3,#4b7,#38d)" };

// The supplier's columns as the one line the model quoted from (prompts.raw_attributes_text).
export const rawText = (p) => Object.entries(p.attributes).sort().map(([k, v]) => `${k}: ${v}`).join("; ") || "(none)";
export const spans = (p, field) => p.extracted_attributes.filter((a) => a.evidence_field === field).map((a) => [a.evidence_start, a.evidence_end]);
export const titleHtml = (p) => highlight(p.title, spans(p, "title"));
export const descriptionHtml = (p, max = 1500) => highlight((p.description ?? "").slice(0, max), spans(p, "description"));
export const rawHtml = (p) => highlight(rawText(p), spans(p, "raw_attributes"));

// One row per fact: the supplier's typed column if it has one, else what the model read (with its quote).
export function specs(p) {
  const read = Object.fromEntries(p.extracted_attributes.map((a) => [a.name, a]));
  const size = p.size_value ? `${p.size_system && p.size_system !== "alpha" ? p.size_system + " " : ""}${p.size_value}` : null;
  const rows = [
    ["Colour", p.color_base, read.color], ["Material", p.material, read.material], ["For", p.gender, read.gender],
    ["Size", size, read.size], ["Length", null, read.length],
  ];
  return rows.filter(([, given, model]) => given || model).map(([label, given, model]) => ({
    label, value: given ?? `${model.value}${model.unit ? " " + model.unit : ""}`,
    source: given ? "supplier" : "listing", quote: model?.evidence_text, field: model?.evidence_field,
  })).concat([["Brand", p.brand], ["GTIN", p.gtin], ["SKU", p.supplier_sku], ["Seller", p.supplier]]
    .filter(([, v]) => v).map(([label, value]) => ({ label, value, source: "supplier" })));
}

export const breadcrumb = (p) => (p.category?.full_path ?? "Not classified yet").split(" > ").map(esc).join(" › ");

export async function similar(p, n = 6) {
  const words = p.title.split(/\s+/).slice(0, 4).join(" ");
  const body = await search({ q: words, filters: p.category?.node_id ? { category_id: [p.category.node_id] } : {}, pageSize: n + 1, parse: false });
  return body.items.filter((i) => i.id !== p.id).slice(0, n);
}
