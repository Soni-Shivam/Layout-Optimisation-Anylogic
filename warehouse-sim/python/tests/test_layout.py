import pytest

from whsim import scenario, templates
from whsim.layout import Grid, LayoutError, compile_layout, graph_of, pick_tour, validate

# a hand-checkable warehouse: 7 x 7, cell 2 m
TINY = [
    "# # # # # # #",
    "# A A A A A #",
    "# A S A S A #",
    "# A S A S A #",
    "# A A A A A #",
    "DI R A H PK G DO",
    "# # # # # # #",
]
SKUS = [("X", 3.0), ("Y", 2.0), ("Z", 1.0)]


def tiny(levels=1):
    return Grid.parse(TINY, cell_m=2.0, levels=levels)


def test_tiny_is_valid_and_compiles():
    g = tiny()
    assert validate(g, 3) == []
    lay = compile_layout(g, SKUS, "abc", "tiny")
    assert lay["stats"]["n_slots"] == 4 and lay["stats"]["n_skus"] == 3
    walk = sum(t in ("A", "DI", "DO", "R", "PK", "G", "H") for row in g.cells for t in row)
    assert lay["stats"]["n_nodes"] == walk
    types = sorted(f["type"] for f in lay["facilities"])
    assert types == ["DI", "DO", "G", "H", "PK", "R"]
    for f in lay["facilities"]:                       # coordinates are cell centres in metres
        assert (f["x"], f["y"]) == ((f["c"] + 0.5) * 2.0, (f["r"] + 0.5) * 2.0)


def test_tour_length_by_hand():
    lay = compile_layout(tiny(), SKUS, "abc", "tiny")
    node = {(n[0], n[1]): i for i, n in enumerate(lay["nodes"])}
    g = graph_of(lay)
    home, pk = node[(5, 3)], node[(5, 4)]
    # bay (2,2) is picked from its north neighbour (1,2); bay (3,4) from its north neighbour?
    # (2,4) is a shelf, so the first walkable neighbour in N,S,W,E order is S = (4,4)
    acc = {(s["r"], s["c"]): s["node"] for s in lay["slots"]}
    assert acc[(2, 2)] == node[(1, 2)] and acc[(3, 4)] == node[(4, 4)]
    order, k, length = pick_tour(g, home, [acc[(2, 2)], acc[(3, 4)]], [pk])
    # H(5,3) -> (4,4): 2 steps; (4,4) -> (1,2): 5 steps; (1,2) -> PK(5,4): 6 steps; PK -> H: 1 step
    assert order == [acc[(3, 4)], acc[(2, 2)]]
    assert length == pytest.approx((2 + 5 + 6 + 1) * 2.0)


@pytest.mark.parametrize("bad, msg", [
    (["# # #", "# A #", "# # #"], "need at least"),
    (["# # # #", "# H Q #", "# # # #"], "unknown token"),
    (["# # # # #", "# A S A #", "A # # # #"], "boundary cell"),
])
def test_validate_rejects(bad, msg):
    assert any(msg in e for e in validate(Grid.parse(bad)))


def test_disconnected_and_unreachable_shelf_rejected():
    rows = list(TINY)
    rows[3] = "# A S # S A #"          # still connected around the outside
    assert validate(Grid.parse(rows), 3) == []
    rows[1] = "# A A # A A #"          # aisle cell (2,3) is now walled in on all four sides
    errs = validate(Grid.parse(rows), 3)
    assert any("not connected" in e for e in errs)
    rows = list(TINY)
    rows[2] = "# A A A S S #"
    rows[3] = "# A A A S S #"
    rows[4] = "# A A A S S #"          # bay (3,5) is surrounded
    assert any("no walkable neighbour" in e for e in validate(Grid.parse(rows)))


def test_too_few_slots():
    assert any("every SKU needs a slot" in e for e in validate(tiny(), 5))
    with pytest.raises(LayoutError):
        compile_layout(tiny(), [(f"K{i}", 1.0) for i in range(5)])


def test_abc_puts_fast_movers_closest():
    lay = compile_layout(tiny(levels=2), SKUS, "abc", "tiny")
    g = graph_of(lay)
    home = next(f["node"] for f in lay["facilities"] if f["type"] == "H")
    pk = [f["node"] for f in lay["facilities"] if f["type"] == "PK"]
    cost = {s["sku"]: g.dist(home, s["node"]) + min(g.dist(s["node"], p) for p in pk)
            for s in lay["slots"] if s["sku"]}
    assert cost["X"] <= cost["Y"] <= cost["Z"]
    assert sum(s["sku"] is not None for s in lay["slots"]) == 3


@pytest.mark.parametrize("lid", list(templates.CANDIDATES))
def test_all_candidates_valid(lid):
    p = dict(templates.CANDIDATES[lid])
    slotting = p.pop("slotting")
    g = templates.parallel_aisle(**p)
    skus = [(s, w) for s, w, _ in scenario.make_skus(400)]
    assert validate(g, len(skus)) == []
    lay = compile_layout(g, skus, slotting, lid)
    assert len({s["sku"] for s in lay["slots"] if s["sku"]}) == 400


def test_scenario_format():
    skus = scenario.make_skus(50)
    rows = scenario.make_day(skus, seed=3)
    assert rows == sorted(rows, key=lambda r: (r[0], r[1] != "RECEIPT", r[2]))
    known = {s[0] for s in skus}
    by_order = {}
    for t, typ, i, sku, q in rows:
        assert typ in ("ORDER", "RECEIPT") and sku in known and q >= 1
        if typ == "ORDER":
            by_order.setdefault(i, []).append((t, sku))
    for lines in by_order.values():
        assert len({t for t, _ in lines}) == 1             # all lines of an order arrive together
        assert len({s for _, s in lines}) == len(lines)    # no duplicate SKU within an order
    assert scenario.make_day(skus, seed=3) == rows         # reproducible


@pytest.mark.parametrize("kw", [dict(cols=12, pack="near_out", n_pack=3), dict(cols=12, pack="central", n_pack=5),
                                dict(n_pack=0), dict(pack="side")])
def test_template_refuses_parameters_that_do_not_fit(kw):
    with pytest.raises(ValueError):
        templates.parallel_aisle(**kw)
