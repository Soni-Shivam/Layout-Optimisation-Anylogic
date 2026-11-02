# E-commerce Fulfilment Warehouse: Simulation with Automatic Model Generation (Spec v0.2)

IE305 Simulation Lab, Shivam Soni and Siddhesh Phadke. This spec replaces v0.1. The scope is now the **e-commerce each-picking** warehouse (human pickers, packing stations, multi-SKU baskets). It reviews `IE305_Warehouse_Simulation_Project_Plan.docx` and keeps its core: grid → JSON → runtime-built AnyLogic model → candidate comparison. It cuts or defers the parts that came from the old pallet/forklift proposal. **Constraint: free AnyLogic (PLE) only.**

---

## 0. Review of the docx: keep, change, cut

| Docx item | Verdict | Reason |
|---|---|---|
| Layout generator ≠ model generator; JSON is the interface | **Keep** | Correct and central |
| Runtime (Java) construction from JSON, not one .alp per layout | **Keep** | It is also the only route that lets PLE run many layouts unattended (§5) |
| Manual-vs-generated equivalence test (11.3) | **Keep, make it a milestone gate** | Best single proof of the contribution |
| Common random numbers, fixed scenario files | **Keep** | — |
| "Forecasts are not distributions", label assumed uncertainty | **Keep** | — |
| Inventory balance I_s(t) | **Keep** | It couples the two streams |
| Forklifts as the main movers, charging, MTBF/MTTR, carbon KPI | **Cut from v1** | Each-picking uses walking pickers with carts. Forklifts appear only in inbound putaway, as a simple pool. Breakdowns and charging are v2. |
| Dock counts 12/18/24, loading strategy "by destination" | **Cut** | It is a pallet-terminal factor. Replace it with **carrier cut-off times** (§1) |
| Hierarchical objective "min forklifts + workers" first | **Change** | Stage A: layout (pick distance / cycle time). Stage B: **min pickers + packers** s.t. cut-off service level (§7) |
| Grid codes DI/DO/A/S/PK/G/C/#/. | **Change slightly** | Split `PK` (packing) from pick faces. Storage = rack *modules* with an orientation, not single cells (§4.2) |
| Mendeley + B2FIND datasets | **Keep, but define their roles** | Neither has inbound receipts or real e-commerce baskets. Each one covers a different input (§3) |
| KS + Chi-square | **Change** | KS with estimated parameters is invalid. Use parametric-bootstrap KS / Anderson–Darling + Q-Q (§3.3) |
| Full factorial of 12 factors | **Cut** | Screen with a fractional / one-factor design. Only the layout and staffing factors go to search |

---

## 1. Frozen system (v1)

One rectangular building, one pick zone, single-level shelving, one product class, one day = one terminating replication (e.g. 16 h of order arrivals + drain).

```
INBOUND  truck → DI dock → receiving buffer → receive/check (receivers) → putaway (putaway pool, cart/forklift) → pick face (shelf slot)
OUTBOUND order → order pool → release (immediate | wave every W min | batch of B orders)
         → picker + cart: route over required slots (S-shape | largest-gap | nearest-neighbour+2-opt)
         → packing station queue → pack (packer) → outbound staging G → departs at next carrier cut-off at DO
SHARED   SKU on-hand inventory · slot occupancy · receiving buffer · picker / packer / receiver / putaway pools
```

**Coupling rules (identical for all layouts):**
- `OnHand_s(t) = I_s(0) + PutAway_s(0,t) − Picked_s(0,t)`. Stock that is received but not yet put away is not pickable.
- An order is released only when all its lines are available (**hold policy**). Held orders are released FIFO when putaway completes. KPIs: held-order count and hold time.
- Putaway goes to the SKU's assigned slot(s). If a slot is full, the unit goes to an overflow slot (nearest free), and the overflow count is recorded.
- **Carrier cut-offs** (e.g. 10:00, 14:00, 18:00, 22:00): an order is *on time* if it reaches staging before the first cut-off after `arrival + promise window`. This replaces "due loading slot".

**Fixed vs stochastic vs decided:**

| Fixed input | Stochastic (from data) | Design decision | Operational policy |
|---|---|---|---|
| Footprint, walls, columns, DI/DO positions | Order arrivals λ(t) (hour × weekday) | Rack module positions and orientation | Release: immediate / wave / batch |
| Rack module size, slots per module | Lines per order, units per line, SKU choice, co-occurrence | SKU → slot (random / ABC by pick frequency / COI) | Picker routing heuristic |
| #packing stations (v1) | Pick time per line, pack time per order | Packing station positions (v2) | Picker assignment: FIFO / nearest |
| Initial inventory per SKU | Inbound truck times, delay, units per truck | Cross-aisle count / aisle orientation | Packing station choice: shortest queue |
| Walk speed (range) | Receive and putaway times | (Stage B) #pickers, #packers, #receivers | — |

