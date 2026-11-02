import Link from "next/link";
import type { SearchItem } from "@/lib/api";
import { formatMoney } from "@/lib/money";
import { swatch } from "@/lib/swatch";

/** One result. The link carries the search, so the product page can show how it ranked and lead back. */
export function ProductCard({ item, search }: { item: SearchItem; search: string }) {
  return (
    <Link className="card" href={`/products/${item.id}${search ? `?${search}` : ""}`}>
      <div className="swatch" style={{ background: swatch(item.color) }} aria-hidden="true">{item.color ?? ""}</div>
      <div className="body">
        <span className="title">{item.title}</span>
        <span className="meta">{[item.brand, item.size].filter(Boolean).join(" · ")}</span>
        <span className="meta">{item.category_path?.split(" > ").at(-1)}</span>
        <span className="price">{formatMoney(item.price)}</span>
      </div>
    </Link>
  );
}
