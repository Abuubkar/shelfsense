// PROTOTYPE variant I: composite of the strongest pieces. A's facet sidebar; one applied-filters bar above the
// results that merges what was read from the query (editable, B) with clicked facets, with "Clear all"; C's
// explanation as a drawer when you open a product; D's suggested refinements when results run thin; and zero-result
// recovery that offers to drop each filter. Question: is this the one to build? Throwaway.
import { esc, highlight, money, parsedSummary, product, search } from "./api.js";

export const NAME = "Composite (A+B+C+D)";
const NAMES = { brand: "Brand", color: "Colour", category_id: "Category", price: "Price" };

function chipsToText(keywords, chips) {
  return [keywords, ...chips.map((c) => ({ gender: c.label === "women" ? "women's" : c.label === "men" ? "men's" : c.label, colors: c.value, exclude_colors: `not ${c.value}`, materials: c.value, exclude_materials: `no ${c.value}`, size: c.label, price: c.label })[c.key])].join(" ");
}

export function mount(root) {
  const state = { q: "black womens hiking boots under $100 size 8", sel: {}, items: [], cursor: null, last: null, chips: [], keywords: "" };
  root.innerHTML = `
  <style>
    .i-top{position:sticky;top:0;z-index:4;background:var(--card);border-bottom:1px solid var(--line)}
    .i-row{max-width:1260px;margin:auto;padding:12px 22px;display:flex;gap:14px;align-items:center}
    .i-row b{font-size:19px;letter-spacing:-.02em}.i-row form{flex:1;max-width:680px}
    .i-row input{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink);font-size:15px}
    .i-body{max-width:1260px;margin:auto;padding:16px 22px 100px;display:grid;grid-template-columns:230px 1fr;gap:26px}
    .i-side h4{margin:14px 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:500}
    .i-side label{display:flex;gap:8px;align-items:center;font-size:14px;padding:3px 0}.i-side label span{margin-left:auto;font-size:12px;color:var(--muted)}
    .i-applied{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:10px}
    .i-chip{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 6px 4px 11px;font-size:13px;background:var(--accent-bg);color:var(--accent)}
    .i-chip.facet{background:var(--card);color:var(--ink);border:1px solid var(--line)}.i-chip.off{text-decoration:line-through;opacity:.6}
    .i-chip button{border:0;background:transparent;color:inherit}.i-chip small{opacity:.7}
    .i-kw{font-size:13px;color:var(--muted)}.i-kw b{color:var(--ink)}
    .i-clear{border:0;background:transparent;color:var(--accent);text-decoration:underline;font-size:13px}
    .i-src{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 6px;color:var(--muted)}
    .i-note{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px;font-size:14px;margin-bottom:10px}
    .i-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:14px}
    .i-card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:4px;font-size:14px;cursor:pointer;text-align:left;color:var(--ink)}
    .i-card:hover{border-color:var(--accent)}.i-card .m{font-size:12px;color:var(--muted)}
    .i-try{margin-top:14px;font-size:14px}.i-try button{border:1px solid var(--accent);color:var(--accent);background:transparent;border-radius:999px;padding:4px 11px;margin:3px;font-size:13px}
    .i-more[hidden]{display:none}.i-more{display:block;margin:20px auto;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:8px 22px}
    .i-drawer{position:fixed;top:0;right:0;bottom:0;width:min(480px,94vw);background:var(--card);border-left:1px solid var(--line);box-shadow:-12px 0 30px rgba(0,0,0,.2);padding:22px;overflow:auto;z-index:20}
    .i-drawer .x{float:right;border:0;background:transparent;color:var(--muted);font-size:18px}
    .i-drawer h3{margin:0 0 4px}.i-drawer .f{font-size:14px;line-height:1.6;margin:10px 0}.i-drawer .f span{display:block;font-size:11px;color:var(--muted)}
    .i-bar{display:grid;grid-template-columns:140px 1fr 50px;gap:8px;align-items:center;font-size:12px;margin:3px 0}.i-bar i{display:block;height:7px;border-radius:4px;background:var(--accent)}
  </style>
  <header class="i-top"><div class="i-row"><b>shelfsense</b><form><input aria-label="Search"></form></div></header>
  <div class="i-body"><aside class="i-side"></aside><main><div class="i-applied"></div><div class="i-notes"></div><div class="i-grid"></div><div class="i-try"></div><button class="i-more" hidden>Load more</button></main></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.q;
  $("form").onsubmit = (e) => { e.preventDefault(); state.q = $("input").value; state.sel = {}; run(); };
  $(".i-more").onclick = () => run(true);

  const filters = () => {
    const f = {};
    for (const [k, vs] of Object.entries(state.sel)) {
      if (k === "price") { const [lo, hi] = vs[0].split("-"); if (lo) f.price_min = lo; if (hi) f.price_max = Number(hi) - 1; } else f[k] = vs;
    }
    return f;
  };
  async function run(more = false) {
    const body = await search({ q: state.q, filters: filters(), cursor: more ? state.cursor : null, debug: true });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    if (!more) { state.last = body; state.chips = parsedSummary(body.query_parse); state.keywords = body.query_parse?.keywords ?? state.q; }
    render();
  }
  function toggle(k, v) {
    const vs = new Set(state.sel[k] ?? []);
    if (k === "price") state.sel.price = vs.has(v) ? [] : [v]; else { vs.has(v) ? vs.delete(v) : vs.add(v); state.sel[k] = [...vs]; }
    if (!state.sel[k].length) delete state.sel[k];
    run();
  }
  function label(k, v) { const fv = state.last.facets.find((f) => f.name === k)?.values.find((x) => x.value === v); return fv ? (k === "category_id" ? fv.label.split(" > ").slice(-1)[0] : fv.label) : v; }
  function render() {
    const body = state.last, qp = body.query_parse;
    $(".i-side").innerHTML = body.facets.map((f) => `<h4>${NAMES[f.name]}</h4>` + f.values.slice(0, 8).map((v) => `<label><input type="checkbox" data-k="${f.name}" data-v="${esc(v.value)}" ${state.sel[f.name]?.includes(v.value) ? "checked" : ""}>${esc(f.name === "category_id" ? v.label.split(" > ").slice(-1)[0] : v.label)}<span>${v.count}</span></label>`).join("")).join("");
    root.querySelectorAll(".i-side input").forEach((c) => c.onchange = () => toggle(c.dataset.k, c.dataset.v));
    const parsedChips = state.chips.map((c, n) => `<span class="i-chip ${c.relaxed ? "off" : ""}" title="Read from your search">${esc(c.label)}<button data-n="${n}" aria-label="Remove ${esc(c.label)}">✕</button></span>`);
    const facetChips = Object.entries(state.sel).flatMap(([k, vs]) => vs.map((v) => `<span class="i-chip facet"><small>${NAMES[k]}</small> ${esc(label(k, v))}<button data-k="${k}" data-v="${esc(v)}" aria-label="Remove">✕</button></span>`));
    $(".i-applied").innerHTML = `<span class="i-kw">${body.total.toLocaleString()} results for <b>${esc(state.keywords)}</b></span>${parsedChips.join("")}${facetChips.join("")}`
      + (parsedChips.length + facetChips.length ? `<button class="i-clear">Clear all</button>` : "") + (qp ? `<span class="i-src">${qp.source}${qp.ms ? " · " + qp.ms + " ms" : ""}</span>` : "");
    root.querySelectorAll(".i-applied button[data-n]").forEach((b) => b.onclick = () => { state.chips.splice(Number(b.dataset.n), 1); state.q = chipsToText(state.keywords, state.chips); $("input").value = state.q; run(); });
    root.querySelectorAll(".i-applied button[data-k]").forEach((b) => b.onclick = () => toggle(b.dataset.k, b.dataset.v));
    root.querySelector(".i-clear")?.addEventListener("click", () => { state.sel = {}; state.q = state.keywords; $("input").value = state.q; run(); });
    $(".i-notes").innerHTML = (qp?.source === "degraded" ? `<div class="i-note">Showing broader results: we couldn’t read filters from your search in time.</div>` : "")
      + (qp?.price_relaxed ? `<div class="i-note">Nothing in your price range, so the price is crossed out and all prices are shown.</div>` : "");
    $(".i-grid").innerHTML = state.items.map((i, n) => `<button class="i-card" data-n="${n}"><span>${esc(i.title)}</span><span class="m">${[i.brand, i.color, i.size].filter(Boolean).map(esc).join(" · ")}</span><b class="price">${money(i.price)}</b></button>`).join("");
    root.querySelectorAll(".i-card").forEach((c) => c.onclick = () => explain(state.items[Number(c.dataset.n)]));
    $(".i-more").hidden = !state.cursor;
    renderTry(body);
  }
  function renderTry(body) {
    const tries = [];
    if (!body.total) {
      state.chips.forEach((c, n) => tries.push({ text: `without “${c.label}”`, act: () => { state.chips.splice(n, 1); state.q = chipsToText(state.keywords, state.chips); $("input").value = state.q; run(); } }));
      Object.entries(state.sel).forEach(([k, vs]) => vs.forEach((v) => tries.push({ text: `without ${label(k, v)}`, act: () => toggle(k, v) })));
    } else if (body.total < 6 || body.total > 40) {
      const colors = body.facets.find((f) => f.name === "color")?.values ?? [];
      if (body.total > 40) colors.slice(0, 3).forEach((c) => tries.push({ text: `only ${c.label} · ${c.count}`, act: () => toggle("color", c.value) }));
    }
    $(".i-try").innerHTML = tries.length ? `${body.total ? "Narrow it down:" : "No results. Try:"} ${tries.map((t, n) => `<button data-n="${n}">${esc(t.text)}</button>`).join("")}` : "";
    root.querySelectorAll(".i-try button").forEach((b) => b.onclick = tries[Number(b.dataset.n)].act);
  }
  async function explain(item) {
    root.querySelector(".i-drawer")?.remove();
    const p = await product(item.id);
    const spans = (f) => p.extracted_attributes.filter((a) => a.evidence_field === f).map((a) => [a.evidence_start, a.evidence_end]);
    const raw = Object.entries(p.attributes).sort().map(([k, v]) => `${k}: ${v}`).join("; ") || "(none)";
    const s = item.debug?.scores ?? {}, max = Math.max(1e-9, ...["bm25", "knn", "hybrid", "rerank"].map((k) => Math.abs(s[k] ?? 0)));
    const d = document.createElement("aside");
    d.className = "i-drawer";
    d.innerHTML = `<button class="x" aria-label="Close">✕</button><h3>${esc(p.title)}</h3><b class="price">${money(p.price)}</b> <span class="muted">· ${esc(p.category?.full_path ?? "not classified yet")}</span>
      <div class="f"><span>Title</span>${highlight(p.title, spans("title"))}</div>
      <div class="f"><span>Description</span>${highlight((p.description ?? "").slice(0, 900), spans("description"))}</div>
      <div class="f"><span>Supplier columns</span>${highlight(raw, spans("raw_attributes"))}</div>
      <div class="f"><span>Read from the listing</span>${p.extracted_attributes.map((a) => `${a.name} <b>${esc(a.value)}${a.unit ? " " + a.unit : ""}</b>`).join(" · ") || "nothing yet (not enriched)"}</div>
      <div class="f"><span>Why it ranked #${item.rank}</span>${["bm25", "knn", "hybrid", "rerank"].filter((k) => s[k] != null).map((k) => `<div class="i-bar">${k}<i style="width:${Math.max(4, Math.abs(s[k]) / max * 100)}%"></i>${s[k].toFixed(2)}</div>`).join("") || "<span class='muted'>(scores exist on the first page)</span>"}</div>`;
    d.querySelector(".x").onclick = () => d.remove();
    root.append(d);
  }
  run();
}
