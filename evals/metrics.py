"""Eval metrics, written out rather than taken from a library: each is a few lines, and writing them pins the exact
definition the gates use (gains, ties, what an empty answer counts as).

- nDCG@k: discounted cumulative gain with exponential gains (2^grade - 1) over log2(rank + 1), divided by the
  same for the ideal order of every graded product. A query with nothing relevant has no nDCG and is skipped.
- MRR: 1 / rank of the first result graded 2 or 3; 0 when none of the results is.
- Hierarchical F1: precision and recall over the categories' ancestor sets (each category plus every node above
  it), summed over all products before dividing (micro). A wrong leaf in the right branch still scores the shared
  ancestors; NONE predicts the empty set.
- Slot F1: precision and recall over the filter values a parse set, summed over queries.
- McNemar's exact test: whether two models that disagree on some items differ by more than chance, from the
  items only one of them gets right (two-sided binomial at p = 0.5).
"""

import math
import re
from dataclasses import dataclass
from typing import Any

ABSENT = "ABSENT"
LIST_SLOTS = ("colors", "exclude_colors", "materials", "exclude_materials")
SCALAR_SLOTS = ("price_min", "price_max", "gender", "size")
SLOTS = LIST_SLOTS + SCALAR_SLOTS


def dcg(grades: list[int]) -> float:
    return sum((2**g - 1) / math.log2(rank + 1) for rank, g in enumerate(grades, start=1))


def ndcg(ranked: list[int], all_grades: list[int], k: int = 10) -> float | None:
    """nDCG@k of `ranked` (the grades of the results, in order) against every product's grade for the query."""
    ideal = dcg(sorted(all_grades, reverse=True)[:k])
    return dcg(ranked[:k]) / ideal if ideal else None


def reciprocal_rank(ranked: list[int], relevant: int = 2) -> float:
    return next((1 / rank for rank, g in enumerate(ranked, start=1) if g >= relevant), 0.0)


def ancestors(path: str | None) -> set[str]:
    """A category and every node above it, as path prefixes: "A > B > C" -> {"A", "A > B", "A > B > C"}."""
    if not path:
        return set()
    parts = path.split(" > ")
    return {" > ".join(parts[:n]) for n in range(1, len(parts) + 1)}


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, predicted: set[Any], gold: set[Any]) -> None:
        self.tp += len(predicted & gold)
        self.fp += len(predicted - gold)
        self.fn += len(gold - predicted)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def hierarchical_f1(pairs: list[tuple[str | None, str]]) -> float:
    """Micro hierarchical F1 over (predicted path or None, gold path) pairs."""
    counts = Counts()
    for predicted, gold in pairs:
        counts.add(ancestors(predicted), ancestors(gold))
    return counts.f1


def attribute_sets(predicted: str | None, gold: str) -> tuple[set[str], set[str]]:
    """One attribute of one product as (predicted, gold) sets for Counts.add. A wrong value is then both a false
    positive and a false negative; a value predicted where the listing states none (gold ABSENT) is a false
    positive."""
    return ({predicted} if predicted else set()), (set() if gold == ABSENT else {gold})


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def keyword_tokens(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())}


def slot_values(filters: dict[str, Any]) -> dict[str, set[str]]:
    """Every filter slot of a parse as a set of comparable strings ("US 8" for a size)."""
    values: dict[str, set[str]] = {}
    for slot in LIST_SLOTS:
        values[slot] = {str(v) for v in filters.get(slot) or []}
    for slot in SCALAR_SLOTS:
        v = filters.get(slot)
        if isinstance(v, dict):
            v = f"{v['system']} {v['value']}"
        values[slot] = {str(v)} if v is not None else set()
    return values


def score_parse(predicted: dict[str, Any], gold: dict[str, Any], per_slot: dict[str, Counts],
                keywords: Counts) -> bool:
    """Adds one query's parse to the per-slot and keyword counts; True when every filter slot is exactly right
    (exact match is on filters: the keywords are free text, scored by token F1)."""
    p, g = slot_values(predicted["filters"]), slot_values(gold["filters"])
    for slot in SLOTS:
        per_slot.setdefault(slot, Counts()).add(p[slot], g[slot])
    keywords.add(keyword_tokens(predicted["keywords"]), keyword_tokens(gold["keywords"]))
    return p == g


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (the value at rank ceil(pct/100 * n)); 0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def mcnemar_p(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts (items only A got right, only B got right)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)
