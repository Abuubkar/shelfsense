import type { Facet, QueryParse } from "@/lib/api";
import type { SearchState } from "@/lib/search-state";
import { understood } from "@/lib/understood";

const TITLES: Record<string, string> = { brand: "Brand", color: "Colour", category_id: "Category", price: "Price" };

export function FacetSidebar({ facets, state, parse, onToggle }: {
  facets: Facet[]; state: SearchState; parse?: QueryParse | null;
  onToggle: (facet: "brand" | "color" | "category_id" | "price", value: string) => void;
}) {
  const chips = understood(parse);
  return (
    <aside className="facets" aria-label="Filters">
      {chips.length > 0 && (
        <div className="understood" aria-label="Filters read from your search">
          <b>From your search</b>
          {chips.map((c) => <span key={c.label} className={`chip${c.relaxed ? " relaxed" : ""}`}>{c.label}</span>)}
        </div>
      )}
      {facets.map((facet) => (
        <section key={facet.name}>
          <h2>{TITLES[facet.name] ?? facet.name}</h2>
          {facet.values.slice(0, 8).map((v) => {
            const checked = facet.name === "price" ? state.price === v.value : state[facet.name as "brand"].includes(v.value);
            const label = facet.name === "category_id" ? v.label.split(" > ").at(-1) : v.label;
            return (
              <label key={v.value}>
                <input type="checkbox" checked={checked} onChange={() => onToggle(facet.name, v.value)} />
                {label}<span>{v.count}</span>
              </label>
            );
          })}
        </section>
      ))}
    </aside>
  );
}
