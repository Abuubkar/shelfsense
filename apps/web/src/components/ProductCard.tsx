import Link from "next/link";
import type { SearchItem } from "@/lib/api";
import { highlight } from "@/lib/highlight";
import { formatMoney } from "@/lib/money";
import { ProductArt } from "./ProductArt";

/** One result. The link carries the search, so the product page can show how it ranked and lead back. The search's
 * words are marked in the title; a result with none of them is labelled as related (found by meaning). */
export function ProductCard({ item, search, terms = "" }: { item: SearchItem; search: string; terms?: string }) {
  const parts = highlight(item.title, terms);
  const related = terms.trim() !== "" && !parts.some((p) => p.hit);
  return (
    <Link className="card" href={`/products/${item.id}${search ? `?${search}` : ""}`}>
      <div className="art-tile"><ProductArt id={item.id} title={item.title} color={item.color} categoryPath={item.category_path} className="art" /></div>
      <div className="body">
        <span className="title">{parts.map((p, n) => p.hit ? <b key={n}>{p.text}</b> : p.text)}</span>
        <span className="meta">{[item.brand, item.color, item.size].filter(Boolean).join(" · ")}</span>
        <span className="foot">
          <span className="price">{formatMoney(item.price)}</span>
          {related && <span className="related">Related</span>}
        </span>
      </div>
    </Link>
  );
}
