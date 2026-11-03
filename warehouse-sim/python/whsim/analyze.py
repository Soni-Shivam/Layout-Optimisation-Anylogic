"""Summarise runs.csv (AnyLogic: model/WarehouseSim/results/runs.csv, reference sim: results/refsim_runs.csv).

    python3 -m whsim.analyze FILE [--by layout|packers|pickers|...] [--where KEY=VALUE ...] [--baseline GROUP]

Per group: mean and 95% t confidence half-width over the seeds. With a baseline group, also the
paired difference (same seed = same day file and same service-time streams) and its 95% CI.
runs.csv collects every experiment, so filter to one of them with --where, e.g.
    CompareLayouts:  --by layout --where pickers=7 --where cart_units=24
    StaffPickers:    --by pickers --where layout=D40.3_63.1-P3-Xnone-asis
Each (group, seed) must then hold exactly one configuration; otherwise the script stops and says why.
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict

from scipy import stats as st

KPIS = ["fulfil_mean_s", "fulfil_p95_s", "on_time_pct", "pick_m_per_order", "tour_m_mean", "orders_per_tour", "held_orders",
        "util_pick", "util_pack", "recv_buffer_max", "backlog_end"]


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def ci(xs):
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("nan")
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, st.t.ppf(0.975, n - 1) * sd / math.sqrt(n)


def num(v):
    return float(v) if v not in ("", None) else float("nan")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--baseline")
    ap.add_argument("--by", default="layout")
    ap.add_argument("--where", action="append", default=[], help="KEY=VALUE filter (repeatable)")
    a = ap.parse_args(argv)
    rows = read(a.file)
    for w in a.where:
        k, _, v = w.partition("=")
        if not rows or k not in rows[0]:
            raise SystemExit(f"--where: unknown column {k!r}")
        rows = [r for r in rows if r[k] == v]
    if not rows:
        raise SystemExit("no rows left after the --where filters")
    # identical configuration + seed: the last row wins (a re-run); different configurations must not mix
    config = ("layout", "scenario", "pickers", "packers", "receivers", "putaway", "cart_units")
    last = {}
    for r in rows:
        last[tuple(r[k] for k in config) + (r["seed"],)] = r
    groups = defaultdict(dict)
    for r in last.values():
        g, s = r[a.by], r["seed"]
        if s in groups[g]:
            other = groups[g][s]
            diff = [k for k in config if other[k] != r[k]]
            raise SystemExit(f"group {a.by}={g}, seed {s} has runs that differ in {diff}: "
                             f"add --where filters, e.g. --where {diff[0]}={r[diff[0]]}")
        groups[g][s] = r
    print(f"{a.by:28s} n  " + "  ".join(f"{k:>18s}" for k in KPIS))
    for g in sorted(groups):
        rs = list(groups[g].values())
        cells = []
        for k in KPIS:
            m, h = ci([num(r[k]) for r in rs])
            cells.append(f"{m:10.2f} ±{h:6.2f}" if not math.isnan(h) else f"{m:10.2f}        ")
        print(f"{g:28s} {len(rs):2d} " + "  ".join(f"{c:>18s}" for c in cells))
    if a.baseline:
        base = groups.get(a.baseline)
        if not base:
            raise SystemExit(f"baseline {a.baseline!r} not found")
        print(f"\npaired difference vs {a.baseline} (same seeds), mean ± 95% half-width:")
        for g in sorted(groups):
            if g == a.baseline:
                continue
            seeds = sorted(set(groups[g]) & set(base))
            cells = []
            for k in KPIS:
                d = [num(groups[g][s][k]) - num(base[s][k]) for s in seeds]
                m, h = ci(d) if d else (float("nan"), float("nan"))
                sig = "*" if not math.isnan(h) and abs(m) > h else " "
                cells.append(f"{m:+10.2f} ±{h:6.2f}{sig}")
            print(f"{g:28s} {len(seeds):2d} " + "  ".join(f"{c:>18s}" for c in cells))
        print("(* = the 95% CI of the difference excludes 0)")


if __name__ == "__main__":
    main()
