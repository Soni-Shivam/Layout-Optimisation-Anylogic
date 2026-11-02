# WarehouseSim: grid layout → automatically built AnyLogic model

IE305 Simulation Lab. An e-commerce fulfilment warehouse (human pickers, packing stations, multi-SKU orders,
inbound trucks) whose AnyLogic model is **built at start-up from a layout file**. Changing the layout means
changing a JSON file, not the model.

```
 grid of building blocks          compiled layout JSON             generic AnyLogic model (one .alp)
 (template or hand-drawn)  ──▶   nodes, edges, facilities,  ──▶   Main.setup(): load files, size pools,
 python/whsim/templates.py        slots + SKU slotting              draw layout, feed workload into the
 python/whsim/layout.py           data/layouts/*.json               fixed flowchart → KPIs to results/
                                                                    ▲
 input models (teammate) ──▶ data/skus.csv, data/scenarios/day_<seed>.csv, data/config/run_config.json
```

## Quick start

```bash
tools/check.sh          # data + all tests + generate and verify model/WarehouseSim/WarehouseSim.alp
tools/refsim.sh         # expected KPIs from the reference simulator, all layouts x 5 days
```

Then in **AnyLogic 8.9 (PLE is enough)**: open `model/WarehouseSim/WarehouseSim.alp` and run one of:

| Experiment | What it does |
|---|---|
| **Simulation** | One day on `Main.layoutFile` (default `I_v_c0_central_abc`), animated: the layout is drawn from the JSON and worker dots move along the aisles. The console prints a summary at the end of the day. |
| **CompareLayouts** | Every layout in `data/layouts/index.txt` × days 1–5 (30 runs). |
| **StaffPackers** | Packers 2–5 × days 1–5 on the default layout (20 runs). |

Every run (of every experiment) appends one row to `model/WarehouseSim/results/runs.csv` and writes `orders_<layout>_s<seed>.csv`. Summarise with:

```bash
cd python
python3 -m whsim.analyze ../model/WarehouseSim/results/runs.csv --where packers=3 --baseline I_v_c0_central_random   # CompareLayouts
python3 -m whsim.analyze ../model/WarehouseSim/results/runs.csv --by packers --where layout=I_v_c0_central_abc       # StaffPackers
```

Compare with `results/refsim_runs.csv` from `tools/refsim.sh`. The two must agree closely; see "Verification" below.

## The pipeline, file by file

| Step | Code | Output |
|---|---|---|
| 1. Layout candidates | `python/whsim/templates.py` (parametric: flow I/U/L, racks v/h, cross-aisles, packing position) | a `Grid` of tokens |
| 2. Validate + compile | `python/whsim/layout.py` (`validate`, `compile_layout`) | `data/layouts/<id>.json` |
| 3. Workload | `python/whsim/scenario.py` (**placeholder** until the fitted input models are ready) | `data/skus.csv`, `data/scenarios/day_<seed>.csv` |
| 4. Run settings | `python/whsim/cli.py` (`RUN_CONFIG`) | `data/config/run_config.json` |
| 5. Model | `anylogic/build_model.py` + the core `java/src/wh/*.java` | `model/WarehouseSim/WarehouseSim.alp` |
| 6. Analysis | `python/whsim/analyze.py`, `python/whsim/render.py` (layout PNGs in `build/previews/`) | tables, figures |

`python3 -m whsim.cli all|layouts|scenarios|config` regenerates the inputs. `python3 -m whsim.cli check my_grid.txt` validates a hand-drawn grid.

### Grid tokens (one cell = `cell_m` metres, default 1.5 m)

| Token | Meaning | | Token | Meaning |
|---|---|---|---|---|
| `#` | wall / column | | `DI` | inbound dock (outer wall only) |
| `.` | unused floor | | `DO` | outbound dock (outer wall only) |
| `A` | aisle | | `R` | receiving buffer cell |
| `S` | shelf bay with `levels` pick slots | | `PK` | packing station (one per cell) |
| `H` | picker depot (exactly one) | | `G` | outbound staging cell |

Every token except `#`, `.` and `S` is walkable and becomes a node of the aisle graph. Edges join walkable 4-neighbours. A slot is picked from the first walkable neighbour of its bay, in N, S, W, E order. The validator rejects:
- unknown tokens, or docks off the outer wall
- shelves or docks with no walkable neighbour
- walkable cells not connected to the depot
- missing facilities
- fewer slots than SKUs

### Compiled layout JSON (`whsim.layout/1`)

`id, template, params, slotting, cell_m, rows, cols, levels, grid` (rows of tokens), `nodes` (`[r, c, x_m, y_m]`, index = node id), `edges` (`[a, b, length_m]`), `facilities` (`{id, type, r, c, x, y, node}`, ids `DI1, PK2, ...`), `slots` (`{id, r, c, level, node, sku}`), `stats`. **All geometry is decided in Python. AnyLogic only instantiates what this file lists.**

### Workload files (what the input models must produce)

- `data/skus.csv`: `sku,weight,init_qty`. `weight` = relative pick frequency (used for ABC slotting), `init_qty` = opening stock.
- `data/scenarios/day_<seed>.csv`: `t_s,type,id,sku,qty`, sorted by `t_s`. One row per order line (`ORDER`, id = order id, all lines of an order share `t_s`) or per receipt line (`RECEIPT`, id = truck id).
- `data/config/run_config.json`: horizon, carrier cut-offs, promise lead time, staff, walking speeds, receiving buffer size per cell, and the service-time distributions:
  - `pick_per_line_s`
  - `pack_per_order_s` + `pack_per_unit_s` × units
  - `receive_per_line_s`
  - `putaway_handling_s`

  Families: `const, uniform, triangular, exponential, normal (truncated at min), lognormal (mean, sd of the variable), gamma (shape, scale), weibull (shape, scale), empirical (values)`.

