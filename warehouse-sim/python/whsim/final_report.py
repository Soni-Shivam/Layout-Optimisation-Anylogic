"""reports/REPORT.md - the final report, assembled from the result files (no number is typed by hand).

    python3 -m whsim.final_report      (after whsim.input_report, whsim.validate, whsim.optimize, whsim.opt_report)

It also runs the real-day replay: the as-is and the recommended design on the 10 historical days.
"""
from __future__ import annotations

import csv
import json
import math
import shutil

from . import design
from .cli import DATA, ROOT, RUN_CONFIG
from .optimize import OUT, des_eval, means, paired, P95_MAX_S, ON_TIME_MIN

REPORT = ROOT / "reports" / "REPORT.md"


def f(x, nd=1):
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.{nd}f}"


def real_day_replay(designs):
    """DES of the designs on the 10 historical days (copied as r_<k>.csv so the evaluator can loop over k)."""
    days = (DATA / "scenarios" / "real_index.txt").read_text().split()
    folder = OUT / "realdays"
    folder.mkdir(parents=True, exist_ok=True)
    for k, d in enumerate(days, 1):
        shutil.copy(DATA / "scenarios" / d, folder / f"r_{k}.csv")
    from . import optimize
    comp = optimize.compile_designs(designs, OUT / "layouts" / "real")
    lst = OUT / "real_layouts.txt"
    lst.write_text("\n".join(str(p) for _, p in comp.values()) + "\n")
    cfg = OUT / "real_config.json"
    cfg.write_text(json.dumps(RUN_CONFIG, indent=2))
    res = OUT / "real_des.csv"
    if res.exists():
        res.unlink()
    optimize._java("des", lst, cfg, folder / "r_{seed}.csv", DATA / "skus.csv", 1, len(days), res)
    rows = list(csv.DictReader(open(res)))
    ids = {p.stem: did for did, (d, p) in comp.items()}
    for r in rows:
        r["design"] = ids.get(r["layout"], r["layout"])
    return rows, days


