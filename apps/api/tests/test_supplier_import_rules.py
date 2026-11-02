from shelfsense_api.supplier_import import resume_point

PREVIOUS = ["A", "B", "C", "D"]  # the last page read; D was its last item


def test_a_stable_boundary_continues_after_the_overlap_item() -> None:
    assert resume_point(["D", "E", "F"], PREVIOUS) == 1


def test_products_inserted_ahead_shift_the_boundary_and_are_skipped_over() -> None:
    # Two new products at the front pushed everything right: the window now starts two items earlier.
    assert resume_point(["B", "C", "D", "E", "F"], PREVIOUS) == 3


def test_a_moved_last_item_falls_back_to_the_previous_ones() -> None:
    # D was updated and jumped to the front; C still marks where the page ended.
    assert resume_point(["B", "C", "E", "F"], PREVIOUS) == 2


def test_a_shift_longer_than_the_window_finds_nothing() -> None:
    assert resume_point(["X", "Y", "Z"], PREVIOUS) is None
