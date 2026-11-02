// PROTOTYPE: variant switcher. ?variant=A..I, floating bar, ← → keys. Throwaway.
import * as A from "./variant-a.js";
import * as B from "./variant-b.js";
import * as C from "./variant-c.js";
import * as D from "./variant-d.js";
import * as E from "./variant-e.js";
import * as F from "./variant-f.js";
import * as G from "./variant-g.js";
import * as H from "./variant-h.js";
import * as I from "./variant-i.js";
import { DETAILS, currentDetail, resetDetail } from "./details.js";

const VARIANTS = { A, B, C, D, E, F, G, H, I };
const keys = Object.keys(VARIANTS);
const app = document.getElementById("app");
const current = () => (keys.includes(new URLSearchParams(location.search).get("variant")) ? new URLSearchParams(location.search).get("variant") : "A");

function show(key) {
  const url = new URL(location);
  url.searchParams.set("variant", key);
  history.replaceState(null, "", url);
  app.innerHTML = "";
  document.querySelectorAll(".g-drawer,.i-drawer").forEach((d) => d.remove());
  const u = new URL(location);  // E keeps its own q and f in the URL; other variants start fresh
  if (key !== "E") { u.searchParams.delete("q"); u.searchParams.delete("f"); }
  if (key !== "A") { u.searchParams.delete("detail"); u.searchParams.delete("aq"); }
  history.replaceState(null, "", u);
  VARIANTS[key].mount(app);
  bar.querySelector(".label").textContent = key === "A"
    ? `A · detail ${currentDetail()}: ${DETAILS[currentDetail()].NAME} (click a product)`
    : `${key} · ${VARIANTS[key].NAME}`;
}
// Variant A was chosen (slice 5b); on A the bar cycles its product-detail designs instead (?detail=1..5).
function showDetail(key) {
  const url = new URL(location);
  url.searchParams.set("detail", key);
  history.replaceState(null, "", url);
  resetDetail(app);
  show("A");
}
function step(d) {
  if (current() === "A") {
    const ds = Object.keys(DETAILS);
    return showDetail(ds[(ds.indexOf(currentDetail()) + d + ds.length) % ds.length]);
  }
  show(keys[(keys.indexOf(current()) + d + keys.length) % keys.length]);
}

const bar = document.createElement("div");
bar.className = "switcher";
bar.innerHTML = `<span class="tag">PROTOTYPE</span><button aria-label="Previous variant">←</button><span class="label"></span><button aria-label="Next variant">→</button>`;
bar.children[1].onclick = () => step(-1);
bar.children[3].onclick = () => step(1);
document.body.append(bar);
addEventListener("keydown", (e) => {
  if (e.target.closest("input,textarea,[contenteditable]")) return;
  if (e.key === "ArrowLeft") step(-1);
  if (e.key === "ArrowRight") step(1);
});
show(current());