---

## 2. Modules and file interfaces

| # | Module | Tech | Reads | Writes |
|---|---|---|---|---|
| M-A | Data pipeline | Python (pandas, SciPy) | `data/raw/*` | `data/distributions/*.json`, fit report |
| M-B | Scenario generator | Python | distributions | `data/scenarios/day_<seed>.csv` (fixed once, layout-independent) |
| M-C | Layout generator + compiler + validator | Python (networkx) | template/params | `configurations/<cand>.json` (grid + compiled geometry + slotting + distance matrix) |
| M-D | Generic model + runtime builder | AnyLogic PLE + Java | `<cand>.json`, `day_<seed>.csv`, `run.json` | `results/runs.csv`, `results/orders_<run>.csv` |
| M-E | Job bridge ("the API") | Java (in AnyLogic) + Python | `jobs/pending/*.json` | `jobs/done/*.json` |
| M-F | Analysis / optimiser | Python | results | rankings, CIs, next jobs |
| M-G (optional) | Static .alp exporter | Python `alpgen.py` (already exists) | `<cand>.json` | `Warehouse_<cand>.alp` with drawn markup, for demo |

**One owner for the JSON schemas** (`layout`, `scenario`, `run`, `job`, `result`), versioned in `schemas/`.

---

## 3. Data: which public datasets feed which input

No single public dataset covers the whole warehouse, so the plan below is to **assemble it from several sources and label each input as real or assumed.** This is normal practice and the report should say so explicitly.

| Input | Source | Real / assumed | What you extract |
|---|---|---|---|
| **Order arrivals, baskets, SKU popularity** | **UCI Online Retail II** (CC BY 4.0, ~1.07 M lines, 2009–2011, `Invoice, StockCode, Quantity, InvoiceDate, CustomerID`) | Real | λ(hour, weekday); lines/order; units/line; SKU frequency (ABC); co-occurrence. Drop cancellations (`C…` invoices), non-product codes (POST, M, …) and wholesale outliers (qty cap at a percentile) |
| Basket sensitivity (optional) | **Instacart Market Basket** (Kaggle) | Real | Lines/order and co-occurrence only. It has hour-of-day but no timestamps, so do not use it for arrivals |
| **Pick time per line, picker performance, real layout** | **Mendeley "Order Picking Dataset from a Footwear Manufacturing Company"** (CC BY 4.0; WMS-derived, with timestamps, operators, picking waves, Cartesian storage locations, routing) | Real | Time per pick line (after removing travel = timestamp gap − distance/speed), operator variability. Also a **real layout to reproduce as a JSON test case**. Files must be inspected first (§3.1) |
| **Routing / layout verification** | **KIT benchmark instances for manual order picking** (CC BY 4.0, 2 GB; NetworkX layouts, storage assignments, order streams per shift, reference solutions) | Benchmark | Rebuild the rectangular layouts with our compiler. Check that our route lengths match their reference solutions. Use their order streams as a second demand scenario |
| **Inbound truck delay vs schedule** | **USAID SCMS Delivery History** (data.gov / Kaggle; scheduled vs actual delivery dates, line quantities). Verify the fields on download | Real (different industry) | Distribution of `actual − scheduled` delay in days. Used as a **shape** for delay, rescaled to hours |
| **Inbound quantities and timing** | Replenishment rule driven by the demand stream | **Assumed** (documented) | Per SKU, periodic review (R, S): trucks arrive daily at scheduled slots plus the fitted delay; quantity = order-up-to minus position. That gives receipts consistent with demand, with no procurement model |
| Pack time, receive time, putaway time | Literature values (e.g. pack 30–90 s/order, receive per unit) | **Assumed** | Triangular/lognormal with documented sources, plus sensitivity runs |
| Walk speed | Literature (~0.8–1.2 m/s with cart) | Assumed | Uniform range |

### 3.1 Data audit (week 1)

For each dataset: download it, list the files and columns, count rows, check the time span and timestamp resolution, and find missing values. Write it all into `data/DATA_DICTIONARY.md`. The Mendeley record's file list does not show on the landing page, so **check before you rely on it** that it really has line-level pick timestamps. If it does not, pick time becomes an assumed input as well.

### 3.2 Input modelling procedure (per input)

