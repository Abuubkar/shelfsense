// PROTOTYPE variant B: editable query chips. One big search box; what we understood appears as chips you can
// remove or edit; refinements are pills; results are a dense list with infinite scroll. No sidebar.
// Question: does showing (and editing) the parse beat facets? Throwaway.
import { esc, money, parsedSummary, search } from "./api.js";

export const NAME = "Editable query chips";

// The API takes gender, size and exclusions only through the parse, so chips are turned back into words.
function chipsToText(keywords, chips) {
  const words = chips.map((c) => ({
    gender: c.label === "women" ? "women's" : c.label === "men" ? "men's" : c.label,
    colors: c.value, exclude_colors: `not ${c.value}`, materials: c.value, exclude_materials: `no ${c.value}`,
    size: c.label, price: c.label,
  })[c.key]);
  return [keywords, ...words].join(" ");
}

export function mount(root) {
  const state = { text: "navy wool socks not cotton", chips: [], keywords: "", items: [], cursor: null, last: null, extra: {} };
  root.innerHTML = `
  <style>
    .b-wrap{max-width:860px;margin:0 auto;padding:40px 20px 100px}
    .b-box{display:flex;align-items:center;gap:10px;border:2px solid var(--ink);border-radius:14px;padding:6px 8px 6px 18px;background:var(--card)}
    .b-box input{flex:1;border:0;outline:0;font-size:20px;padding:10px 0;background:transparent;color:var(--ink)}
    .b-box button{border:0;background:var(--ink);color:var(--bg);border-radius:10px;padding:10px 18px}
    .b-read{margin:14px 2px 6px;font-size:13px;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .b-chip{display:inline-flex;align-items:center;gap:6px;background:var(--accent-bg);color:var(--accent);border-radius:999px;padding:4px 6px 4px 12px;font-size:14px}
    .b-chip button{border:0;background:transparent;color:inherit;font-size:14px;padding:0 4px}
    .b-chip.kw{background:var(--card);color:var(--ink);border:1px dashed var(--line);padding-right:12px}
    .b-chip.off{opacity:.55;text-decoration:line-through}
    .b-src{font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 6px}
    .b-pills{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 18px}
    .b-pills select{border:1px solid var(--line);border-radius:999px;padding:6px 10px;background:var(--card);color:var(--ink)}
    .b-note{background:var(--warn-bg);color:var(--warn);border-radius:8px;padding:8px 12px;font-size:14px;margin-bottom:10px}
    .b-count{font-size:13px;color:var(--muted);margin:0 0 6px}
    .b-row{display:grid;grid-template-columns:1fr auto;gap:4px 16px;padding:12px 4px;border-bottom:1px solid var(--line)}
    .b-row .t{font-size:15px}.b-row .m{font-size:12px;color:var(--muted);grid-column:1}.b-row .price{grid-row:1/3;grid-column:2;align-self:center}
    .b-end{text-align:center;color:var(--muted);padding:20px;font-size:13px}
  </style>
  <div class="b-wrap"><form class="b-box"><input aria-label="Search" placeholder="Describe what you want"><button>Search</button></form>
  <div class="b-read"></div><div class="b-pills"></div><div class="b-notes"></div><p class="b-count"></p><div class="b-list"></div><div class="b-end"></div></div>`;
  const $ = (s) => root.querySelector(s);
  $("input").value = state.text;
  $("form").onsubmit = (e) => { e.preventDefault(); state.text = $("input").value; state.extra = {}; run(); };

  async function run(more = false) {
    const body = await search({ q: state.text, filters: state.extra, cursor: more ? state.cursor : null, pageSize: 20 });
    state.items = more ? state.items.concat(body.items) : body.items;
    state.cursor = body.next_cursor;
    if (!more) { state.last = body; state.chips = parsedSummary(body.query_parse); state.keywords = body.query_parse?.keywords ?? state.text; }
    render(more);
  }
  function render(more) {
    const body = state.last, qp = body.query_parse;
    if (!more) {
      $(".b-read").innerHTML = `<span>We searched for</span><span class="b-chip kw" title="Click to edit">${esc(state.keywords)}</span>`
        + state.chips.map((c, n) => `<span class="b-chip ${c.relaxed ? "off" : ""}">${esc(c.label)}<button data-n="${n}" aria-label="Remove ${esc(c.label)}">✕</button></span>`).join("")
        + (qp ? `<span class="b-src">${qp.source}${qp.ms ? " · " + qp.ms + " ms" : ""}</span>` : "");
      root.querySelectorAll(".b-read button").forEach((b) => b.onclick = () => {
        state.chips.splice(Number(b.dataset.n), 1);
        state.text = chipsToText(state.keywords, state.chips);
        $("input").value = state.text;
        run();
      });
      $(".b-chip.kw").onclick = () => {
        const kw = prompt("Search for", state.keywords);
        if (kw != null) { state.keywords = kw; state.text = chipsToText(kw, state.chips); $("input").value = state.text; run(); }
      };
      $(".b-pills").innerHTML = body.facets.filter((f) => f.values.length > 1).map((f) => `<select data-f="${f.name}"><option value="">${f.name === "category_id" ? "Category" : f.name[0].toUpperCase() + f.name.slice(1)}</option>${f.values.slice(0, 10).map((v) => `<option value="${esc(v.value)}">${esc(f.name === "category_id" ? v.label.split(" > ").slice(-1)[0] : v.label)} (${v.count})</option>`).join("")}</select>`).join("");
      root.querySelectorAll(".b-pills select").forEach((s) => s.onchange = () => {
        const f = s.dataset.f;
        if (f === "price") { const [lo, hi] = s.value.split("-"); state.extra.price_min = lo || undefined; state.extra.price_max = hi ? Number(hi) - 1 : undefined; }
        else state.extra[f] = s.value ? [s.value] : [];
        run();
      });
      $(".b-notes").innerHTML = (qp?.source === "degraded" ? `<div class="b-note">We couldn’t read filters in time; these are broader results for your exact words.</div>` : "")
        + (qp?.price_relaxed ? `<div class="b-note">Nothing in that price range, so the price is crossed out above.</div>` : "");
      $(".b-count").textContent = `${body.total.toLocaleString()} products`;
    }
    $(".b-list").innerHTML = state.items.map((i) => `<div class="b-row"><div class="t">${esc(i.title)}</div><div class="price">${money(i.price)}</div>
      <div class="m">${[i.brand, i.color, i.size, (i.category_path ?? "").split(" > ").slice(-1)[0]].filter(Boolean).map(esc).join(" · ")}</div></div>`).join("");
    $(".b-end").textContent = state.cursor ? "Loading more as you scroll…" : "That’s everything.";
  }
  new IntersectionObserver((entries) => { if (entries[0].isIntersecting && state.cursor) run(true); }).observe($(".b-end"));
  run();
}