The placeholder generator is plain assumptions (NHPP orders, Zipf SKU mix, geometric basket size, an (s, S)-like truck rule). It is documented in `scenario.py`. Replacing it with the fitted models means writing these same files.

## How the model is built at run time (the "translation")

`Main.setup()` runs on start-up:

1. Resolves the files: `layoutIndex ≥ 0` picks a line of `data/layouts/index.txt` (used by the experiments). `{seed}` in `scenarioFile` becomes the seed.
2. `Warehouse.load(...)` parses the layout, run config, day file and SKU master, and **cross-checks them**: every SKU must have a slot and be in the SKU master, and every node must be reachable. Any problem stops the run with a message naming the file and line.
3. Sizes the four resource pools (pickers, packers, receivers, putaway) from the config, or from parameters `nPickers`... if > 0.
4. `drawLayout()` draws every cell and facility label from the JSON (runtime `ShapeRectangle`/`ShapeText`).
5. Creates one `Order` agent per order and one `Receipt` per receipt line, and puts them into the flowchart. Each waits in its arrival delay until its time.

The flowchart is the same for every warehouse:

```
Order:   orderIn → orderArrive (until t) → stockCheck ─ reserved ─────────────→ pickSeize → pickWalk → pickRelease
                                                     └ short → holdWait ──────↗   (picker)  (tour)
         → pack (packer) → staging (until next cut-off) → shipped
Receipt: receiptIn → receiptArrive → receive (receiver) → putSeize → putWalk (dock → slot → dock) → putRelease
         → stored        (stock up + held orders whose lines are now all in stock are released, oldest first)
DayClock → endOfDay (horizon_s) → finishRun(): writes results, finishSimulation()
```

Decisions and times come from the core classes (`java/src/wh/`), embedded unchanged in `Main`:

| Class | Responsibility |
|---|---|
| `Warehouse.planPick` | Nearest-neighbour tour: depot → slots → nearest packing station → depot. Walk at `walk_speed_mps` plus one pick time per line. |
| `Warehouse.planPutaway` | Trip from inbound dock → slot → dock. |
| `Warehouse.packTime` | Pack time: per order + per unit. |
| `Inventory` | `OnHand = opening + put away − picked`. All-or-nothing reservation on arrival. Stock is pickable only after putaway. |
| `Kpi` | Timestamps per order and receipt line, time-weighted levels, and the summary and per-order CSV files. |

**Common random numbers:** every random time is drawn from a stream seeded by (seed, stream, order or receipt index). The same order gets the same pick and pack times on every layout, whatever the event order. Comparisons between layouts are therefore paired, and the CIs of the differences are tight.

**KPIs in `runs.csv`:**
- Fulfilment time (arrival → packed): mean and p95.
- Cycle time (arrival → shipped).
- % packed by the due cut-off.
- Held orders (stock-outs) and mean hold time.
- Pick metres per order, total putaway metres.
- Receiving-buffer max, mean and overflow events.
- Utilisation of each pool.
- Units received, picked and on hand. Backlog at the end of the day.

## Verification (what was checked here, and what was not)

`tools/check.sh` runs all of the following:

- **Python, 15 tests.** Validator rejections, hand-computed tour length on a 7×7 layout, ABC puts fast movers on the cheapest slots, all candidates valid, scenario file format.
- **Java core, 16,000+ checks (`java/test/CoreTest.java`):**
  - JSON parser.
  - Every distribution's sample mean against its theoretical mean.
  - Tiny-layout tour, walk timing and motion.
  - Inventory all-or-nothing reservation.
  - Scenario parsing errors.
  - **Java router = Python router exactly** (length, station, stop order) on every order of day 1 on every layout.
  - **Full days on the reference simulator** for every layout: stock balance, units picked = units of picked orders, timestamps in order, every shipment at the first cut-off after packing, and all receipts put away.
- **AnyLogic model:**
  - Every Java snippet in the model (block parameters, functions, shapes, experiments, plus the embedded core) is compiled against the AnyLogic 8.9.10 engine and Process Modeling Library jars.
  - The `.alp` is loaded and re-written by AnyLogic's own serializer and version converters.
  - The serializer drops only the default `connections` agent-link tags, as for the lab models.

**Not verified here: an actual run inside AnyLogic.** Please run `Simulation` once and check:
- the layout is drawn and the dots move
- the console line at the end of the day
- `CompareLayouts` results against `results/refsim_runs.csv`

Expect close but not identical numbers. AnyLogic may order simultaneous events differently, for example which waiting order gets a freed picker at the same instant.

## v1 modelling assumptions (deliberately simple)

- One zone, single-level shelving, one SKU per slot (no slot capacity limit).
- Single-order picking, FIFO, first free picker.
- The packing queue is pooled across stations. The station only changes the walk.
- An order is released only when every line is in stock (hold policy). Stock counts only after the putaway trip has finished.
- Putaway takes one receipt line per trip.
- No congestion between pickers.
- Shipping happens at fixed carrier cut-offs, with no travel to the outbound dock.
- A day is a terminating run (no warm-up). It starts with opening stock and empty queues.

Each of these is one place in the code, which keeps the next refinements local. Examples: batch picking in `planPick`, wave release in the stock check, picker congestion via an AnyLogic network (pickers moving with `MoveTo`).