1. **Clean**: duplicates, cancellations, impossible values, timezone.
2. **Stationarity**: counts per hour × weekday. Test for equal rates (χ² / dispersion index). If they differ, fit an **NHPP** with a piecewise-constant λ(t). Check that inter-arrivals within one hour bucket are exponential: if they are, Poisson-within-bucket is supported by the data, not assumed.
3. **Independence**: lag-1 autocorrelation plot / runs test before i.i.d. fitting.
4. **Fit** candidates (Exp, Gamma, Lognormal, Weibull; discrete: Poisson, Geometric, NegBin, empirical). Rank them with **AIC/BIC**.
5. **Goodness of fit**: Q-Q / P-P plots, **Anderson–Darling**, **parametric-bootstrap KS** (because the parameters are estimated), χ² for discrete inputs with expected count ≥ 5 per bin.
6. **Fallback**: empirical resampling when no family passes. Keep it as a baseline in any case.
7. **Store** in `distributions/*.json`: family, params, n, window, test p-values, source, real/assumed flag.
8. You can reuse `code-masala/anylogic/tools/fit_distributions.py` from Lab 6.

### 3.3 Basket generator (the e-commerce part)

Pick one of these, from simplest to most realistic, and compare them in the input validation:
- **B1**: lines ~ fitted discrete; SKUs drawn independently, ∝ popularity. Ignores co-occurrence.
- **B2**: **bootstrap real baskets** from Online Retail II within the same hour bucket (keeps co-occurrence exactly). **Recommended v1.**
- **B3**: a fitted co-occurrence model (e.g. pairwise lift sampling). Only if you have time.

SKU universe: keep the top ~500–2000 SKUs by frequency (they cover most lines) and map them onto slots. Report the coverage %.

### 3.4 Scenario generator output

`data/scenarios/day_<seed>.csv`, generated once and identical for every layout:
```
t_s,type,id,sku,qty
21340.2,ORDER,O000123,85123A,2
21340.2,ORDER,O000123,22423,1
25200.0,TRUCK,T0007,85123A,48
```
Scenario families: `baseline`, `peak+20%`, `peak+40%` (λ scaled), `late_supply` (inbound delay shifted).
**Input validation**: replay of the real days vs generated days, compared on hourly counts, lines/order and SKU frequencies. Then compare their simulated KPIs.

### 3.5 Output data analysis

- Terminating simulation (one day), so no warm-up. Start each day with steady opening inventory and empty queues; document this.
- n replications from a pilot run so the 95% half-width ≤ target. Your Lab 10 dashboard code (t with n−1 df, `firstStays`) already does this.
- Compare candidates by **paired differences under CRN**. For selecting among k: Bonferroni or a two-stage R&S procedure (e.g. Rinott).
- Verification KPIs on every run: flow conservation per SKU, Little's law per queue, utilisation vs λ/(cμ).

---

## 4. Automatic model generation (the core contribution)

### 4.1 Pipeline

```
grid (user draws / template / GA)
   └─▶ Python compiler: validate → geometry (m) → aisle graph → access points → slotting → all-pairs distances
          └─▶ <cand>.json
                 └─▶ AnyLogic Main.onStartup → LayoutBuilder.build(json)
                        creates walls, nodes, paths, areas, shelf agents, docks, packing stations
                        binds the generic flowchart's lookups to the created objects
                        └─▶ same generic processes run → KPIs
```
All geometry logic sits in **Python** (easy to test, and the GA reuses it). AnyLogic **only instantiates** what the JSON describes. It never decides geometry. This keeps the Java small.

### 4.2 Grid vocabulary (freeze this)

| Code | Meaning | Generated as |
|---|---|---|
| `#` | wall / column | wall segment / blocked |
| `.` | unused | nothing |
| `A` | aisle cell (optional flag `>` `<` `^` `v` for one-way) | network node + paths to neighbouring `A` |
| `S` | shelf module cell; module = k cells, with orientation | shelf agent, slots on both faces, access node per face cell |
| `DI` / `DO` | inbound / outbound dock (boundary only) | dock agent + node |
| `R` | receiving buffer | rectangular node, capacity |
| `PK` | packing station | station agent (packer resource) + node |
| `G` | outbound staging | rectangular node, capacity |
| `H` | picker home / cart depot | home node of the picker pool |

Cell size is global (e.g. 1.2 m: shelf depth and aisle width as multiples). Docks and stations carry IDs in a sidecar list, not in the cell code.

### 4.3 Compiled JSON (example, abbreviated)

