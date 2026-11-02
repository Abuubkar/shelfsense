// The product page's data: one GraphQL query (typed by `pnpm codegen`), the facts with where each came from, and
// how the ranking models scored the product in the search it was opened from.
import { graphql } from "@/gql";
import type { ProductDetailQuery } from "@/gql/graphql";
import { api, type SearchItem } from "./api";
import { gql } from "./graphql";
import { apiFilters, type SearchState } from "./search-state";

export const ProductDetailDocument = graphql(`
  query ProductDetail($id: UUID!) {
    product(id: $id) {
      id title description brand gtin supplier supplierSku
      price { amountMinor currency }
      attributes { name value }
      colorBase material gender sizeSystem sizeValue
      extractedAttributes { name value unit evidenceField evidenceStart evidenceEnd evidenceText }
      category { fullPath nodeId confidence }
    }
  }
`);

export type Product = NonNullable<ProductDetailQuery["product"]>;

export async function loadProduct(id: string): Promise<Product | null> {
  return (await gql(ProductDetailDocument, { id })).product ?? null;
}

// The supplier's columns as the one line the model quoted from (the API's prompts.raw_attributes_text).
export const rawAttributesText = (p: Product) =>
  [...p.attributes].sort((a, b) => a.name.localeCompare(b.name)).map((a) => `${a.name}: ${a.value}`).join("; ") || "(none)";

export const spansFor = (p: Product, field: string) =>
  p.extractedAttributes.filter((a) => a.evidenceField === field).map((a) => ({ start: a.evidenceStart, end: a.evidenceEnd }));

export type Spec = { label: string; value: string; source: "seller" | "listing"; quote?: string; field?: string };

/** One row per fact: the seller's own column when it has one, else what was read from the listing (with the quote). */
export function specs(p: Product): Spec[] {
  const read = Object.fromEntries(p.extractedAttributes.map((a) => [a.name, a]));
  const size = p.sizeValue ? `${p.sizeSystem && p.sizeSystem !== "alpha" ? p.sizeSystem + " " : ""}${p.sizeValue}` : null;
  const facts: [string, string | null | undefined, (typeof read)[string] | undefined][] = [
    ["Colour", p.colorBase, read.color], ["Material", p.material, read.material], ["For", p.gender, read.gender],
    ["Size", size, read.size], ["Length", null, read.length],
  ];
  const out: Spec[] = [];
  for (const [label, given, model] of facts) {
    if (given) out.push({ label, value: given, source: "seller" });
    else if (model) out.push({ label, value: `${model.value}${model.unit ? " " + model.unit : ""}`, source: "listing", quote: model.evidenceText, field: model.evidenceField });
  }
  for (const [label, value] of [["Brand", p.brand], ["GTIN", p.gtin], ["SKU", p.supplierSku], ["Seller", p.supplier]] as const) {
    if (value) out.push({ label, value, source: "seller" });
  }
  return out;
}

/** The product's place in the search it was opened from, with every stage's score, and the results around it
 * (to rank it by each model). Null when it wasn't opened from a search, or isn't among the first 48 results. */
export async function rankingFor(id: string, search: SearchState):
    Promise<{ item: SearchItem; items: SearchItem[]; weights: [number, number] } | null> {
  if (!search.q) return null;
  const { data } = await api.GET("/v1/search", { params: { query: { q: search.q, page_size: 48, debug: true, ...apiFilters(search) } } });
  const item = data?.items.find((i) => i.id === id);
  const [keyword = 0.5, meaning = 0.5] = data?.debug?.hybrid_weights ?? [];
  return item && data ? { item, items: data.items, weights: [keyword, meaning] } : null;
}

export async function similar(p: Product): Promise<SearchItem[]> {
  const { data } = await api.GET("/v1/search", { params: { query: {
    q: p.title.split(/\s+/).slice(0, 4).join(" "), page_size: 7, parse: false,
    ...(p.category?.nodeId ? { category_id: [p.category.nodeId] } : {}),
  } } });
  return (data?.items ?? []).filter((i) => i.id !== p.id).slice(0, 6);
}
