// PROTOTYPE variant A: classic storefront. Facet sidebar + card grid + "load more". The parse shows up as
// "understood" chips above the facets. Question: is the familiar layout enough? Throwaway.
import { esc, money, parsedSummary, search } from "./api.js";
import { DETAILS, currentDetail } from "./details.js";

export const NAME = "Classic storefront";
const FACET_PARAM = { brand: "brand", color: "color", category_id: "category_id" };
const SWATCH = { black: "#222", white: "#f4f4f0", gray: "#9a9a96", brown: "#7a5232", beige: "#d9c7a3", red: "#c8312f", pink: "#e98cb2", orange: "#ec7a26", yellow: "#efc63a", green: "#3f8f4e", blue: "#2f6fd0", navy: "#1f2f5c", purple: "#7c4bb3", gold: "#c9a227", silver: "#c3c7cc", multicolor: "linear-gradient(135deg,#e54,#fc3,#4b7,#38d)" };

export function mount(root) {
  const state = { q: new URLSearchParams(location.search).get("aq") ?? "waterproof women's hiking boots under $120", selected: {}, price: null, items: [], cursor: null, last: null };
  root.innerHTML = `
  <style>
    .a-top{display:flex;gap:16px;align-items:center;padding:14px 24px;border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:2}
    .a-logo{font-weight:800;letter-spacing:-.02em;font-size:20px}.a-top form{flex:1;display:flex;max-width:720px}
    .a-top input{flex:1;padding:10px 14px;border:1px solid var(--line);border-radius:8px 0 0 8px;background:var(--bg);color:var(--ink)}
    .a-top button{padding:0 18px;border:0;border-radius:0 8px 8px 0;background:var(--accent);color:#fff}
    .a-body{display:grid;grid-template-columns:240px 1fr;gap:28px;padding:20px 24px 90px;max-width:1280px;margin:auto}
    .a-side h4{margin:18px 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
    .a-side label{display:flex;gap:8px;align-items:center;font-size:14px;padding:3px 0}.a-side label span{margin-left:auto;color:var(--muted);font-size:12px}
    .a-under{background:var(--accent-bg);border-radius:8px;padding:10px 12px;font-size:13px}.a-under b{display:block;margin-bottom:6px}
    .a-chip{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:2px 9px;margin:2px;font-size:12px}
    .a-chip.relaxed{text-decoration:line-through;opacity:.6}
    .a-head{display:flex;align-items:baseline;gap:12px;margin-bottom:12px}.a-head h2{margin:0;font-size:18px}
    .a-banner{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px;margin-bottom:12px;font-size:14px}
    .a-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}
    .a-card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
    .a-img{height:120px;display:flex;align-items:center;justify-content:center;font-size:12px;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.4)}
    .a-card .b{padding:10px 12px;display:flex;flex-direction:column;gap:4px;flex:1}.a-card .t{font-size:14px;line-height:1.35}
    .a-card .m{font-size:12px;color:var(--muted)}.a-card .price{margin-top:auto}
    .a-more[hidden]{display:none}.a-more{display:block;margin:24px auto;padding:10px 26px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px}
  </style>
  <header class="a-top"><span class="a-logo">shelfsense</span>
    <form><input name="q" aria-label="Search" placeholder="Search products"><button>Search</button></form></header>
  <div class="a-body"><aside class="a-side"></aside><main><div class="a-head"></div><div class="a-banners"></div><div class="a-grid"></div><button class="a-more" hidden>Load more</button></main></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.q;
  $("form").onsubmit = (e) => {
    e.preventDefault(); state.q = $("input").value; state.selected = {}; state.price = null;
    const u = new URL(location); u.searchParams.set("aq", state.q); history.replaceState(null, "", u);  // survives switching detail designs
    run();
  };
  $(".a-more").onclick = () => run(true);

  function filters() {
    const f = {};
    for (const [name, set] of Object.entries(state.selected)) f[FACET_PARAM[name]] = [...set];
    if (state.price) { const [lo, hi] = state.price.split("-"); if (lo) f.price_min = lo; if (hi) f.price_max = Number(hi) - 1; }
    return f;
  }
  async function run(more = false) {
    const body = await search({ q: state.q, filters: filters(), cursor: more ? state.cursor : null });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    state.last = body;
    render();
  }
  function render() {
    const body = state.last, qp = body.query_parse;
    const understood = parsedSummary(qp);
    $(".a-side").innerHTML = (understood.length ? `<div class="a-under"><b>From your search</b>${understood.map((c) => `<span class="a-chip ${c.relaxed ? "relaxed" : ""}">${esc(c.label)}</span>`).join("")}</div>` : "")
      + body.facets.map((f) => `<h4>${f.name === "category_id" ? "Category" : esc(f.name)}</h4>` + f.values.slice(0, 8).map((v) => {
        const on = f.name === "price" ? state.price === v.value : state.selected[f.name]?.has(v.value);
        const label = f.name === "category_id" ? v.label.split(" > ").slice(-1)[0] : v.label;
        return `<label><input type="checkbox" data-f="${f.name}" data-v="${esc(v.value)}" ${on ? "checked" : ""}>${esc(label)}<span>${v.count}</span></label>`;
      }).join("")).join("");
    root.querySelectorAll(".a-side input").forEach((box) => box.onchange = () => {
      const { f, v } = box.dataset;
      if (f === "price") state.price = box.checked ? v : null;
      else { state.selected[f] ??= new Set(); box.checked ? state.selected[f].add(v) : state.selected[f].delete(v); }
      run();
    });
    $(".a-head").innerHTML = `<h2>${body.total.toLocaleString()} results</h2><span class="muted">for “${esc(qp?.keywords ?? state.q)}”</span>`;
    $(".a-banners").innerHTML = (qp?.source === "degraded" ? `<div class="a-banner">Showing broader results: we couldn’t read filters from your search in time.</div>` : "")
      + (qp?.price_relaxed ? `<div class="a-banner">Nothing matched your price, so we’re showing all prices.</div>` : "");
    $(".a-grid").innerHTML = state.items.map((i, n) => `
      <article class="a-card" data-n="${n}" data-id="${i.id}" tabindex="0" style="cursor:pointer"><div class="a-img" style="background:${SWATCH[i.color] ?? "#b9b7ae"}">${esc(i.color ?? "")}</div>
      <div class="b"><div class="t">${esc(i.title)}</div><div class="m">${esc(i.brand ?? "")}${i.size ? " · " + esc(i.size) : ""}</div>
      <div class="m">${esc((i.category_path ?? "").split(" > ").slice(-1)[0])}</div><div class="price">${money(i.price)}</div></div></article>`).join("");
    $(".a-more").hidden = !state.cursor;
    root.querySelectorAll(".a-card").forEach((card) => {
      const open = () => DETAILS[currentDetail()].open({ item: state.items[Number(card.dataset.n)], card, root });
      card.onclick = open;
      card.onkeydown = (e) => { if (e.key === "Enter") open(); };
    });
  }
  run();
}
