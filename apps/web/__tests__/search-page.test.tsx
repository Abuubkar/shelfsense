import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { SearchPage } from "@/components/SearchPage";
import type { SearchResponse } from "@/lib/api";

// The page reads its state from the URL and changes it with router.push; here the URL is a variable the test owns.
let url = new URL("http://localhost/");
const push = jest.fn((to: string) => { url = new URL(to, "http://localhost"); });
jest.mock("next/navigation", () => ({
  useSearchParams: () => url.searchParams,
  usePathname: () => url.pathname,
  useRouter: () => ({ push }),
}));

const item = (n: number) => ({
  id: `00000000-0000-7000-8000-${String(n).padStart(12, "0")}`, rank: n, title: `Trail Boot ${n}`, brand: "Northpeak",
  price: { amount_minor: 12999, currency: "USD" }, color: "black", size: "US 8", category_id: 187,
  category_path: "Apparel & Accessories > Shoes",
});
const parse = (overrides: Partial<NonNullable<SearchResponse["query_parse"]>> = {}) => ({
  source: "llm" as const, keywords: "boots", category_hint: "boots", price_relaxed: false, ms: 900,
  filters: { price_min: null, price_max: null, colors: [], exclude_colors: [], materials: [], exclude_materials: [], gender: null, size: null },
  ...overrides,
});
const page = (overrides: Partial<SearchResponse> = {}): SearchResponse => ({
  items: [item(1), item(2)], total: 3, next_cursor: null, query_parse: parse(),
  facets: [{ name: "color", values: [{ value: "black", label: "black", count: 2 }, { value: "navy", label: "navy", count: 1 }] }],
  ...overrides,
});

const requests: URL[] = [];
let respond: (request: URL) => SearchResponse = () => page();
const server = setupServer(http.get("http://localhost/api/v1/search", ({ request }) => {
  const u = new URL(request.url);
  requests.push(u);
  return HttpResponse.json(respond(u));
}));

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => { url = new URL("http://localhost/?q=boots"); requests.length = 0; push.mockClear(); respond = () => page(); });
afterAll(() => server.close());

test("selecting a facet puts it in the URL, and the next search sends it", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<SearchPage />);
  await user.click(await screen.findByRole("checkbox", { name: /black/ }));

  expect(push).toHaveBeenCalledWith("/?q=boots&color=black", { scroll: false });
  rerender(<SearchPage />); // the router would re-render with the new URL
  await waitFor(() => expect(requests.at(-1)?.searchParams.getAll("color")).toEqual(["black"]));
  expect(requests.at(-1)?.searchParams.get("q")).toBe("boots");
});

test("load more sends the cursor and appends the next page", async () => {
  const user = userEvent.setup();
  respond = (u) => (u.searchParams.get("cursor") === "page-2"
    ? page({ items: [item(3)], next_cursor: null })
    : page({ next_cursor: "page-2" }));
  render(<SearchPage />);
  await user.click(await screen.findByRole("button", { name: "Load more" }));

  expect(await screen.findByRole("link", { name: /Trail Boot 3/ })).toBeInTheDocument();
  expect(requests.at(-1)?.searchParams.get("cursor")).toBe("page-2");
  expect(screen.getAllByRole("link")).toHaveLength(1 + 3); // the logo, then the three products
  expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
});

test("a degraded parse says the results are broader", async () => {
  respond = () => page({ query_parse: parse({ source: "degraded", keywords: "white mens tee size L" }) });
  render(<SearchPage />);
  expect(await screen.findByRole("status")).toHaveTextContent("Showing broader results");
});

test("filters read from the query are shown, a relaxed price struck through", async () => {
  respond = () => page({ query_parse: parse({ price_relaxed: true, filters: { ...parse().filters, gender: "women", price_max: 12000 } }) });
  render(<SearchPage />);
  const understood = await screen.findByLabelText("Filters read from your search");
  expect(understood).toHaveTextContent("women");
  expect(screen.getByText("under $120")).toHaveClass("relaxed");
  expect(screen.getByText("Nothing matched your price, so all prices are shown.")).toBeInTheDocument();
});

test("each result links to its product page, carrying the search", async () => {
  render(<SearchPage />);
  const link = await screen.findByRole("link", { name: /Trail Boot 1/ });
  expect(link).toHaveAttribute("href", `/products/${item(1).id}?q=boots`);
});
