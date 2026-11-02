import { render, screen, within } from "@testing-library/react";
import { RankingModels } from "@/components/RankingModels";
import type { SearchItem } from "@/lib/api";

const result = (id: string, rank: number, scores: Record<string, number>, stage: "head" | "tail" = "head"): SearchItem => ({
  id, rank, title: id, brand: null, price: { amount_minor: 100, currency: "USD" }, color: null, size: null,
  category_id: null, category_path: null, debug: { stage, scores },
});

test("draws one bar per model and ranks the product by each model alone", () => {
  const boot = result("boot", 1, { bm25: 13.5, bm25_normalized: 1, knn: 0.8, knn_normalized: 0, hybrid: 0.5, rerank: 5.3 });
  const shoe = result("shoe", 2, { bm25: 8.0, bm25_normalized: 0.4, knn: 0.9, knn_normalized: 1, hybrid: 0.7, rerank: 2.1 });
  render(<RankingModels item={boot} items={[boot, shoe]} />);

  const bars = screen.getAllByRole("listitem");
  expect(bars.map((b) => within(b).getByText(/match|Hybrid|Reranker/).textContent)).toEqual(
    ["Keyword match", "Meaning match", "Hybrid", "Reranker"]);
  expect(within(bars[1]).getByText("#2")).toBeInTheDocument(); // second by meaning
  expect(within(bars[3]).getByText("#1")).toBeInTheDocument(); // first after reranking
  expect(bars[3]).toHaveClass("decided"); // in the top 50, the reranker decides the order
  expect(screen.getByRole("img", { name: /Keyword match: 100%/ })).toBeInTheDocument();
});

test("below the top 50 the combined score decides, and no reranker bar is drawn", () => {
  const item = result("sock", 60, { bm25: 2, knn: 0.81, tail: 2.81 }, "tail");
  render(<RankingModels item={item} items={[item]} />);
  expect(screen.queryByText("Reranker")).not.toBeInTheDocument();
  expect(screen.getByText("Combined score").closest("li")).toHaveClass("decided");
});
