"""The eval comment CI posts on a pull request: each gated metric on the PR against main, with the delta.

    uv run python evals/pr_comment.py <PR results.json> <main results.json> > comment.md

The first line is a marker, so CI updates its own comment instead of adding one per push. Status per metric:
pass; known miss (main misses it too); newly missed (main passes it); or dropped (worse than main by more than
1.5 points). Only the last two fail the job (run.py --fail-on regressions).
"""

import json
import sys
from pathlib import Path
from typing import Any

from run import BASELINE_TOLERANCE, GATES, check_gates, lookup

MARKER = "<!-- shelfsense-eval -->"


def fmt(value: Any, threshold: float) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}" if threshold > 1 else f"{value:.4f}"


def comment(head: dict[str, Any], base: dict[str, Any]) -> str:
    now, before = head["metrics"], base["metrics"]
    passed_before = {g["metric"]: g["passed"] for g in check_gates(before)}
    rows, problems = [], 0
    for gate in check_gates(now):
        key = gate["metric"]
        threshold = next(t for k, _, t in GATES if k == key)
        op = next(o for k, o, _ in GATES if k == key)
        value, old = gate["value"], lookup(before, key)
        delta = "" if old is None else f"{value - old:+.4f}" if threshold <= 1 else f"{value - old:+,.0f}"
        worse = old is not None and threshold <= 1 and (old - value if op == ">=" else value - old) > BASELINE_TOLERANCE
        if worse:
            status = "**dropped**"
        elif gate["passed"]:
            status = "pass"
        elif passed_before.get(key):
            status = "**newly missed**"
        else:
            status = "known miss"
        problems += status.startswith("**")
        rows.append(f"| `{key}` | {fmt(old, threshold)} | {fmt(value, threshold)} | {delta} | {gate['gate']} | {status} |")
    verdict = (f"{problems} regression(s) against main." if problems else
               "No regressions against main. Known misses are main's too; the gates are unchanged (ADR 0018).")
    search = now.get("search_mappings", {})
    lines = [MARKER, "### Offline eval (dev split, replayed)", "", verdict, "",
             "| Metric | main | this PR | Δ | Gate | Status |", "|---|---:|---:|---:|---|---|", *rows, ""]
    if search:
        lines += [f"Served index: `{search['served']}`. Latency gates come from the last live run "
                  "(`make eval-latency`), not from CI.", ""]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    head_path, base_path = Path(sys.argv[1]), Path(sys.argv[2])
    if not head_path.exists():  # run.py stopped before writing results: say so, don't compare stale numbers
        sys.stdout.write(f"{MARKER}\n### Offline eval (dev split, replayed)\n\n**The eval didn't finish**: see the "
                         "eval-offline job's log.\n")
    else:
        sys.stdout.write(comment(json.loads(head_path.read_text()), json.loads(base_path.read_text())))
