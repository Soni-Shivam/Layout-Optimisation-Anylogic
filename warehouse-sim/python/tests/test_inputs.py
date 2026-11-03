"""Input models: cleaning rules, SKU ids and the workload files the simulation reads."""
import csv

import numpy as np
import pytest

from whsim import input_models as im
from whsim import real_data as rd
from whsim import scenario
from whsim.cli import DATA, RUN_CONFIG


def test_sku_id_and_half_sizes():
    assert rd.sku_id("8N10W9 ", 9.0) == "8N10W9_9"
    assert rd.sku_id("8N10W9", 9.5) == "8N10W9_9.5"
    assert list(rd.fix_size([105, 9, 9.5, 35, 235])) == [10.5, 9, 9.5, 3.5, 235]   # C3: '105' = 10.5


def check_day_file(path, skus):
    rows = scenario.read_day(path)
    assert rows, path
    assert [r[0] for r in rows] == sorted(r[0] for r in rows), "rows sorted by t_s"
    orders = {}
    for t, typ, i, sku, q in rows:
        assert typ in ("ORDER", "RECEIPT") and sku in skus and q >= 1 and float(q).is_integer()
        assert 0 <= t < RUN_CONFIG["horizon_s"]
        if typ == "ORDER":
            orders.setdefault(i, []).append((t, sku))
    for lines in orders.values():
        assert len({t for t, _ in lines}) == 1            # all lines of an order arrive together
        assert len({s for _, s in lines}) == len(lines)   # one line per SKU
    return orders


@pytest.mark.parametrize("name", [f"day_{k}.csv" for k in range(1, 11)] + ["real_index"])
def test_day_files_obey_the_format(name):
    skus = {s for s, _, _ in scenario.read_skus(DATA / "skus.csv")}
    if name == "real_index":
        for day in (DATA / "scenarios" / "real_index.txt").read_text().split():
            check_day_file(DATA / "scenarios" / day, skus)
    else:
        check_day_file(DATA / "scenarios" / name, skus)


def test_skus_and_waves_consistent():
    skus = scenario.read_skus(DATA / "skus.csv")
    assert len(skus) == 2515
    assert abs(sum(w for _, w, _ in skus) - 1) < 2e-5        # 2,515 shares written with 8 decimals
    assert all(q >= 2 for _, _, q in skus)
    names = {s for s, _, _ in skus}
    with open(im.WAVES_CSV) as f:
        waves = list(csv.DictReader(f))
    assert len(waves) == 9707
    assert all(set(w["skus"].split()) <= names for w in waves)


def test_synthetic_day_is_deterministic_per_seed():
    a = im.make_synthetic_day(3)
    b = im.make_synthetic_day(3)
    c = im.make_synthetic_day(4)
    assert a == b and a != c


def test_real_day_replays_the_data():
    lines, _ = rd.load_lines()
    day = "2023-03-06"
    sel = lines[lines.created.dt.normalize() == np.datetime64(day)]
    rows = im.make_real_day(day)
    orders = {r[2] for r in rows if r[1] == "ORDER"}
    units = sum(r[4] for r in rows if r[1] == "ORDER")
    assert len(orders) == sel.order.nunique()
    assert units == int(sel.qty.sum())
