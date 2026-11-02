// The search page's state lives in the URL (shareable, and Back works): q, facet values, a price bucket.
// These turn it into API query parameters and back.

export type SearchState = { q: string; brand: string[]; color: string[]; category_id: string[]; price: string | null };
export const FACETS = ["brand", "color", "category_id"] as const;

export function fromParams(params: URLSearchParams): SearchState {
  return {
    q: params.get("q") ?? "",
    brand: params.getAll("brand"),
    color: params.getAll("color"),
    category_id: params.getAll("category_id"),
    price: params.get("price"),
  };
}

export function toParams(state: SearchState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.q) params.set("q", state.q);
  for (const name of FACETS) for (const value of state[name]) params.append(name, value);
  if (state.price) params.set("price", state.price);
  return params;
}

/** The search API's filters. A price bucket "2500-5000" is [from, to) in minor units: price_max is to - 1. */
export function apiFilters(state: SearchState) {
  const [lo, hi] = (state.price ?? "").split("-");
  return {
    brand: state.brand.length ? state.brand : undefined,
    color: state.color.length ? state.color : undefined,
    category_id: state.category_id.length ? state.category_id.map(Number) : undefined,
    price_min: lo ? Number(lo) : undefined,
    price_max: hi ? Number(hi) - 1 : undefined,
  };
}

export function toggle(state: SearchState, facet: "brand" | "color" | "category_id" | "price", value: string): SearchState {
  if (facet === "price") return { ...state, price: state.price === value ? null : value };
  const values = state[facet];
  return { ...state, [facet]: values.includes(value) ? values.filter((v) => v !== value) : [...values, value] };
}
