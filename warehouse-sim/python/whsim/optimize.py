"""Simulation-based optimisation of the footwear warehouse, in coordinates.

Decision variables (a DESIGN, see whsim.design):
    depot (x, y) m      where pickers start / drop off (packing stations sit next to it)
    cross_aisles [x]    0-2 extra cross aisles (each turns one rack column into an aisle, losing its slots)
    slotting            random (as-is) | class (A/B/C zones) | abc (dedicated by turnover)
and, on the chosen layout, the operating policy: number of pickers and cart size (wave batching).

Stages (python3 -m whsim.optimize):
  1  SCREEN    static objective = mean tour length of the 9.8k REAL historical waves (Picking_Wave.csv)
               on the candidate layout, same nearest-neighbour routing as the simulation (Java, fast):
               1a depot scan over the open floor (heat map), 1b genetic algorithm over all variables.
  2  RANK      the best distinct screened designs + the as-is variants, each simulated on the same
               synthetic days (reference DES, common random numbers); paired differences vs the as-is
               layout with Bonferroni-corrected 95% CIs.
  3  OPERATE   on the recommended layout: pickers x cart size grid -> fewest pickers meeting the service
               targets (on-time >= ON_TIME_MIN %, p95 fulfilment <= P95_MAX_S), then the cart size with the least
               walking.
  4  ROBUST    recommended vs as-is when the (assumed) pick time per line is 50% lower / higher.
Outputs: data/config/designs.json (for AnyLogic CompareLayouts), results/opt/*.csv, reports/optimization.md,
reports/figures/opt_*.png.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import random
import subprocess

from scipy import stats as st

from . import design, scenario
from .cli import DATA, RUN_CONFIG, ROOT, write_designs, write_layouts
from .layout import save

OUT = ROOT / "results" / "opt"
FIG = ROOT / "reports" / "figures"
WAVES = ROOT / "data" / "real" / "waves.csv"
JAVA = pathlib.Path.home() / "AnyLogic" / "anylogic" / "jre" / "bin" / "java"
CLASSES = ROOT / "build" / "classes"
ON_TIME_MIN, P95_MAX_S = 95.0, 7200.0
DAYS = (1, 10)                     # synthetic days used in the DES stages


# ----------------------------------------------------------------------------- evaluation back-ends
def _skus():
    return [(s, w) for s, w, _ in scenario.read_skus(DATA / "skus.csv")]


def _java(*args):
    r = subprocess.run([str(JAVA), "-cp", str(CLASSES), "wh.Evaluate", *map(str, args)], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])


def compile_designs(designs, folder):
    """Writes one layout JSON per design (skipping invalid ones); returns {design_id: (design, path)}."""
    folder.mkdir(parents=True, exist_ok=True)
    skus, out = _skus(), {}
    for d in designs:
        did = design.design_id({**design.BASELINE, **d})
        if did in out:
            continue
        try:
            lay = design.apply_design(d, skus)
        except Exception as e:          # e.g. too few slots after removing rack columns
            print(f"  skip {did}: {e}")
            continue
        path = folder / f"{lay['id']}.json"
        save(lay, path)
        out[did] = ({**design.BASELINE, **d}, path)
    return out


def static_eval(designs, tag):
    """Mean historical-wave tour length (m) of every design: {design_id: (design, mean, p95)}."""
    comp = compile_designs(designs, OUT / "layouts" / tag)
    lst = OUT / f"{tag}_layouts.txt"
    lst.write_text("\n".join(str(p) for _, p in comp.values()) + "\n")
    res = OUT / f"{tag}_static.csv"
    _java("static", lst, WAVES, res)
    by_file = {r["layout_file"]: r for r in csv.DictReader(open(res))}
    return {did: (d, float(by_file[str(p)]["mean_tour_m"]), float(by_file[str(p)]["p95_tour_m"]))
            for did, (d, p) in comp.items()}


def des_eval(designs, tag, config=None, days=DAYS):
    """Reference DES of every design x day: returns rows of runs.csv (dicts)."""
    comp = compile_designs(designs, OUT / "layouts" / tag)
    lst = OUT / f"{tag}_layouts.txt"
    lst.write_text("\n".join(str(p) for _, p in comp.values()) + "\n")
    cfg = OUT / f"{tag}_config.json"
    cfg.write_text(json.dumps(config or RUN_CONFIG, indent=2))
    res = OUT / f"{tag}_des.csv"
    if res.exists():
        res.unlink()
    _java("des", lst, cfg, DATA / "scenarios" / "day_{seed}.csv", DATA / "skus.csv", days[0], days[1], res)
    rows = list(csv.DictReader(open(res)))
    ids = {p.stem: did for did, (d, p) in comp.items()}
    for r in rows:
        r["design"] = ids.get(r["layout"], r["layout"])
    return rows, {did: d for did, (d, p) in comp.items()}


# ----------------------------------------------------------------------------- stage 1: screening
def snap_depot(x, y, cells):
    return list(min(cells, key=lambda p: ((p[0] - x) ** 2 + (p[1] - y) ** 2, p)))


def depot_scan(slotting="abc", step=3):
    """Every `step`-th open cell as depot (no extra aisles): the travel landscape over the floor."""
    cells = design.open_cells()
    pts = cells[::step]
    designs = [{"depot": [round(x, 2), round(y, 2)], "slotting": slotting} for x, y in pts]
    res = static_eval(designs, f"scan_{slotting}")
    return [(d["depot"][0], d["depot"][1], m) for d, m, _ in res.values()]


def ga(generations=14, pop=24, seed=7):
    """Genetic algorithm over (depot, extra cross aisles, slotting); fitness = static mean wave tour (m)."""
    rng = random.Random(seed)
    cells = design.open_cells()
    racks = [round(x, 2) for _, x in design.rack_columns()]
    slots = list(design.SLOTTING_POLICIES)

    def make():
        return {"depot": [round(v, 2) for v in rng.choice(cells)],
                "cross_aisles": sorted(rng.sample(racks, rng.choice([0, 0, 1, 2]))),
                "slotting": rng.choice(slots)}

    def mutate(d):
        d = json.loads(json.dumps(d))
        if rng.random() < 0.7:
            x, y = d["depot"]
            d["depot"] = [round(v, 2) for v in snap_depot(x + rng.gauss(0, 8), y + rng.gauss(0, 12), cells)]
        if rng.random() < 0.3:
            xa = d["cross_aisles"]
            op = rng.choice(["add", "drop", "move"])
            if op == "add" and len(xa) < 2:
                xa.append(rng.choice([r for r in racks if r not in xa]))
            elif op == "drop" and xa:
                xa.pop(rng.randrange(len(xa)))
            elif op == "move" and xa:
                xa[rng.randrange(len(xa))] = rng.choice([r for r in racks if r not in xa])
            d["cross_aisles"] = sorted(xa)
        if rng.random() < 0.15:
            d["slotting"] = rng.choice(slots)
        return d

    def cross(a, b):
        return {"depot": list(rng.choice([a, b])["depot"]), "cross_aisles": list(rng.choice([a, b])["cross_aisles"]),
                "slotting": rng.choice([a, b])["slotting"]}

    population = [dict(design.BASELINE, depot=list(design.BASELINE["depot"]))] + [make() for _ in range(pop - 1)]
    seen, history = {}, []
    for g in range(generations):
        todo = [d for d in population if design.design_id({**design.BASELINE, **d}) not in seen]
        for did, (d, mean, p95) in static_eval(todo, f"ga_g{g:02d}").items():
            seen[did] = (d, mean)
        scored = sorted(((seen[design.design_id({**design.BASELINE, **d})][1], d) for d in population
                         if design.design_id({**design.BASELINE, **d}) in seen), key=lambda t: t[0])
        best = scored[0]
        history.append((g, best[0], sum(s for s, _ in scored) / len(scored)))
        print(f"  generation {g:2d}: best {best[0]:7.2f} m  ({design.design_id({**design.BASELINE, **best[1]})}), "
              f"evaluated {len(seen)} designs")

        def pick():
            a, b = rng.sample(scored, 2)
            return (a if a[0] <= b[0] else b)[1]

        population = [d for _, d in scored[:2]]                 # elitism
        while len(population) < pop:
            child = cross(pick(), pick()) if rng.random() < 0.6 else pick()
            population.append(mutate(child))
    ranked = sorted(seen.items(), key=lambda kv: kv[1][1])
    return ranked, history


# ----------------------------------------------------------------------------- stage 2-4 helpers
def paired(rows, base, kpi):
    """{design: (mean diff vs base, half-width)} over the seeds both share (t, Bonferroni over designs)."""
    by = {}
    for r in rows:
        by.setdefault(r["design"], {})[r["seed"]] = float(r[kpi]) if r[kpi] != "" else math.nan
    m = max(1, len(by) - 1)
    out = {}
    for did, vals in by.items():
        if did == base:
            continue
        d = [vals[s] - by[base][s] for s in vals if s in by[base]]
        n = len(d)
        mean = sum(d) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1)) if n > 1 else math.nan
        t = st.t.ppf(1 - 0.05 / (2 * m), n - 1) if n > 1 else math.nan
        out[did] = (mean, t * sd / math.sqrt(n))
    return out


def means(rows, kpi):
    by = {}
    for r in rows:
        by.setdefault(r["design"], []).append(float(r[kpi]) if r[kpi] != "" else math.nan)
    return {k: sum(v) / len(v) for k, v in by.items()}


def config_with(**kw):
    c = json.loads(json.dumps(RUN_CONFIG))
    for k, v in kw.items():
        if k == "pickers":
            c["resources"]["pickers"] = v
        elif k == "cart":
            c["batching"]["cart_units"] = v
        elif k == "pick_scale":
            p = c["times"]["pick_per_line_s"]
            p["mean"], p["sd"] = p["mean"] * v, p["sd"] * v
    return c


def operate(d, pickers=range(2, 9), carts=(0, 12, 24, 36)):
    rows = []
    for k in pickers:
        for cu in carts:
            rs, _ = des_eval([d], f"op_p{k}_c{cu}", config_with(pickers=k, cart=cu))
            for r in rs:
                r["pickers_cfg"], r["cart_cfg"] = k, cu
            rows += rs
    return rows


# ----------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--generations", type=int, default=14)
    ap.add_argument("--pop", type=int, default=24)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    asis = dict(design.BASELINE)
    asis_ids = {s: design.design_id({**asis, "slotting": s}) for s in design.SLOTTING_POLICIES}

    print("stage 1a: depot scan (as-is and abc slotting)")
    scans = {s: depot_scan(s) for s in ("asis", "abc")}
    with open(OUT / "depot_scan.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slotting", "x", "y", "mean_tour_m"])
        for s, pts in scans.items():
            w.writerows([s, *p] for p in pts)

    print("stage 1b: genetic algorithm")
    ranked, history = ga(a.generations, a.pop)
    with open(OUT / "ga_history.csv", "w", newline="") as f:
        csv.writer(f).writerows([["generation", "best_m", "mean_m"], *history])
    with open(OUT / "ga_designs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["design", "mean_tour_m", "depot_x", "depot_y", "cross_aisles", "slotting"])
        for did, (d, m) in ranked:
            w.writerow([did, f"{m:.3f}", d["depot"][0], d["depot"][1], " ".join(map(str, d["cross_aisles"])), d["slotting"]])
    static_asis = static_eval([{**asis, "slotting": s} for s in design.SLOTTING_POLICIES], "asis")

    print("stage 2: DES ranking with common random numbers")
    finalists, used = [], set()
    for did, (d, m) in ranked:                      # best distinct designs (different depot cell or aisles)
        key = (tuple(d["depot"]), tuple(d["cross_aisles"]))
        if key in used:
            continue
        used.add(key)
        finalists.append(d)
        if len(finalists) == 4:
            break
    cands = [{**asis, "slotting": s} for s in design.SLOTTING_POLICIES] + finalists
    rows, dmap = des_eval(cands, "rank")
    base = asis_ids["asis"]
    kpis = ["pick_m_per_order", "tour_s_mean", "fulfil_mean_s", "fulfil_p95_s", "on_time_pct", "util_pick"]
    diffs = {k: paired(rows, base, k) for k in kpis}
    avg = {k: means(rows, k) for k in kpis}
    # recommended = significantly shortest travel per order among the candidates
    best = min((did for did in dmap if did != base), key=lambda did: avg["pick_m_per_order"][did])
    rec = dmap[best]

    print(f"stage 3: pickers x cart size on {best}")
    op_rows = operate(rec)
    feas = []
    for k in sorted({r["pickers_cfg"] for r in op_rows}):
        for cu in sorted({r["cart_cfg"] for r in op_rows}):
            rs = [r for r in op_rows if r["pickers_cfg"] == k and r["cart_cfg"] == cu]
            ot = sum(float(r["on_time_pct"]) for r in rs) / len(rs)
            p95 = sum(float(r["fulfil_p95_s"]) for r in rs) / len(rs)
            walk = sum(float(r["pick_m_total"]) for r in rs) / len(rs)
            if ot >= ON_TIME_MIN and p95 <= P95_MAX_S:
                feas.append((k, walk, cu, ot, p95))       # fewest pickers, then least walking
    op_choice = min(feas) if feas else None
    with open(OUT / "operate.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(op_rows[0].keys()))
        w.writeheader()
        w.writerows(op_rows)

    print("stage 4: robustness to the assumed pick time")
    robust = {}
    for scale in (0.5, 1.0, 1.5):
        rs, _ = des_eval([asis, rec], f"robust_{scale}", config_with(pick_scale=scale))
        robust[scale] = (means(rs, "fulfil_mean_s"), means(rs, "pick_m_per_order"), paired(rs, base, "fulfil_mean_s"))

    # designs for AnyLogic: as-is (4 storage policies), recommended, runner-up
    runner = next((d for d in finalists if design.design_id({**asis, **d}) != best), None)
    keep = [{**asis, "slotting": s} for s in design.SLOTTING_POLICIES] + [rec] + ([runner] if runner else [])
    write_designs(keep, note="written by whsim.optimize: as-is x 4 storage policies, recommended, runner-up")
    write_layouts(keep)

    summary = dict(asis=asis_ids, static_asis={k: v[1] for k, v in static_asis.items()}, recommended=best,
                   recommended_design=rec, operate_choice=op_choice, kpi_means={k: avg[k] for k in kpis},
                   paired_vs_asis={k: {d: list(v) for d, v in diffs[k].items()} for k in kpis},
                   robust={str(s): {"fulfil_mean_s": v[0], "pick_m_per_order": v[1],
                                    "paired_fulfil": {d: list(x) for d, x in v[2].items()}} for s, v in robust.items()},
                   ga_best=ranked[0][0], ga_evaluated=len(ranked))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("recommended", "operate_choice", "ga_best", "ga_evaluated")}, indent=2))


if __name__ == "__main__":
    main()
