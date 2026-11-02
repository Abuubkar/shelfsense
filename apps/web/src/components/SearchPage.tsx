"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type SearchItem, type SearchResponse } from "@/lib/api";
import { apiFilters, fromParams, toggle, toParams, type SearchState } from "@/lib/search-state";
import { understood } from "@/lib/understood";
import { FacetSidebar } from "./FacetSidebar";
import { ProductCard } from "./ProductCard";
import { SearchBox } from "./SearchBox";

const PAGE_SIZE = 24;

/** Variant A from the slice 5b prototypes: facet sidebar, card grid, "Load more" through the opaque cursor. The
 * URL is the state: searching, ticking a facet or going Back all change it, and the page follows. */
export function SearchPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const key = params.toString();
  const state = useMemo(() => fromParams(new URLSearchParams(key)), [key]);
  const [first, setFirst] = useState<SearchResponse | null>(null);
  const [items, setItems] = useState<SearchItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchPage = useCallback(async (after?: string) => {
    const { data, error: problem } = await api.GET("/v1/search", {
      params: { query: { q: state.q, page_size: PAGE_SIZE, ...apiFilters(state), ...(after ? { cursor: after } : {}) } },
    });
    if (!data) throw new Error(problem?.detail ?? problem?.title ?? "Search failed");
    return data;
  }, [state]);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    fetchPage()
      .then((data) => { if (current) { setFirst(data); setItems(data.items); setCursor(data.next_cursor ?? null); } })
      .catch((e: Error) => current && setError(e.message))
      .finally(() => current && setLoading(false));
    return () => { current = false; };
  }, [fetchPage]);

  const go = (next: SearchState) => router.push(`${pathname}?${toParams(next)}`, { scroll: false });
  const loadMore = async () => {
    if (!cursor) return;
    setLoading(true);
    try {
      const data = await fetchPage(cursor);
      setItems((previous) => previous.concat(data.items));
      setCursor(data.next_cursor ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const parse = first?.query_parse;
  const chips = understood(parse);
  return (
    <>
      <header className="top">
        <Link className="logo" href="/">shelfsense</Link>
        <SearchBox value={state.q} onSearch={(q) => go({ q, brand: [], color: [], category_id: [], price: null })} />
      </header>
      <div className="layout">
        <FacetSidebar facets={first?.facets ?? []} state={state}
                      onToggle={(facet, value) => go(toggle(state, facet, value))} />
        <main aria-busy={loading}>
          {error && <p role="alert" className="notice">Search failed: {error}</p>}
          {first && (
            <div className="results-head">
              <h1>{first.total.toLocaleString("en-US")} results</h1>
              {state.q && <span className="muted">for “{parse?.keywords ?? state.q}”</span>}
            </div>
          )}
          {chips.length > 0 && (
            <p className="understood" aria-label="Filters read from your search">
              <span className="label">Read from your search</span>
              {chips.map((c) => <span key={c.label} className={`chip${c.relaxed ? " relaxed" : ""}`}>{c.label}</span>)}
            </p>
          )}
          {parse?.source === "degraded" && (
            <p className="notice" role="status">Showing broader results: we couldn’t read filters from your search in time.</p>
          )}
          {parse?.price_relaxed && <p className="notice" role="status">Nothing matched your price, so all prices are shown.</p>}
          {first && !first.total && <p className="empty">No products match. Try fewer words or remove a filter.</p>}
          <ul className="grid">
            {items.map((item) => <li key={item.id}><ProductCard item={item} search={key} terms={parse?.keywords ?? state.q} /></li>)}
          </ul>
          {cursor && <button className="more" onClick={loadMore} disabled={loading}>{loading ? "Loading…" : "Load more"}</button>}
        </main>
      </div>
    </>
  );
}