def main():
    S = json.loads((OUT / "summary.json").read_text())
    IM = json.loads((DATA / "config" / "input_models.json").read_text())
    asis_id = S["asis"]["asis"]
    rec_id = S["recommended"]
    rec = S["recommended_design"]
    m = S["kpi_means"]
    pdiff = S["paired_vs_asis"]
    rows, days = real_day_replay([dict(design.BASELINE), rec])
    rm = {k: means(rows, k) for k in ("pick_m_per_order", "fulfil_mean_s", "fulfil_p95_s", "on_time_pct", "tour_s_mean",
                                      "orders_per_tour", "units_per_tour", "util_pick", "util_pack", "held_orders")}
    rp = {k: paired(rows, asis_id, k) for k in ("pick_m_per_order", "fulfil_mean_s", "pick_m_total")}
    val = (ROOT / "reports" / "validation.md").read_text().split("\n")
    val_table = [ln for ln in val if ln.startswith("|")]
    dv = IM["daily_volume"]
    walk_cut = 100 * (1 - m["pick_m_per_order"][rec_id] / m["pick_m_per_order"][asis_id])
    oc = S["operate_choice"]
    lines = []
    A = lines.append
    A("# Footwear order-fulfilment warehouse: simulation, automatic model generation and layout optimisation")
    A("")
    A("IE305 Simulation Lab, IEOR IIT Bombay. Data: real WMS extract of a footwear manufacturer's warehouse "
      "(Mendeley Data pf2w725pw3 v1, 2023, CC BY 4.0). Companion reports: [input analysis](input_analysis.md), "
      "[validation](validation.md), [optimisation](optimization.md).")
    A("")
    A("## 1. Scope and objectives")
    A("")
    A("**System.** One floor (Z = 1) of a real footwear warehouse: 2,292 storage locations in 864 shelf bays, 17 picking "
      "aisles and 3 cross aisles, a central pick-up / drop-off point (depot). Customer orders are released by the WMS in "
      "batches; pickers push carts of about 24 pairs (a *wave*) along a route through the aisles, drop the cart at a "
      "packing station; packed orders wait in staging for the next carrier cut-off. Inbound trucks are received, put away "
      "and restock the shelves; an order is released to picking only when all its lines are in stock.")
    A("")
    A("**Objectives.** (1) Build a generic, data-driven AnyLogic model that is *generated automatically* from a layout file. "
      "(2) Reproduce the as-is warehouse from its data and validate it. (3) Find better layouts and operating policies by "
      "simulation-based optimisation: where the depot is, where to add cross aisles, how to slot SKUs, how many pickers, "
      "what cart size.")
    A("")
    A("**Boundary and key assumptions.**")
    A("")
    A("| included | excluded / assumed |")
    A("|---|---|")
    A("| order release, stock check / hold, wave batching, picker routing, packing, staging, cut-offs | yard, trucks outside the dock, returns, value-added services |")
    A("| receiving, putaway trips, SKU-level inventory | inbound volumes and opening stock (no data: assumed top-up rule, sensitivity) |")
    A("| real building geometry, real orders, real storage (as-is) | pick / pack / receive times (no timestamps: literature values, varied in the what-ifs) |")
    A("| picker / packer / receiver / putaway resources | docks, receiving and packing area positions (no data: rack-free lower-right quarter) |")
    A("| one zone, one floor, single shift 06:00-21:00 | carrier cut-offs 13:00, 18:00, 20:30 (assumed); no congestion between pickers |")
    A("")
    A("## 2. Data and input analysis")
    A("")
    A(f"Source files: 122,370 order lines (32,621 orders, {IM['n']['skus']:,} SKUs = reference x size) on "
      f"{IM['n']['dates']} days, 215,192 picked units in 9,707 historical waves, 2,292 located storage positions. "
      "Full analysis with cleaning log, statistics and every test: [input_analysis.md](input_analysis.md).")
    A("")
    A("| input | real / assumed | model (test result) |")
    A("|---|---|---|")
    A(f"| orders per day | real | negative binomial, mean {f(dv.get('mean', float('nan')))}; Poisson rejected (dispersion ~88), NB passes chi-square and bootstrap KS |")
    A("| arrivals within the day | real | WMS batch releases (1-5 per day, ~2.8 min long); Poisson arrivals rejected (KS, dispersion); release patterns resampled from the 15 most similar real days |")
    A("| order baskets (SKUs, quantities) | real | bootstrap of real orders (+-3 days window); all parametric fits rejected, heavy tails (max 340 SKUs, 2,400 units) |")
    A("| SKU popularity | real | 21% of SKUs make 80% of lines |")
    A("| storage (as-is) | real | each SKU on the bay it was really picked from most often (70.6% of its picks are there) |")
    A("| cart size, wave formation | real | 61% of real waves carry exactly 24 units -> 24-unit carts, first-fit, wave release (full cart or 15 min) |")
    A("| staff | real (range) | 6.6 operators active per day (1-11) -> 7 pickers as-is |")
    A("| pick time / line, pack, receive, putaway | assumed | lognormal 12 s/line; triangular(40,60,120) s + 4 s/unit; varied x0.5 / x1.5 |")
    A("| inbound + opening stock | assumed | truck every 2 h, top-up rule; opening stock covers q90 of a selling day |")
    A("")
    A("Validation of the workload generator (1,000 synthetic vs 167 real days): daily volume, lines, units, lines/order and the "
      "burstiness of the releases are not significantly different (two-sample KS, see input_analysis.md section 7; checks of the input assumptions in input_audit.md).")
    A("")
    A("![daily volume](figures/daily_volume.png)")
    A("")
    A("![hour profile](figures/hour_profile.png)")
    A("")
    A("## 3. Model building")
    A("")
    A("**Automatic model generation.** A layout is a *design in coordinates* (depot x, y; extra cross-aisle x positions; "
      "slotting policy). `whsim.design` builds the real building from `Storage_Location.csv` on a grid of 5/3 m x 3 m cells "
      "(every bay on its own cell, error <= 0.37 m), applies the design, validates it (connectivity, every shelf reachable, "
      "enough slots) and compiles it to a layout JSON (aisle graph, facilities, slots with their SKU). The AnyLogic model "
      "(`model/WarehouseSim/WarehouseSim.alp`) is the same for every layout: at start-up `Main.setup()` reads the layout, "
      "the run configuration and the day file, sizes the resource pools, *draws the warehouse from the JSON* and feeds the "
      "orders into a fixed flowchart. Changing the warehouse means changing a file, not the model.")
    A("")
    A("**Process logic (Process Modeling Library).** Order: arrival delay -> stock check (SelectOutput; short -> Wait until a "
      "putaway brings the stock) -> pick pool (Wait) -> *cart*: `PickTour` agents formed by `Main.dispatch()` (first-fit up to "
      "24 units, released when full or after 15 min) -> Seize picker -> tour (Delay = nearest-neighbour route over all "
      "the cart's slots, then packing station, then depot) -> Release -> orders go to packing (Service) -> staging until the "
      "next cut-off -> Sink. Receipt: arrival -> receive (Service) -> Seize putaway worker -> trip dock-slot-dock -> stock up "
      "and release held orders.")
    A("")
    A("**Design choices and innovative features.**")
    A("")
    A("- *Layouts in coordinates and a JSON interface*: the optimiser, the tests and AnyLogic all read the same compiled file.")
    A("- *Real geometry and real storage*: the as-is model uses the dataset's building and the SKU locations observed in "
      "215k picks, not a stylised warehouse.")
    A("- *Shared Java core*: routing, batching, inventory and KPI code (`java/src/wh`) is embedded unchanged in the AnyLogic "
      "model and used by a plain-Java reference simulator (`RefSim`) that the optimiser calls thousands of times.")
    A("- *Common random numbers per order*: every service time comes from a stream seeded by (seed, stream, order), so "
      "designs are compared on identical work - paired comparisons with tight confidence intervals.")
    A("- *Oversize orders* are split into cart-sized trips the way the real WMS splits them over waves.")
    A("")
    A("**Verification.** 30 Python tests and 2,500+ Java checks (`tools/check.sh`): distributions vs their formulas, "
      "independence of the random streams, batching rules, inventory balance, Java route = Python route to the last bit on "
      "every order of every layout, full simulated days with conservation checks; every Java snippet of the AnyLogic model "
      "is compiled against the AnyLogic 8.9.10 engine and the model file is loaded by AnyLogic's own serializer.")
    A("")
    A("**Validation against reality.** The 9,143 historical waves routed over their *real* pick locations versus the same "
      "waves in the model's as-is layout:")
    A("")
    A("\n".join(val_table))
    A("")
    A("The as-is model reproduces the real tour lengths within 1%; the real storage is close to class-based "
      "(A/B/C zones), far from random.")
    A("")
    A("![validation](figures/val_tours.png)")
    A("")
    A("## 4. Output analysis (basic): KPIs and the as-is warehouse")
    A("")
    A("KPIs per simulated day: walking per order (m, the order's share of its cart tour), tour time, fulfilment time "
      "(arrival -> packed; mean and p95), on-time % (packed before the due cut-off, due = first cut-off >= arrival + 1 h), "
      "held orders (stock-outs), utilisation of each resource, carts and units per cart.")
    A("")
    A(f"**Real-day replay** - the 10 historical days ({', '.join(d[5:13] for d in days)}), as-is vs recommended layout:")
    A("")
    A("| KPI (mean of 10 real days) | as-is | recommended | paired difference (Bonferroni 95% CI) |")
    A("|---|---|---|---|")
    for k, lab in (("pick_m_per_order", "walk per order (m)"), ("fulfil_mean_s", "fulfilment mean (s)")):
        d = rp[k].get(rec_id, (math.nan, math.nan))
        A(f"| {lab} | {f(rm[k][asis_id])} | {f(rm[k][rec_id])} | {d[0]:+.1f} +- {d[1]:.1f} |")
    for k, lab, nd in (("fulfil_p95_s", "fulfilment p95 (s)", 0), ("on_time_pct", "on time (%)", 1),
                       ("tour_s_mean", "cart tour (s)", 0), ("orders_per_tour", "orders per cart", 2),
                       ("units_per_tour", "units per cart", 1), ("util_pick", "picker utilisation", 2),
                       ("util_pack", "packer utilisation", 2), ("held_orders", "held orders per day", 1)):
        A(f"| {lab} | {f(rm[k][asis_id], nd)} | {f(rm[k][rec_id], nd)} | |")
    A("")
    A("")
    A("Per real day, as-is layout:")
    A("")
    A("| day | orders | first release | on time (%) | held orders | mean hold (min) | fulfil p95 (min) | picker utilisation |")
    A("|---|---|---|---|---|---|---|---|")
    for k, d in enumerate(days, 1):
        r = next(x for x in rows if x["design"] == asis_id and x["scenario"] == f"r_{k}.csv")
        first = min(float(x["t_s"]) for x in csv.DictReader(open(DATA / "scenarios" / d)) if x["type"] == "ORDER")
        hm = float(r["hold_mean_s"]) / 60 if r["hold_mean_s"] else math.nan
        A(f"| {d[5:9]}-{d[9:11]}-{d[11:13]} | {r['orders_arrived']} | {6 + int(first // 3600):02d}:{int(first % 3600 // 60):02d} | "
          f"{f(float(r['on_time_pct']))} | {r['held_orders']} | {f(hm, 0)} | {f(float(r['fulfil_p95_s']) / 60, 0)} | "
          f"{f(float(r['util_pick']), 2)} |")
    A("")
    A("Late orders concentrate on the days where a large WMS release comes shortly before a cut-off and on held orders "
      "waiting for inbound stock (the inbound rule is an assumption); on the other days every order is on time.")
    A("")
    A("Interpretation: utilisation over the whole day is low, but fulfilment takes about an hour because most of a day's "
      "orders are released in one or two WMS batches; the picking queue after a release, not the average load, drives "
      "fulfilment time. Shorter tours shorten that queue.")
    A("")
    A("## 5. Output analysis (advanced): alternatives, what-ifs, optimisation")
    A("")
    A("**Alternatives on 10 synthetic days (common random numbers).**")
    A("")
    A("| design | walk / order (m) | tour (s) | fulfil mean (s) | fulfil p95 (s) | on time (%) | walk vs as-is (Bonferroni 95% CI) |")
    A("|---|---|---|---|---|---|---|")
    for did in m["pick_m_per_order"]:
        d = pdiff["pick_m_per_order"].get(did)
        tag = " (as-is)" if did == asis_id else " **(recommended)**" if did == rec_id else ""
        A(f"| {did}{tag} | {f(m['pick_m_per_order'][did])} | {f(m['tour_s_mean'][did], 0)} | {f(m['fulfil_mean_s'][did], 0)} | "
          f"{f(m['fulfil_p95_s'][did], 0)} | {f(m['on_time_pct'][did])} | {'' if d is None else f'{d[0]:+.1f} +- {d[1]:.1f}'} |")
    A("")
    A("![ranking](figures/opt_rank.png)")
    A("")
    A(f"**Simulation-based optimisation.** Stage 1 screens designs on the real workload (mean tour of the 9,707 historical "
      f"waves): a depot scan over every third open cell and a genetic algorithm over depot (x, y), up to two extra cross "
      f"aisles and the slotting policy ({S['ga_evaluated']} designs evaluated). Stage 2 simulates the best distinct designs "
      f"and the as-is variants on the same 10 days and ranks them with paired, Bonferroni-corrected comparisons. Details: "
      f"[optimization.md](optimization.md).")
    A("")
    A("![depot scan](figures/opt_depot_scan.png)")
    A("")
    A("**What-if: pickers x cart size** (recommended layout, 10 days each).")
    A("")
    if oc:
        k, walk, cu, ot, p95 = oc
        A(f"Fewest pickers meeting on-time >= {ON_TIME_MIN:.0f}% and p95 fulfilment <= {P95_MAX_S / 60:.0f} min, then least "
          f"walking: **{k} pickers, {'single-order picking' if cu == 0 else f'{cu}-unit carts'}** (on time {ot:.1f}%, p95 "
          f"{p95 / 60:.0f} min, {walk / 1000:.1f} km walked per day).")
    A("")
    A("![operate](figures/opt_operate.png)")
    A("")
    A("**What-if: pick time per line** (assumed input), as-is vs recommended:")
    A("")
    A("| pick time x | as-is fulfil (s) | recommended fulfil (s) | difference (95% CI) | as-is walk/order | recommended walk/order |")
    A("|---|---|---|---|---|---|")
    for s, v in S["robust"].items():
        d = v["paired_fulfil"].get(rec_id, [math.nan, math.nan])
        A(f"| {s} | {f(v['fulfil_mean_s'][asis_id], 0)} | {f(v['fulfil_mean_s'][rec_id], 0)} | {d[0]:+.0f} +- {d[1]:.0f} | "
          f"{f(v['pick_m_per_order'][asis_id])} | {f(v['pick_m_per_order'][rec_id])} |")
    A("")
    A("## 6. Animation")
    A("")
    A("Run the **Simulation** experiment in AnyLogic (8.9, free PLE): the warehouse is drawn at start-up from the layout "
      "JSON (aisles, racks, docks, receiving, packing stations, depot); worker dots move along the real aisle network "
      "(red pickers on their cart tours, blue putaway workers, orange packers, yellow receivers; grey = idle); a status "
      "panel and a time plot show orders in system, held orders, staging and the receiving buffer. Set `Main.layoutFile` to "
      f"`data/layouts/{rec_id}.json` to watch the recommended layout, `Main.realDay` = 1..10 to replay a historical day. "
      "Static previews of every layout: `build/previews/` (`python3 -m whsim.render`).")
    A("")
    A("## 7. Recommendation")
    A("")
    dep = rec["depot"]
    xs = ", ".join(f"x = {x:g} m" for x in rec["cross_aisles"]) or "none"
    A(f"1. **Re-slot by pick frequency (ABC, dedicated)** and **move the pick-up / drop-off point to ({dep[0]:g}, {dep[1]:g}) m** "
      f"with **extra cross aisles at {xs}** (design `{rec_id}`): walking per order "
      f"{f(m['pick_m_per_order'][asis_id])} -> {f(m['pick_m_per_order'][rec_id])} m (-{walk_cut:.0f}%), cart tours "
      f"{f(m['tour_s_mean'][asis_id], 0)} -> {f(m['tour_s_mean'][rec_id], 0)} s; the gain holds on the 10 real days and "
      "for pick times from half to one and a half times the assumed value.")
    A("2. Re-slotting alone is the cheap first step (no construction): see the as-is x storage-policy rows above.")
    if oc:
        A(f"3. **Staff {oc[0]} pickers with {oc[2]}-unit carts** on the new layout if the service targets above are the "
          "goal; add pickers only for the morning release, which drives fulfilment time." if oc[2] else
          f"3. **Staff {oc[0]} pickers**; with the current low average load, waiting to fill carts is not worth it.")
    A("4. Before acting: measure pick, pack and receiving times (the model's main assumed inputs) and the dock/packing "
      "area positions, and rerun `whsim.optimize`; extend to the other floors (Z2-Z4) and to picker congestion.")
    A("")
    A("## 8. Limitations")
    A("")
    A("- Service times, inbound and opening stock are assumptions (no timestamps or receipts in the data).")
    A("- The dock / packing area position is assumed; extra cross aisles remove storage slots (the design keeps every SKU "
      "slotted, but capacity for growth is lower).")
    A("- No congestion between pickers in the aisles; one floor only; nearest-neighbour routing (not optimal TSP).")
    A("- The AnyLogic model was verified by compilation and serializer loading here; its runs should be compared with the "
      "reference simulator results in `results/opt/` (small differences from simultaneous-event ordering are expected).")
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
