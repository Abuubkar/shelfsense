import type { Facet } from "@/lib/api";
import type { SearchState } from "@/lib/search-state";

const TITLES: Record<string, string> = { brand: "Brand", color: "Colour", category_id: "Category", price: "Price" };

export function FacetSidebar({ facets, state, onToggle }: {
  facets: Facet[]; state: SearchState;
  onToggle: (facet: "brand" | "color" | "category_id" | "price", value: string) => void;
}) {
  return (
    <aside className="facets" aria-label="Filters">
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
