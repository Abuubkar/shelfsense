import { render, screen, within } from "@testing-library/react";
import { RankingInfo } from "@/components/RankingInfo";
import type { SearchItem } from "@/lib/api";
import { ranksAt } from "@/lib/ranking";

const result = (id: string, rank: number, scores: Record<string, number>, stage: "head" | "tail" = "head"): SearchItem => ({
  id, rank, title: id, brand: null, price: { amount_minor: 100, currency: "USD" }, color: null, size: null,
  category_id: null, category_path: null, debug: { stage, scores },
});
const hrefFor = (id: string) => `/products/${id}?q=boots`;

test("one row per stage in pipeline order, ranked by each model alone, the reranker marked as setting the order", () => {
  const boot = result("boot", 1, { bm25: 13.5, bm25_normalized: 1, knn: 0.8, knn_normalized: 0, hybrid: 0.5, rerank: 5.3 });
  const shoe = result("shoe", 2, { bm25: 8.0, bm25_normalized: 0.4, knn: 0.9, knn_normalized: 1, hybrid: 0.7, rerank: -2.1 });
  render(<RankingInfo item={boot} items={[boot, shoe]} weights={[0.5, 0.5]} hrefFor={hrefFor} />);

  const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
  expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual([
    "KeywordBM25 word match", "Meaningbge\u2011small embeddings", "Hybrid50% keyword, 50% meaning",
    "RerankerSets the orderbge\u2011reranker\u2011base"]);
  expect(within(rows[1]).getByText("#2")).toBeInTheDocument(); // second by meaning
  expect(within(rows[3]).getByText("#1")).toBeInTheDocument(); // first after reranking
  expect(rows[3]).toHaveClass("decider");
  expect(screen.getByRole("columnheader", { name: "Rank of 2" })).toBeInTheDocument();
});

test("neighbours show the deciding score with a real minus sign and link back with the search", () => {
  const a = result("a", 1, { hybrid: 0.4, rerank: 0.2 }), b = result("b", 2, { hybrid: 0.3, rerank: -0.159 });
  const c = result("c", 3, { hybrid: 0.2, rerank: -0.183 });
  render(<RankingInfo item={b} items={[a, b, c]} weights={[0.5, 0.5]} hrefFor={hrefFor} />);

  const around = within(screen.getByRole("region", { name: /Next to it, by reranker score/ })).getAllByRole("listitem");
  expect(around.map((li) => li.textContent)).toEqual(["#1a0.200", "#2This product−0.159", "#3c−0.183"]);
  expect(within(around[0]).getByRole("link")).toHaveAttribute("href", "/products/a?q=boots");
  expect(around[1]).toHaveAttribute("aria-current", "true");
});

test("below the top 50 the combined score sets the order and there is no reranker row", () => {
  const item = result("sock", 60, { bm25: 2, knn: 0.81, tail: 2.81 }, "tail");
  render(<RankingInfo item={item} items={[item]} weights={[0.5, 0.5]} hrefFor={hrefFor} />);
  expect(screen.queryByText("Reranker")).not.toBeInTheDocument();
  expect(screen.getByText("Combined").closest("tr")).toHaveClass("decider");
  expect(screen.queryByRole("region")).not.toBeInTheDocument(); // nothing either side to compare with
});

test("tied scores share a rank and say how many they tie with", () => {
  const items = [result("x", 1, { bm25: 9 }), result("y", 2, { bm25: 8.5 }), result("z", 3, { bm25: 8.5 }), result("w", 4, { bm25: 7 })];
  expect([...ranksAt(items, "bm25").values()]).toEqual([1, 2, 2, 4]);
  render(<RankingInfo item={items[2]} items={items} weights={[0.5, 0.5]} hrefFor={hrefFor} />);
  const keyword = screen.getByRole("rowheader", { name: /Keyword/ }).closest("tr")!;
  expect(within(keyword).getByText("tied with 1")).toBeInTheDocument();
});