```json
{
  "schema": "layout/1",
  "meta": {"id": "U_ABC_03", "cell_m": 1.2, "rows": 30, "cols": 50, "template": "U", "slotting": "ABC"},
  "grid": ["##########", "#DI AAAAS#", "..."],
  "walls": [[0,0,60,0],[60,0,60,36]],
  "nodes": [{"id":"n0","x":1.8,"y":1.8}],
  "edges": [{"a":"n0","b":"n1","len":1.2,"oneway":false}],
  "docks": [{"id":"DI1","type":"in","node":"n0"},{"id":"DO1","type":"out","node":"n88"}],
  "areas": [{"id":"R1","type":"receiving","x":2,"y":2,"w":6,"h":4,"cap":200,"node":"n3"},
            {"id":"G1","type":"staging","x":50,"y":30,"w":6,"h":4,"cap":400,"node":"n87"}],
  "stations": [{"id":"PK1","node":"n80"},{"id":"PK2","node":"n81"}],
  "shelves": [{"id":"S07","x":12,"y":6,"len":6,"orient":"v",
               "slots":[{"id":"S07-03L","node":"n41","sku":"85123A","cap":60}]}],
  "home": {"node":"n85"},
  "dist": {"index":["n0","n3","n41"], "matrix_file":"U_ABC_03.dist.csv"}
}
```

### 4.4 Inside AnyLogic (PLE): what is built at runtime

- **Network**: create `PointNode`/`RectangularNode`/`Path` objects at runtime, add them to a `Network` on the default `Level`, then initialise. The docx's risk row is right that the exact constructors and initialisation call must be checked in **your** AnyLogic 8.9 install. That is spike S1 (§8). Your `tools/verify` shadow-compile setup (`CP_RUNTIME` jars) lets you compile-check the builder against the real engine before opening the IDE.
- **Movers**: picker/receiver/putaway pools are PML `ResourcePool`s of moving units whose home is the `H` node. Pickers travel with `MoveTo`/`seize` on the runtime network. Travel distance is accumulated per unit.
- **Shelves, docks, stations**: agent populations (`add_shelves(...)`). Each holds its node and slot table. **Do not use MHL racks in v1**: they are designed for pallets/forklifts, and runtime creation of them is undocumented.
- **Generic flowchart stays fixed**: destinations come from lookups (`slotNode(sku)`, `stationFor(order)`, `stagingNode()`). The **picking route** is a custom Java function: required slots → heuristic → sequence of nodes → loop of `MoveTo` + pick delay per stop (pick time per line).
- **Orders and lines as plain Java objects, not agents.** Only the order (or the picking tote) flows through the flowchart as an agent. This keeps the agent count low, which is safe against any PLE size limit.
- **Visual**: generated shapes (rectangles for shelves, lines for walls) so the animation shows the generated layout. A PLE watermark is fine.

### 4.5 Generator tests (gate before any experiment)

1. **Equivalence (docx 11.3)**: hand-build layout L0 in the editor and describe L0 in JSON. Same scenario and seeds → KPIs identical (deterministic times) or within CI (stochastic).
2. **Distance check**: AnyLogic picker distance per route = Python route length from the distance matrix (± node-snap tolerance).
3. **KIT check**: compile 3 KIT layouts, run their orders with S-shape routing, and compare against the reference route lengths.
4. **Rejection**: disconnected grid, a shelf with no aisle face, a dock not on the boundary → the compiler rejects it and AnyLogic never sees it.
5. **Conservation** on all templates: units in = on hand + in buffer + picked, per SKU.

---

## 5. Running many layouts in free AnyLogic: the job-bridge "API"

