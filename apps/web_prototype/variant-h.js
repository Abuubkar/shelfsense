// PROTOTYPE variant H: mobile first, in a 390 px phone frame. Sticky search; a horizontally scrolling strip of
// applied filters with a count and a faded edge; a "Filters" button opens a bottom-sheet tray over the results
// (NN/g's tray pattern) whose sticky button shows the live result count before you apply (Baymard). Two-column
// grid with 44 px tap targets. Question: does the design hold up on a phone? Throwaway.
import { esc, money, parsedSummary, search } from "./api.js";

export const NAME = "Mobile + filter tray";

export function mount(root) {
  const state = { q: "kids rain boots green", sel: {}, draft: {}, items: [], last: null, cursor: null, tray: false, preview: null };
  root.innerHTML = `
  <style>
    .h-stage{display:flex;justify-content:center;padding:24px 0 100px}
    .h-phone{width:390px;height:780px;border:10px solid #111;border-radius:44px;overflow:hidden;position:relative;background:var(--bg);display:flex;flex-direction:column;box-shadow:0 20px 50px rgba(0,0,0,.25)}
    .h-top{padding:14px 12px 8px;background:var(--card);border-bottom:1px solid var(--line)}
    .h-top input{width:100%;height:44px;padding:0 14px;border:1px solid var(--line);border-radius:12px;background:var(--bg);color:var(--ink);font-size:16px}
    .h-row{display:flex;align-items:center;gap:8px;margin-top:8px}
    .h-fbtn{height:36px;border:1px solid var(--ink);background:var(--ink);color:var(--bg);border-radius:999px;padding:0 14px;font-size:14px;flex:none}
    .h-strip{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;mask-image:linear-gradient(90deg,#000 85%,transparent)}
    .h-chip{flex:none;height:36px;display:inline-flex;align-items:center;gap:4px;border:1px solid var(--line);border-radius:999px;padding:0 10px;font-size:13px;background:var(--card);color:var(--ink)}
    .h-chip.auto{border-style:dashed}
    .h-count{font-size:12px;color:var(--muted);padding:8px 12px 0}
    .h-list{flex:1;overflow:auto;padding:8px 12px 20px;display:grid;grid-template-columns:1fr 1fr;gap:10px;align-content:start}
    .h-card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:13px}
    .h-card .img{height:96px}.h-card .b{padding:8px;display:flex;flex-direction:column;gap:3px}
    .h-sheet{position:absolute;left:0;right:0;bottom:0;max-height:78%;background:var(--card);border-radius:20px 20px 0 0;box-shadow:0 -10px 30px rgba(0,0,0,.25);display:flex;flex-direction:column;z-index:3}
    .h-scrim{position:absolute;inset:0;background:rgba(0,0,0,.35);z-index:2}
    .h-grab{width:40px;height:5px;border-radius:3px;background:var(--line);margin:8px auto}
    .h-sheet .body{overflow:auto;padding:0 16px 10px}.h-sheet h4{margin:14px 0 8px;font-size:13px}
    .h-opts{display:flex;flex-wrap:wrap;gap:8px}.h-opts button{min-height:44px;border:1px solid var(--line);background:var(--bg);color:var(--ink);border-radius:12px;padding:0 12px;font-size:14px}
    .h-opts button.on{border-color:var(--accent);background:var(--accent-bg);color:var(--accent)}
    .h-apply{margin:10px 16px 18px;height:50px;border:0;border-radius:14px;background:var(--accent);color:#fff;font-size:16px}
    .h-sheet .top{display:flex;justify-content:space-between;align-items:center;padding:0 16px}.h-sheet .top button{border:0;background:transparent;color:var(--accent)}
  </style>
  <div class="h-stage"><div class="h-phone"><div class="h-top"><form><input aria-label="Search" enterkeyhint="search"></form>
  <div class="h-row"><button class="h-fbtn">Filters</button><div class="h-strip"></div></div></div><div class="h-count"></div><div class="h-list"></div><div class="h-overlay"></div></div></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.q;
  $("form").onsubmit = (e) => { e.preventDefault(); state.q = $("input").value; state.sel = {}; run(); };
  $(".h-fbtn").onclick = () => { state.draft = structuredClone(state.sel); state.tray = true; preview(); };

  const toFilters = (sel) => {
    const f = { ...sel };
    if (sel.price) { const [lo, hi] = sel.price[0].split("-"); delete f.price; if (lo) f.price_min = lo; if (hi) f.price_max = Number(hi) - 1; }
    return f;
  };
  async function run() {
    const body = await search({ q: state.q, filters: toFilters(state.sel), pageSize: 20 });
    state.items = body.items; state.last = body; state.cursor = body.next_cursor;
    render();
  }
  async function preview() {
    state.preview = await search({ q: state.q, filters: toFilters(state.draft), pageSize: 1 });
    renderTray();
  }
  function render() {
    const body = state.last, n = Object.values(state.sel).flat().length, auto = parsedSummary(body.query_parse);
    $(".h-strip").innerHTML = (n ? `<span class="h-chip">${n} applied</span>` : "")
      + Object.entries(state.sel).flatMap(([k, vs]) => vs.map((v) => `<button class="h-chip" data-k="${k}" data-v="${esc(v)}">${esc(k === "category_id" ? "category" : v)} ✕</button>`)).join("")
      + auto.map((c) => `<span class="h-chip auto">${esc(c.label)}</span>`).join("");
    root.querySelectorAll(".h-strip button").forEach((b) => b.onclick = () => { state.sel[b.dataset.k] = state.sel[b.dataset.k].filter((x) => x !== b.dataset.v); if (!state.sel[b.dataset.k].length) delete state.sel[b.dataset.k]; run(); });
    $(".h-count").textContent = `${body.total.toLocaleString()} results${body.query_parse?.source === "degraded" ? " (broader)" : ""}`;
    $(".h-list").innerHTML = state.items.map((i) => `<div class="h-card"><div class="img" style="background:${i.color ? `var(--accent-bg)` : "var(--line)"}"></div><div class="b"><span>${esc(i.title)}</span><b class="price">${money(i.price)}</b></div></div>`).join("");
    renderTray();
  }
  function renderTray() {
    if (!state.tray) { $(".h-overlay").innerHTML = ""; return; }
    const body = state.preview ?? state.last;
    $(".h-overlay").innerHTML = `<div class="h-scrim"></div><div class="h-sheet" role="dialog" aria-label="Filters"><div class="h-grab"></div>
      <div class="top"><b>Filters</b><button class="clear">Clear all</button></div><div class="body">
      ${body.facets.map((f) => `<h4>${f.name === "category_id" ? "Category" : f.name[0].toUpperCase() + f.name.slice(1)}</h4><div class="h-opts">${f.values.slice(0, 10).map((v) => `<button data-f="${f.name}" data-v="${esc(v.value)}" class="${state.draft[f.name]?.includes(v.value) ? "on" : ""}">${esc(f.name === "category_id" ? v.label.split(" > ").slice(-1)[0] : v.label)} · ${v.count}</button>`).join("")}</div>`).join("")}
      </div><button class="h-apply">Show ${body.total.toLocaleString()} results</button></div>`;
    $(".h-scrim").onclick = () => { state.tray = false; renderTray(); };
    $(".h-sheet .clear").onclick = () => { state.draft = {}; preview(); };
    root.querySelectorAll(".h-opts button").forEach((b) => b.onclick = () => {
      const { f, v } = b.dataset, vs = new Set(state.draft[f] ?? []);
      if (f === "price") state.draft.price = vs.has(v) ? [] : [v]; else { vs.has(v) ? vs.delete(v) : vs.add(v); state.draft[f] = [...vs]; }
      if (!state.draft[f].length) delete state.draft[f];
      preview();
    });
    $(".h-apply").onclick = () => { state.sel = state.draft; state.tray = false; run(); };
  }
  run();
}
