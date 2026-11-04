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

type Results = { key: string; first: SearchResponse; items: SearchItem[]; cursor: string | null };

/** Variant A from the slice 5b prototypes: facet sidebar, card grid, "Load more" through the opaque cursor. The
 * URL is the state: searching, ticking a facet or going Back all change it, and the page follows. */
export function SearchPage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const key = params.toString();
  const state = useMemo(() => fromParams(new URLSearchParams(key)), [key]);
  // Results and failures carry the URL they belong to, so loading is derived (the shown results are another
  // URL's) instead of set inside the effect; the previous search's results stay on screen meanwhile.
  const [results, setResults] = useState<Results | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchPage = useCallback(async (after?: string) => {
    const { data, error: problem } = await api.GET("/v1/search", {
      params: { query: { q: state.q, page_size: PAGE_SIZE, ...apiFilters(state), ...(after ? { cursor: after } : {}) } },
    });
    if (!data) throw new Error(problem?.detail ?? problem?.title ?? "Search failed");
    return data;
  }, [state]);

  useEffect(() => {
    let current = true;
    fetchPage()
      .then((data) => current && setResults({ key, first: data, items: data.items, cursor: data.next_cursor ?? null }))
      .catch((e: Error) => current && setFailure({ key, message: e.message }));
    return () => { current = false; };
  }, [fetchPage, key]);

  const first = results?.first ?? null;
  const items = results?.items ?? [];
  const cursor = results?.cursor ?? null;
  const error = failure?.key === key ? failure.message : null;
  const loading = loadingMore || (results?.key !== key && failure?.key !== key);

  const go = (next: SearchState) => router.push(`${pathname}?${toParams(next)}`, { scroll: false });
  const loadMore = async () => {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const data = await fetchPage(cursor);
      setResults((r) => r && r.key === key ? { ...r, items: r.items.concat(data.items), cursor: data.next_cursor ?? null } : r);
    } catch (e) {
      setFailure({ key, message: (e as Error).message });
    } finally {
      setLoadingMore(false);
    }
  };

  const parse = first?.query_parse;
  const chips = understood(parse);
  return (
    <>
      <header className="top">
        <Link className="logo" href="/">shelfsense</Link>
        <SearchBox key={state.q} value={state.q} onSearch={(q) => go({ q, brand: [], color: [], category_id: [], price: null })} />
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
