# WarehouseSim: a real footwear warehouse, optimised in coordinates, simulated in AnyLogic

IE305 Simulation Lab, IEOR IIT Bombay. This project models the order-fulfilment warehouse of a footwear manufacturer:
- **Data:** the real WMS extract, Mendeley Data pf2w725pw3, 2023, 122k order lines and 215k picks.
- **Processes:** wave (cart) picking, packing, carrier cut-offs, inbound putaway and stock.
- **Automatic model generation:** the AnyLogic model is built at start-up from a layout JSON.
- **Simulation-based optimisation:** the layout design is optimised in coordinates. That means where the pick-up/drop-off point (depot) sits, where extra cross aisles go, and how SKUs are slotted. Staffing and cart size are optimised too.

```
 real data (data_raw/mendeley)                       design in coordinates (depot x,y; cross aisles x; slotting)
   │ whsim.real_data / input_models                     │ whsim.design  (real building from Storage_Location.csv)
   ▼                                                    ▼
 fitted input models ──▶ skus.csv, day files ──▶  layout JSON (grid, aisle graph, slots)  ◀── whsim.optimize
 (input_models.json)     real-day replays          │                                            (GA + DES ranking)
                                                   ▼
            generic AnyLogic model (model/WarehouseSim/WarehouseSim.alp): Main.setup() reads the files,
            builds the warehouse picture and resource pools, feeds the orders into the fixed flowchart
                                                   │
                                                   ▼  results/runs.csv  ──▶ whsim.analyze, reports/
```

## Reports (start here)

| Report | Content |
|---|---|
| `reports/REPORT.md` | **Final report**: scope, data, model, results, what-ifs, optimisation, recommendation |
| `reports/input_analysis.md` | Input data analysis: cleaning log, summary statistics, fitted distributions with GoF tests, validation of the generator |
| `reports/input_audit.md` | Input data audit against spec §3.1–3.2: data audit (no pick timestamps), independence and seasonality of the daily volume, discrete Anderson–Darling bootstrap, large-sample generator check, SKU-mix drift, picker heterogeneity |
| `reports/validation.md` | The as-is layout model against the real pick locations (tours within 1%) |
| `reports/optimization.md` | The four optimisation stages with figures |

## Run everything

```bash
cd python
python3 -m whsim.cli config          # run settings (data/config/run_config.json)
python3 -m whsim.cli scenarios       # fit the input models, write skus.csv + day files + historical waves
python3 -m whsim.input_report        # reports/input_analysis.md + figures
python3 -m whsim.cli audit           # reports/input_audit.md + figures (checks the input models, ~1 min)
python3 -m whsim.validate            # reports/validation.md
python3 -m whsim.optimize            # simulation-based optimisation (writes designs.json + layouts), ~10 min
python3 -m whsim.opt_report          # reports/optimization.md + figures
cd .. && tools/check.sh              # all tests + generate and verify the AnyLogic model
```

## AnyLogic (8.9, free PLE)

Open `model/WarehouseSim/WarehouseSim.alp` and run one of these experiments:

| Experiment | What it does |
|---|---|
| **Simulation** | One day on `Main.layoutFile`, animated. The default is the as-is warehouse; set `layoutFile` to the recommended design to compare. Worker dots walk the real aisles. Use `Main.realDay = 1..10` to replay a historical day. |
| **CompareLayouts** | Every design in `data/layouts/index.txt` (as-is × 4 storage policies, recommended, runner-up) × synthetic days 1–10, with common random numbers. |
| **ValidateRealDays** | The as-is warehouse on the 10 replayed historical days. |
| **StaffPickers** | 2–8 pickers × days 1–10. |
| **CartSize** | Single-order picking, then 12-, 24- and 36-unit carts × days 1–10. |

Every run appends one row to `model/WarehouseSim/results/runs.csv`. Summarise it with `python3 -m whsim.analyze` and filter one experiment with `--where`. Examples:
- `--where pickers=7 --baseline D40.3_63.1-P3-Xnone-asis`
- `--by pickers --where layout=...`
- `--by cart_units`

`tools/refsim.sh` is not used any more. The optimiser's DES results (`results/opt/*_des.csv`) are the reference-simulator numbers to compare AnyLogic against.

## Layout designs are coordinates

A design is a small dict (see `python/whsim/design.py`). Its id is built from the values, e.g. `D40.3_63.1-P3-Xnone-asis`:

| Key | Meaning |
|---|---|
| `depot` [x, y] m | Pick-up/drop-off point, in the dataset's frame. As-is: (40.3, 63.1), the real central depot. |
| `n_pack` | Packing stations, placed next to the depot. |
| `cross_aisles` [x, …] m | Extra cross aisles. Each turns one rack column into an aisle, and its slots are lost. |
| `slotting` | `asis` = the real storage, i.e. every SKU on the bay it was really picked from most often. Alternatives: `random`, `class` (A/B/C zones by pick frequency) and `abc` (dedicated by turnover). |

The building comes from `Storage_Location.csv`:
- 864 bays.
- 17 picking aisles, 9 m apart.
- 3 cross aisles at x = 6.6, 40.3 and 68.6 m.

It is mapped onto a grid of 5/3 m × 3 m cells, with every bay on its own cell (snapping error ≤ 0.37 m). The rack-free lower-right quarter is used as the dock, receiving and staging area. That placement is an assumption, because the data has no dock positions.

## The model (same flowchart for every layout)

```
Order:   orderIn → orderArrive → stockCheck ─ reserved ─→ pickPool (wait for a cart)  ─────────→ pack → staging → shipped
                                            └ short → holdWait ─↗          ▲ freed when its cart's tour ends
Cart:    Main.dispatch() forms carts (first-fit ≤ cart_units, wave release: full cart or oldest waited max_wait_s)
         tourIn → tourSeize (picker) → tourWalk (nearest-neighbour tour over all the cart's slots → packing → depot) → tourRelease
Receipt: receiptIn → receiptArrive → receive (receiver) → putSeize → putWalk (dock → slot → dock) → putRelease → stored
         (stock up, then held orders whose lines are now in stock are released)
Ticker every tick_s re-checks the wave release; DayClock ends the day at horizon_s and writes the KPIs.
```

The decisions and times come from the core Java in `java/src/wh/`, embedded unchanged in `Main`:
- `Warehouse.formBatch`, `releaseNow` and `planBatch`
- `Inventory`
- `Kpi`

`wh.RefSim` is the same process as a plain-Java event loop. It is used by the optimiser and the tests. Every random time is drawn from a stream seeded by (seed, stream, order index), so comparisons between designs are paired (common random numbers).

## Verification (`tools/check.sh`)

- **Python tests:**
  - Layout compiler and validator, rectangular cells, slotting policies.
  - Real-building geometry: every bay on its own cell.
  - Designs and cross aisles.
  - Input files: format, determinism, exact replay of a real day.
- **Java `CoreTest`:**
  - JSON parser.
  - Every distribution: sample mean against its formula, and the truncated-normal tail.
  - Independence of the random streams.
  - Batching: first-fit, multi-trip orders, wave release.
  - Inventory.
  - **Java router = Python router to the last bit on every order.**
  - **Full reference-sim days**: stock balance, every picked order on exactly one cart, shipments at cut-offs.
- **AnyLogic model:** every Java snippet in it is compiled against the AnyLogic 8.9.10 engine jars, and the `.alp` is loaded and re-written by AnyLogic's own serializer and converters.
- **Not possible here:** a run inside the AnyLogic IDE. Please run **Simulation** once and **ValidateRealDays**, then compare with `results/opt/`.
