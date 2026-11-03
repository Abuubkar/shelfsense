from grading import grade

EMPTY = {"price_min": None, "price_max": None, "colors": [], "exclude_colors": [], "materials": [],
         "exclude_materials": [], "gender": None, "size": None}
JACKETS = "Apparel & Accessories > Clothing > Outerwear > Coats & Jackets"


def query(category: str = JACKETS, **filters) -> dict:
    return {"category": category, "parse": {"keywords": "x", "filters": EMPTY | filters}}


def product(path: str = JACKETS, price: int = 5000, **attributes) -> dict:
    gold = {"color": "ABSENT", "material": "ABSENT", "gender": "ABSENT", "size": "ABSENT", "length": "ABSENT"}
    return {"brand": "Northpeak", "price_minor": price, "gold": {"path": path, "attributes": gold | attributes}}


def test_category_and_every_constraint_is_three_most_is_two_fewer_is_one() -> None:
    q = query(colors=["navy"], materials=["nylon"], price_max=10000)
    assert grade(q, product(color="navy", material="nylon")) == 3
    assert grade(q, product(color="navy", material="polyester")) == 2  # 2 of 3
    assert grade(q, product(color="red", material="polyester")) == 1  # only the price
    assert grade(query(), product()) == 3  # no constraints: the category is everything


def test_siblings_under_a_parent_below_the_top_level_are_related() -> None:
    assert grade(query(), product("Apparel & Accessories > Clothing > Outerwear > Snow Pants & Suits")) == 1
    assert grade(query("Apparel & Accessories > Shoes"), product("Apparel & Accessories > Clothing > Pants")) == 0
    assert grade(query(), product("Home & Garden > Decor > Throw Pillows")) == 0


def test_an_unstated_colour_meets_an_exclusion_but_not_an_inclusion() -> None:
    assert grade(query(exclude_colors=["black"]), product()) == 3
    assert grade(query(colors=["black"]), product()) == 1


def test_gendered_search_accepts_unisex_and_shoe_sizes_compare_in_eu() -> None:
    q = query("Apparel & Accessories > Shoes", gender="men", size={"system": "US", "value": "10"})
    shoes = "Apparel & Accessories > Shoes"
    assert grade(q, product(shoes, gender="men", size="EU 43.5")) == 3  # US 10 men = UK 9 = EU 43.5
    assert grade(q, product(shoes, gender="unisex", size="US 11")) == 3  # unisex US 11 = UK 9 = EU 43.5
    assert grade(q, product(shoes, gender="women", size="US 10")) == 1


def test_brand_and_length_are_constraints_when_the_query_names_them() -> None:
    q = query() | {"brand": "Red Wing", "length_mm": [290, 320]}
    assert grade(q, product(length="305") | {"brand": "Red Wing"}) == 3
    assert grade(q, product(length="305")) == 2
