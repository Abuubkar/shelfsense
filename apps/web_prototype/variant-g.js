// PROTOTYPE variant G: attribute-first shopping. The key filters are promoted to the top and always open: big
// labelled colour swatches with counts, a dual price slider with exact inputs over the price distribution, gender
// and size chips; results in a tight grid with a quick-view drawer showing the listing's evidence (Baymard's filter
// component guidance). Gender and size go through the query text: the API takes them only from the parse.
// Question: do shoppers filter by attributes before they read results? Throwaway.
import { esc, highlight, money, product, search } from "./api.js";

export const NAME = "Attribute-first";
const SWATCH = { black: "#222", white: "#f4f4f0", gray: "#9a9a96", brown: "#7a5232", beige: "#d9c7a3", red: "#c8312f", pink: "#e98cb2", orange: "#ec7a26", yellow: "#efc63a", green: "#3f8f4e", blue: "#2f6fd0", navy: "#1f2f5c", purple: "#7c4bb3", gold: "#c9a227", silver: "#c3c7cc", multicolor: "conic-gradient(#e54,#fc3,#4b7,#38d,#e54)" };
const SIZES = ["XS", "S", "M", "L", "XL", "US 7", "US 8", "US 9", "US 10"];

export function mount(root) {
  const state = { base: "hiking boots", colors: new Set(), gender: "", size: "", lo: "", hi: "", items: [], last: null, cursor: null };
  root.innerHTML = `
  <style>
    .g-wrap{max-width:1180px;margin:0 auto;padding:20px 20px 100px}
    .g-q{display:flex;gap:10px;align-items:center}.g-q input{flex:1;max-width:520px;padding:10px 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font-size:15px}
    .g-panel{margin:16px 0;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;display:grid;grid-template-columns:1.4fr 1fr;gap:18px 30px}
    .g-panel h4{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:500}
    .g-sw{display:flex;gap:10px;flex-wrap:wrap}.g-sw button{border:0;background:transparent;color:var(--ink);display:flex;flex-direction:column;align-items:center;gap:3px;font-size:11px;width:54px}
    .g-sw i{width:34px;height:34px;border-radius:50%;border:2px solid var(--line);display:block}.g-sw button.on i{outline:3px solid var(--accent);outline-offset:2px}
    .g-sw small{color:var(--muted)}
    .g-hist{display:flex;align-items:flex-end;gap:4px;height:46px}.g-hist div{flex:1;background:var(--accent-bg);border-radius:3px 3px 0 0}
    .g-range{display:flex;gap:8px;align-items:center;margin-top:8px;font-size:13px}.g-range input{width:80px;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
    .g-seg{display:inline-flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}.g-seg button{border:0;background:transparent;color:var(--ink);padding:6px 14px;font-size:13px}.g-seg button.on{background:var(--ink);color:var(--bg)}
    .g-sizes{display:flex;gap:6px;flex-wrap:wrap}.g-sizes button{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:8px;min-width:44px;height:36px;font-size:13px}.g-sizes button.on{border-color:var(--accent);background:var(--accent-bg);color:var(--accent)}
    .g-count{font-size:14px;margin:6px 0 10px}
    .g-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
    .g-card{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:13px;position:relative}
    .g-card .img{height:110px}.g-card .b{padding:8px 10px;display:flex;flex-direction:column;gap:3px}
    .g-card .qv{position:absolute;top:8px;right:8px;border:0;border-radius:6px;padding:3px 8px;font-size:11px;background:rgba(0,0,0,.65);color:#fff;opacity:0;transition:opacity .15s}
    .g-card:hover .qv,.g-card .qv:focus{opacity:1}
    .g-drawer{position:fixed;top:0;right:0;bottom:0;width:min(440px,92vw);background:var(--card);border-left:1px solid var(--line);box-shadow:-10px 0 30px rgba(0,0,0,.2);padding:20px;overflow:auto;z-index:20}
    .g-drawer .x{float:right;border:0;background:transparent;color:var(--muted);font-size:18px}
    .g-drawer p{font-size:14px;line-height:1.6}
  </style>
  <div class="g-wrap"><form class="g-q"><input aria-label="What are you shopping for?"></form>
  <div class="g-panel"></div><div class="g-count"></div><div class="g-grid"></div></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.base;
  $("form").onsubmit = (e) => { e.preventDefault(); state.base = $("input").value; run(); };

  const queryText = () => [state.gender && `${state.gender}'s`.replace("kids's", "kids"), state.base, state.size && `size ${state.size}`].filter(Boolean).join(" ");
  async function run(more = false) {
    const f = { color: [...state.colors] };
    if (state.lo) f.price_min = Math.round(Number(state.lo) * 100);
    if (state.hi) f.price_max = Math.round(Number(state.hi) * 100);
    const body = await search({ q: queryText(), filters: f, cursor: more ? state.cursor : null, pageSize: 30 });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    if (!more) state.last = body;
    render();
  }
  function render() {
    const body = state.last, colors = body.facets.find((x) => x.name === "color")?.values ?? [], prices = body.facets.find((x) => x.name === "price")?.values ?? [];
    const peak = Math.max(1, ...prices.map((p) => p.count));
    $(".g-panel").innerHTML = `
      <div><h4>Colour</h4><div class="g-sw">${colors.map((c) => `<button data-c="${c.value}" class="${state.colors.has(c.value) ? "on" : ""}" aria-pressed="${state.colors.has(c.value)}"><i style="background:${SWATCH[c.value] ?? "#999"}"></i>${esc(c.label)}<small>${c.count}</small></button>`).join("")}</div></div>
      <div><h4>Price</h4><div class="g-hist" title="Results per price band">${prices.map((p) => `<div style="height:${Math.max(6, p.count / peak * 100)}%" title="${esc(p.label)}: ${p.count}"></div>`).join("")}</div>
        <div class="g-range">$<input inputmode="decimal" placeholder="min" value="${state.lo}" data-r="lo"> to $<input inputmode="decimal" placeholder="max" value="${state.hi}" data-r="hi"></div></div>
      <div><h4>For</h4><div class="g-seg">${["", "women", "men", "kids"].map((g) => `<button data-g="${g}" class="${state.gender === g ? "on" : ""}">${g || "Anyone"}</button>`).join("")}</div></div>
      <div><h4>Size</h4><div class="g-sizes">${SIZES.map((s) => `<button data-s="${s}" class="${state.size === s ? "on" : ""}">${s}</button>`).join("")}</div></div>`;
    root.querySelectorAll("[data-c]").forEach((b) => b.onclick = () => { state.colors.has(b.dataset.c) ? state.colors.delete(b.dataset.c) : state.colors.add(b.dataset.c); run(); });
    root.querySelectorAll("[data-g]").forEach((b) => b.onclick = () => { state.gender = b.dataset.g; run(); });
    root.querySelectorAll("[data-s]").forEach((b) => b.onclick = () => { state.size = state.size === b.dataset.s ? "" : b.dataset.s; run(); });
    root.querySelectorAll("[data-r]").forEach((i) => i.onchange = () => { state[i.dataset.r] = i.value; run(); });
    const qp = body.query_parse;
    $(".g-count").innerHTML = `<b>${body.total.toLocaleString()}</b> products${qp?.price_relaxed ? " · no matches in that price, showing all" : ""}${qp?.source === "degraded" ? " · broader results" : ""}`;
    $(".g-grid").innerHTML = state.items.map((i, n) => `<div class="g-card"><div class="img" style="background:${SWATCH[i.color] ?? "#b9b7ae"}"></div><button class="qv" data-n="${n}">Quick view</button>
      <div class="b"><span>${esc(i.title)}</span><b class="price">${money(i.price)}</b></div></div>`).join("");
    root.querySelectorAll(".qv").forEach((b) => b.onclick = () => quickView(state.items[Number(b.dataset.n)]));
  }
  async function quickView(item) {
    root.querySelector(".g-drawer")?.remove();
    const p = await product(item.id);
    const spans = (f) => p.extracted_attributes.filter((a) => a.evidence_field === f).map((a) => [a.evidence_start, a.evidence_end]);
    const d = document.createElement("aside");
    d.className = "g-drawer";
    d.innerHTML = `<button class="x" aria-label="Close">✕</button><h3>${highlight(p.title, spans("title"))}</h3><b class="price">${money(p.price)}</b>
      <p>${highlight((p.description ?? "").slice(0, 600), spans("description"))}</p>
      <p class="muted">${p.extracted_attributes.map((a) => `${a.name}: <b>${esc(a.value)}</b>`).join(" · ") || "Attributes not extracted yet."}</p>`;
    d.querySelector(".x").onclick = () => d.remove();
    root.append(d);
  }
  run();
}
