// PROTOTYPE variant E: instant search. Federated autocomplete while you type (query suggestions and category
// scopes on the left, product previews on the right: Algolia's pattern), a sticky horizontal filter toolbar, and
// an applied-filters bar with "Clear all" that also lists filters read from the query (Baymard). State lives in
// the URL. Typeahead never calls the model (parse=false); Enter does. Throwaway.
import { debounce, esc, money, parsedSummary, search } from "./api.js";

export const NAME = "Instant search + toolbar";
const LABEL = { color: "Colour", brand: "Brand", category_id: "Category", price: "Price" };

export function mount(root) {
  const url = new URL(location);
  const state = { q: url.searchParams.get("q") ?? "rain jacket", sel: JSON.parse(url.searchParams.get("f") ?? "{}"), items: [], cursor: null, last: null, open: null };
  root.innerHTML = `
  <style>
    .e-head{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line)}
    .e-row{max-width:1200px;margin:auto;padding:12px 20px;display:flex;gap:14px;align-items:center}
    .e-logo{font-weight:800}.e-search{position:relative;flex:1}
    .e-search input{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink);font-size:15px}
    .e-ac{position:absolute;top:calc(100% + 6px);left:0;right:0;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 12px 30px rgba(0,0,0,.18);display:grid;grid-template-columns:1fr 1.4fr;overflow:hidden}
    .e-ac h5{margin:0;padding:10px 14px 4px;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
    .e-ac .opt{padding:7px 14px;font-size:14px;cursor:pointer}.e-ac .opt:hover{background:var(--accent-bg)}.e-ac .opt small{color:var(--muted)}
    .e-ac .prods{border-left:1px solid var(--line);padding-bottom:8px}.e-ac .p{display:flex;justify-content:space-between;gap:10px;padding:7px 14px;font-size:13px;cursor:pointer}.e-ac .p:hover{background:var(--accent-bg)}
    .e-bar{max-width:1200px;margin:auto;padding:0 20px 10px;display:flex;gap:8px;flex-wrap:wrap;position:relative}
    .e-dd{position:relative}.e-dd>button{border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:999px;padding:6px 14px;font-size:13px}
    .e-dd>button.on{border-color:var(--accent);color:var(--accent);background:var(--accent-bg)}
    .e-pop{position:absolute;top:calc(100% + 6px);left:0;min-width:240px;background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 24px rgba(0,0,0,.16);padding:10px;z-index:6;max-height:320px;overflow:auto}
    .e-pop label{display:flex;gap:8px;align-items:center;font-size:14px;padding:4px 2px}.e-pop label span{margin-left:auto;color:var(--muted);font-size:12px}
    .e-pop input[type=search]{width:100%;margin-bottom:6px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink)}
    .e-applied{max-width:1200px;margin:auto;padding:10px 20px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:13px}
    .e-chip{display:inline-flex;flex-direction:column;border:1px solid var(--line);background:var(--card);border-radius:8px;padding:3px 26px 3px 9px;position:relative;line-height:1.2}
    .e-chip small{font-size:10px;color:var(--muted)}.e-chip button{position:absolute;right:4px;top:50%;transform:translateY(-50%);border:0;background:transparent;color:var(--muted)}
    .e-chip.auto{border-style:dashed}.e-clear{border:0;background:transparent;color:var(--accent);text-decoration:underline}
    .e-main{max-width:1200px;margin:auto;padding:14px 20px 100px}
    .e-tools{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-size:14px}
    .e-tools button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:4px 10px;border-radius:6px}
    .e-tools button.on{background:var(--ink);color:var(--bg)}
    .e-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:14px}
    .e-grid.list{grid-template-columns:1fr}
    .e-card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:5px;font-size:14px}
    .e-grid.list .e-card{flex-direction:row;align-items:center;justify-content:space-between}
    .e-card .m{font-size:12px;color:var(--muted)}
    .e-note{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px;font-size:13px;margin-bottom:10px}
  </style>
  <header class="e-head"><div class="e-row"><span class="e-logo">shelfsense</span><form class="e-search"><input aria-label="Search" autocomplete="off"><div class="e-ac" hidden></div></form></div>
  <div class="e-bar"></div></header><div class="e-applied"></div>
  <main class="e-main"><div class="e-tools"><span class="count"></span><span><button data-v="grid" class="on">Grid</button> <button data-v="list">List</button></span></div><div class="e-notes"></div><div class="e-grid"></div></main>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.q;

  const persist = () => { const u = new URL(location); u.searchParams.set("q", state.q); u.searchParams.set("f", JSON.stringify(state.sel)); history.replaceState(null, "", u); };
  const filters = () => {
    const f = {};
    for (const [k, vs] of Object.entries(state.sel)) {
      if (k === "price") { const [lo, hi] = vs[0].split("-"); if (lo) f.price_min = lo; if (hi) f.price_max = Number(hi) - 1; }
      else f[k] = vs;
    }
    return f;
  };

  const typeahead = debounce(async (text) => {
    if (!text.trim()) { $(".e-ac").hidden = true; return; }
    const body = await search({ q: text, pageSize: 5, parse: false });
    const cats = (body.facets.find((f) => f.name === "category_id")?.values ?? []).slice(0, 3);
    $(".e-ac").innerHTML = `<div><h5>Searches</h5><div class="opt" data-q="${esc(text)}">${esc(text)} <small>· ${body.total} results</small></div>
      ${cats.map((c) => `<div class="opt" data-q="${esc(text)}" data-cat="${esc(c.value)}">${esc(text)} <small>in ${esc(c.label.split(" > ").slice(-1)[0])} · ${c.count}</small></div>`).join("")}</div>
      <div class="prods"><h5>Products</h5>${body.items.map((i) => `<div class="p" data-q="${esc(i.title)}"><span>${esc(i.title)}</span><b>${money(i.price)}</b></div>`).join("")}</div>`;
    $(".e-ac").hidden = false;
    root.querySelectorAll(".e-ac [data-q]").forEach((el) => el.onmousedown = (e) => {
      e.preventDefault(); state.q = el.dataset.q; $("input").value = state.q; state.sel = el.dataset.cat ? { category_id: [el.dataset.cat] } : {};
      $(".e-ac").hidden = true; run();
    });
  }, 200);
  $("input").oninput = (e) => typeahead(e.target.value);
  $("input").onblur = () => setTimeout(() => ($(".e-ac").hidden = true), 150);
  $("form").onsubmit = (e) => { e.preventDefault(); state.q = $("input").value; state.sel = {}; $(".e-ac").hidden = true; run(); };
  root.querySelectorAll(".e-tools button").forEach((b) => b.onclick = () => {
    root.querySelectorAll(".e-tools button").forEach((x) => x.classList.toggle("on", x === b));
    $(".e-grid").classList.toggle("list", b.dataset.v === "list");
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".e-dd")) { state.open = null; root.querySelectorAll(".e-pop").forEach((p) => p.remove()); } });

  async function run(more = false) {
    persist();
    const body = await search({ q: state.q, filters: filters(), cursor: more ? state.cursor : null });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    if (!more) state.last = body;
    render();
  }
  function toggle(name, value) {
    const vs = new Set(state.sel[name] ?? []);
    if (name === "price") state.sel.price = vs.has(value) ? [] : [value];
    else { vs.has(value) ? vs.delete(value) : vs.add(value); state.sel[name] = [...vs]; }
    if (!state.sel[name].length) delete state.sel[name];
    run();
  }
  function render() {
    const body = state.last, qp = body.query_parse;
    $(".e-bar").innerHTML = body.facets.map((f) => `<div class="e-dd" data-f="${f.name}"><button class="${state.sel[f.name] ? "on" : ""}">${LABEL[f.name]}${state.sel[f.name] ? ` · ${state.sel[f.name].length}` : ""} ▾</button></div>`).join("");
    root.querySelectorAll(".e-dd").forEach((dd) => dd.querySelector("button").onclick = (e) => {
      e.stopPropagation();
      root.querySelectorAll(".e-pop").forEach((p) => p.remove());
      const f = body.facets.find((x) => x.name === dd.dataset.f);
      const pop = document.createElement("div");
      pop.className = "e-pop";
      const options = (filter = "") => f.values.filter((v) => v.label.toLowerCase().includes(filter)).map((v) => `<label><input type="checkbox" data-v="${esc(v.value)}" ${state.sel[f.name]?.includes(v.value) ? "checked" : ""}>${esc(f.name === "category_id" ? v.label.split(" > ").slice(-1)[0] : v.label)}<span>${v.count}</span></label>`).join("");
      pop.innerHTML = (f.values.length > 6 ? `<input type="search" placeholder="Search ${LABEL[f.name].toLowerCase()}">` : "") + `<div class="opts">${options()}</div>`;
      dd.append(pop);
      const wire = () => pop.querySelectorAll("input[type=checkbox]").forEach((c) => c.onchange = () => toggle(f.name, c.dataset.v));
      pop.querySelector("input[type=search]")?.addEventListener("input", (ev) => { pop.querySelector(".opts").innerHTML = options(ev.target.value.toLowerCase()); wire(); });
      wire();
    });
    const label = (name, v) => { const fv = body.facets.find((x) => x.name === name)?.values.find((x) => x.value === v); return fv ? (name === "category_id" ? fv.label.split(" > ").slice(-1)[0] : fv.label) : v; };
    const chips = Object.entries(state.sel).flatMap(([k, vs]) => vs.map((v) => `<span class="e-chip"><small>${LABEL[k]}</small>${esc(label(k, v))}<button data-k="${k}" data-v="${esc(v)}" aria-label="Remove">✕</button></span>`))
      .concat(parsedSummary(qp).map((c) => `<span class="e-chip auto" title="Read from your search"><small>from search</small>${esc(c.label)}${c.relaxed ? " (dropped)" : ""}</span>`));
    $(".e-applied").innerHTML = chips.length ? chips.join("") + (Object.keys(state.sel).length ? `<button class="e-clear">Clear all</button>` : "") : "";
    root.querySelectorAll(".e-applied button[data-k]").forEach((b) => b.onclick = () => toggle(b.dataset.k, b.dataset.v));
    root.querySelector(".e-clear")?.addEventListener("click", () => { state.sel = {}; run(); });
    $(".count").textContent = `${body.total.toLocaleString()} results for “${qp?.keywords ?? state.q}”`;
    $(".e-notes").innerHTML = qp?.source === "degraded" ? `<div class="e-note">Showing broader results for your exact words.</div>` : "";
    $(".e-grid").innerHTML = state.items.map((i) => `<div class="e-card"><span>${esc(i.title)}</span><span class="m">${[i.brand, i.color, i.size].filter(Boolean).map(esc).join(" · ")}</span><b class="price">${money(i.price)}</b></div>`).join("")
      + (state.cursor ? `<button class="e-card more" style="cursor:pointer;justify-content:center;align-items:center">Load more</button>` : "");
    root.querySelector(".e-card.more")?.addEventListener("click", () => run(true));
  }
  run();
}
