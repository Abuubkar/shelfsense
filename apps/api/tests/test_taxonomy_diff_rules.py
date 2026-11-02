from shelfsense_api.taxonomy import Node, diff_releases


def tree(*rows: tuple[int, str]) -> list[Node]:
    """Nodes from (id, path) rows, with parents and leaves worked out like read_release does."""
    id_by_path = {path: node_id for node_id, path in rows}
    parents = {id_by_path[" > ".join(p.split(" > ")[:-1])] for _, p in rows if " > " in p}
    return [Node(node_id, id_by_path.get(" > ".join(path.split(" > ")[:-1])), path.split(" > ")[-1], path,
                 path.count(" > ") + 1, node_id not in parents) for node_id, path in rows]


OLD = tree((1, "Apparel"), (2, "Apparel > Shoes"), (3, "Apparel > Coats"), (4, "Apparel > Hats"),
           (5, "Apparel > Socks"), (6, "Apparel > Scarves"), (7, "Apparel > Gloves"), (8, "Apparel > Mittens"))


def kinds(new: list[Node]) -> dict[int, tuple[str, int | None, bool]]:
    return {r.old_node_id: (r.kind, r.new_node_id, r.needs_review) for r in diff_releases(OLD, new)}


def test_ids_that_survive_are_same_or_renamed() -> None:
    new = tree((1, "Apparel"), (2, "Apparel > Shoes"), (3, "Apparel > Coats & Jackets"), (4, "Apparel > Hats"),
               (5, "Apparel > Socks"), (6, "Apparel > Scarves"), (7, "Apparel > Gloves"), (8, "Apparel > Mittens"))
    result = kinds(new)
    assert result[2] == ("same", 2, False)
    assert result[3] == ("renamed", 3, False)


def test_a_leaf_that_gains_children_is_split() -> None:
    new = tree((1, "Apparel"), (2, "Apparel > Shoes"), (21, "Apparel > Shoes > Boots"),
               (22, "Apparel > Shoes > Sneakers"), (3, "Apparel > Coats"), (4, "Apparel > Hats"),
               (5, "Apparel > Socks"), (6, "Apparel > Scarves"), (7, "Apparel > Gloves"), (8, "Apparel > Mittens"))
    assert kinds(new)[2] == ("split", None, False)
    assert kinds(new)[1] == ("same", 1, False)  # a parent with more children is still the same parent


def test_a_new_id_on_the_same_path_is_renamed_but_flagged() -> None:
    new = tree((1, "Apparel"), (2, "Apparel > Shoes"), (3, "Apparel > Coats"), (40, "Apparel > Hats"),
               (5, "Apparel > Socks"), (6, "Apparel > Scarves"), (7, "Apparel > Gloves"), (8, "Apparel > Mittens"))
    assert kinds(new)[4] == ("renamed", 40, True)


def test_categories_landing_on_one_are_merged_and_gone_ones_deleted() -> None:
    # Mittens' ID is gone and its path now belongs to Gloves' ID: both old categories land on node 7.
    new = tree((1, "Apparel"), (2, "Apparel > Shoes"), (3, "Apparel > Coats"), (4, "Apparel > Hats"),
               (7, "Apparel > Mittens"))
    result = kinds(new)
    assert result[7][:2] == ("merged", 7) and result[8][:2] == ("merged", 7)
    assert result[5] == ("deleted", None, True) and result[6] == ("deleted", None, True)
