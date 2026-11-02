// PROTOTYPE variant F: summary and compare. In the style of AI shopping modes: a dismissible summary card says what
// was understood and what the results look like (brands, price span, colours), computed from facets with no extra
// model call; a comparison table of the top 3 products by attribute, with the listing's own words on hover; then
// the full results. Question: does a synthesized answer help, or does it get in the way of the list? Throwaway.
import { esc, money, parsedSummary, product, search } from "./api.js";

export const NAME = "Summary + compare";

export function mount(root) {
  const state = { q: "womens hiking boots under $150", items: [], cursor: null, last: null, hideSummary: false };
  root.innerHTML = `
  <style>
    .f-wrap{max-width:1040px;margin:0 auto;padding:22px 20px 100px}
    .f-box{display:flex;gap:8px}.f-box input{flex:1;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font-size:16px}
    .f-box button{border:0;border-radius:10px;padding:0 18px;background:var(--accent);color:#fff}
    .f-sum{margin-top:16px;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:0 12px 12px 0;padding:14px 18px;background:var(--card);position:relative}
    .f-sum .x{position:absolute;top:8px;right:10px;border:0;background:transparent;color:var(--muted)}
    .f-sum p{margin:4px 0;line-height:1.55}.f-sum .k{font-size:12px;color:var(--muted)}
    .f-pill{display:inline-block;border-radius:999px;background:var(--accent-bg);color:var(--accent);padding:1px 9px;font-size:13px;margin:2px}
    .f-cmp{margin-top:18px;overflow-x:auto}.f-cmp table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
    .f-cmp th,.f-cmp td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.f-cmp th{font-weight:500;color:var(--muted);width:130px;font-size:12px}
    .f-cmp td span[title]{border-bottom:1px dotted var(--muted);cursor:help}
    .f-cmp thead td{font-weight:600}
    .f-h{margin:26px 0 8px;font-size:15px}
    .f-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
    .f-card{border:1px solid var(--line);border-radius:10px;padding:12px;background:var(--card);font-size:14px;display:flex;flex-direction:column;gap:4px}
    .f-card .m{font-size:12px;color:var(--muted)}
    .f-more[hidden]{display:none}.f-more{display:block;margin:18px auto;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:8px 20px}
  </style>
  <div class="f-wrap"><form class="f-box"><input aria-label="Search"><button>Search</button></form>
  <div class="f-sum-slot"></div><div class="f-cmp"></div><h3 class="f-h"></h3><div class="f-list"></div><button class="f-more" hidden>More results</button></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.q;
  $("form").onsubmit = (e) => { e.preventDefault(); state.q = $("input").value; state.hideSummary = false; run(); };
  $(".f-more").onclick = () => run(true);

  async function run(more = false) {
    const body = await search({ q: state.q, cursor: more ? state.cursor : null, pageSize: 24 });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    if (!more) { state.last = body; await renderTop(body); }
    renderList();
  }
  async function renderTop(body) {
    const qp = body.query_parse, facet = (n) => body.facets.find((f) => f.name === n)?.values ?? [];
    const prices = state.items.map((i) => i.price.amount_minor);
    const span = prices.length ? `${money({ amount_minor: Math.min(...prices), currency: "USD" })} to ${money({ amount_minor: Math.max(...prices), currency: "USD" })}` : "";
    const brands = facet("brand"), colors = facet("color");
    $(".f-sum-slot").innerHTML = state.hideSummary || !body.total ? "" : `<div class="f-sum"><button class="x" aria-label="Hide summary">✕</button>
      <div class="k">What we found</div>
      <p><b>${body.total.toLocaleString()}</b> products match <b>${esc(qp?.keywords ?? state.q)}</b>${parsedSummary(qp).map((c) => ` <span class="f-pill">${esc(c.label)}${c.relaxed ? " (dropped)" : ""}</span>`).join("")}.</p>
      <p>From ${brands.length} brand${brands.length === 1 ? "" : "s"}${brands.length ? ` (most from ${esc(brands[0].label)})` : ""}; the top results run ${span}.
      ${colors.length ? `Most common colours: ${colors.slice(0, 3).map((c) => esc(c.label)).join(", ")}.` : ""}</p>
      ${qp?.source === "degraded" ? `<p class="k">Filters couldn’t be read in time, so this covers your exact words.</p>` : ""}</div>`;
    root.querySelector(".f-sum .x")?.addEventListener("click", () => { state.hideSummary = true; $(".f-sum-slot").innerHTML = ""; });
    const top = await Promise.all(state.items.slice(0, 3).map((i) => product(i.id)));
    const ev = (p, name) => p.extracted_attributes.find((a) => a.name === name);
    const cell = (p, name, fallback) => { const a = ev(p, name); return a ? `<span title="Listing says: “${esc(a.evidence_text)}” (${a.evidence_field})">${esc(a.value)}${a.unit ? " " + a.unit : ""}</span>` : esc(fallback ?? "–"); };
    $(".f-cmp").innerHTML = top.length < 2 ? "" : `<table><thead><tr><th></th>${top.map((p) => `<td>${esc(p.title)}</td>`).join("")}</tr></thead><tbody>
      <tr><th>Price</th>${top.map((p) => `<td class="price">${money(p.price)}</td>`).join("")}</tr>
      <tr><th>Brand</th>${top.map((p) => `<td>${esc(p.brand ?? "–")}</td>`).join("")}</tr>
      <tr><th>Colour</th>${top.map((p) => `<td>${cell(p, "color", p.color_base)}</td>`).join("")}</tr>
      <tr><th>Material</th>${top.map((p) => `<td>${cell(p, "material", p.material)}</td>`).join("")}</tr>
      <tr><th>Size</th>${top.map((p) => `<td>${cell(p, "size", p.size_value ? `${p.size_system === "alpha" ? "" : p.size_system + " "}${p.size_value}` : null)}</td>`).join("")}</tr>
      <tr><th>For</th>${top.map((p) => `<td>${cell(p, "gender", p.gender)}</td>`).join("")}</tr>
      <tr><th>Category</th>${top.map((p) => `<td>${esc(p.category?.full_path.split(" > ").slice(-1)[0] ?? "not classified yet")}</td>`).join("")}</tr>
      </tbody></table>`;
  }
  function renderList() {
    $(".f-h").textContent = state.last.total ? "All results" : "No results";
    $(".f-list").innerHTML = state.items.map((i) => `<div class="f-card"><span>${esc(i.title)}</span><span class="m">${[i.brand, i.color, i.size].filter(Boolean).map(esc).join(" · ")}</span><b class="price">${money(i.price)}</b></div>`).join("");
    $(".f-more").hidden = !state.cursor;
  }
  run();
}
