import pytest
from metrics import Counts, hierarchical_f1, mcnemar_p, ndcg, percentile, reciprocal_rank, score_parse


def test_ndcg_divides_by_the_ideal_order_of_every_graded_product() -> None:
    # DCG = 7/log2(2) + 3/log2(3) + 0 = 8.8928; ideal top 3 is [3, 2, 1]: 8.8928 + 1/log2(4) = 9.3928.
    assert ndcg([3, 2, 0], [3, 2, 0, 1], k=3) == pytest.approx(8.8928 / 9.3928, abs=1e-4)


def test_ndcg_is_undefined_when_nothing_is_relevant() -> None:
    assert ndcg([0, 0], [0, 0, 0]) is None


def test_reciprocal_rank_counts_the_first_result_graded_two_or_more() -> None:
    assert reciprocal_rank([1, 0, 2, 3]) == pytest.approx(1 / 3)
    assert reciprocal_rank([1, 1]) == 0.0


def test_hierarchical_f1_credits_shared_ancestors_and_none_predicts_nothing() -> None:
    # A>B>C for A>B>D: tp 2 (A, A>B), fp 1, fn 1. NONE for A>E: fn 2. Micro P = 2/3, R = 2/5, F1 = 0.5.
    assert hierarchical_f1([("A > B > C", "A > B > D"), (None, "A > E")]) == pytest.approx(0.5)


def test_slot_f1_counts_each_filter_value_and_exact_match_needs_every_slot() -> None:
    empty = {"price_min": None, "price_max": None, "colors": [], "exclude_colors": [], "materials": [],
             "exclude_materials": [], "gender": None, "size": None}
    gold = {"keywords": "hiking socks", "filters": empty | {"colors": ["red"], "materials": ["wool"]}}
    predicted = {"keywords": "sock", "filters": empty | {"colors": ["red"], "gender": "women"}}
    per_slot: dict[str, Counts] = {}
    keywords = Counts()
    assert score_parse(predicted, gold, per_slot, keywords) is False
    total = Counts(*(sum(getattr(c, f) for c in per_slot.values()) for f in ("tp", "fp", "fn")))
    assert (total.tp, total.fp, total.fn) == (1, 1, 1)  # red right, women extra, wool missed
    assert per_slot["colors"].f1 == 1.0 and per_slot["materials"].recall == 0.0
    assert (keywords.tp, keywords.fp, keywords.fn) == (1, 0, 1)  # "sock" matches "socks" by stem
    assert score_parse(gold, gold, per_slot, keywords) is True


def test_percentile_is_nearest_rank() -> None:
    assert percentile([5, 1, 3, 2, 4], 50) == 3
    assert percentile(list(range(1, 21)), 95) == 19


def test_mcnemar_p_is_the_two_sided_binomial_tail_of_the_discordant_items() -> None:
    # 1 vs 9 discordant: P(X <= 1 | n=10, 0.5) = 11/1024, doubled.
    assert mcnemar_p(1, 9) == pytest.approx(22 / 1024)
    assert mcnemar_p(5, 5) == 1.0
    assert mcnemar_p(0, 0) == 1.0