**Confirmed constraint:** PLE cannot export a standalone app, so Python cannot start AnyLogic runs on its own. (Some third-party sources also mention model-size limits. AnyLogic's help lists OptQuest at max 500 iterations and 7 decision variables. Check both in your install.)

**Option 1: Parameter Variation (simplest).** Python writes `candidates.csv` (k layouts) + seeds. A PV experiment over `candIdx × seed` runs them all in one click. Enough for template comparison and staffing grids.

**Option 2: file-based job bridge (the API you offered to build). Recommended for the optimiser.**
A **Custom Experiment** (or a long-running PV with one "worker" run) inside the AnyLogic IDE loops:
```
while (!stopFile.exists()):
    job = oldest file in jobs/pending/        // {"cand":"U_ABC_03.json","seeds":[1..20],"staff":{...},"policy":{...}}
    move it to jobs/running/
    for seed in job.seeds: create a Main engine, set its params from the job, run to the stop time, collect KPIs
    write jobs/done/<id>.json with per-seed KPIs
    sleep 1 s if nothing is pending
```
Python side: `bridge.submit(job) → id`, `bridge.wait(id) → results`. The GA/optimiser in Python then runs **closed-loop and unattended** while the IDE stays open. This is plain file I/O, so no extra licence is needed. Spike S2 verifies that PLE allows Custom Experiments and repeated engine runs.

**Option 3: AnyLogic Cloud API (Python client):** possible with a free cloud account, but runs are quota-limited and models are public. Not recommended as the main path.

---

## 6. Candidate layout generation

1. **Templates** (Python functions with parameters): I-flow (DI and DO on opposite walls), U-flow (same wall), L-flow. Within each one: aisle orientation, number of cross-aisles {0, 1, 2}, packing station location {near DO, central}, slotting {random, ABC, COI}.
2. **Constrained parametric generator**: the chromosome is *(aisle orientation, #cross-aisles, cross-aisle positions, shelf-block offsets, PK positions, slotting rule)*, not raw cells. Every chromosome decodes into a valid grid by construction, and the validator is a second guard.
3. **Static screen** (no DES, milliseconds per layout): expected route length per order = mean over sampled baskets of the routing heuristic on the distance matrix; plus putaway distance. Score = `E[D_pick] + α·E[D_putaway]`.
4. **Search**: a GA or simulated annealing on the static score proposes the population. Only the top-k per generation go to AnyLogic via the bridge. The DES score includes congestion at pack stations and picker blocking (v2), plus held orders.
5. **Report the gap** between the static and DES rankings. If they agree, travel dominates; where they differ, queueing matters. Either way it is a result.

---

## 7. Objectives and KPIs

**Stage A (layout), with staffing fixed at a generous level:**
`min E_ω[ mean order cycle time ]` (or `E[D_pick]` as the screening proxy), s.t. on-time-to-cut-off ≥ 98% and receiving-buffer overflow = 0.

**Stage B (staffing) on the best 2–3 layouts:**
`min (#pickers + #packers + #receivers)` (or a cost-weighted sum), s.t. on-time ≥ 98% and p95 cycle time ≤ T* under baseline, +20% and +40%. Small grid → Parameter Variation, or OptQuest if it fits the limits.

**Stage C (policies, zero cost):** release (immediate / wave / batch) × routing heuristic on the final layout.

**KPIs per run:** order cycle time (mean, p95) · % on time to cut-off · orders/hour · picker distance per order and per line · pick/pack/receive utilisation · pack-station queue length and wait · held orders and hold time (stock-outs) · receiving buffer max/avg/overflow · putaway distance · units in backlog at the end of the day.

---

## 8. Milestones (critical path in bold)

| # | Work | Exit criterion |
|---|---|---|
| **S1 (wk 1)** | **Spike: runtime network + 1 moving resource from a 5×5 JSON, in PLE 8.9** | A picker walks a generated path and its distance = Python's |
| S2 (wk 1) | Spike: Custom Experiment loop reading `jobs/pending` | 3 queued jobs run unattended |
| M1 (wk 1–2) | Data audit + dictionary for the 4 datasets | `DATA_DICTIONARY.md`, real/assumed table |
| M2 (wk 2–3) | Input models + basket generator B2 + inbound (R,S) generator + scenario files | Fit report; replay vs generated agree |
| **M3 (wk 2–3)** | **Manual baseline L0 in AnyLogic: inbound, inventory, picking, packing, cut-offs** | One day runs, conservation holds |
| **M4 (wk 3–4)** | **Python compiler + Java LayoutBuilder; L0 from JSON** | Equivalence test passes |
| M5 (wk 4) | Templates I/U/L × slotting; PV over cand × seed | Ranked table with paired CIs |
| M6 (wk 5) | Job bridge + static screen + GA | Optimised layout beats the best template, with significance |
| M7 (wk 5–6) | Staffing (Stage B), policies (Stage C), KIT/Mendeley validation | Final tables |
| M8 | Grid-drawing UI (Python or AnyLogic start screen), optional `alpgen.py` export, report | Demo: draw grid → run → KPIs |

---

## 9. Decisions still open

1. **Cut-off times and promise window** (e.g. same-day if ordered before 14:00).
2. **Scale**: #SKUs (500? 2000?), building size, #packing stations, staffing ranges.
3. **Hold vs partial-ship** policy for stock-outs (the spec assumes hold).
4. Whether a single person (Shivam?) owns the schemas and the bridge, while Siddhesh owns data and fitting. The split in the docx (workstreams A–F) works with 2 people as {A, D, E} vs {B, C, F}.
