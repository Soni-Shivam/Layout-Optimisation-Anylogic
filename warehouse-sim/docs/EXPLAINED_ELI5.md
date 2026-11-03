# The whole project, explained like you are 5

All numbers below are copied from the project reports (`reports/REPORT.md`, `input_analysis.md`, `validation.md`, `optimization.md`). Nothing is invented. Where something is an **assumption** (we had no data), it says so.

**The one-minute story.**
A real shoe warehouse gave us its records. We (1) studied the records, (2) built a copy of the warehouse inside the computer, (3) checked the copy behaves like the real one, (4) let the computer try many "what if we rearrange things?" ideas, and (5) found a better arrangement: **walking per order drops from 113.2 m to 68.4 m (-40%)**.

**Kitchen analogy used throughout**

| In the kitchen | In the project |
|---|---|
| Ingredients | the real data (orders, picks, shelf positions) |
| Recipe card | the **layout JSON file** (where everything is) |
| The kitchen itself | the **AnyLogic model** (it cooks whatever recipe card you hand it) |
| A shadow kitchen without a screen | the **Java reference simulator** (`RefSim`), fast, used by the optimizer |
| Taste-tester who tries 251 recipes | the **optimizer** |
| Health inspector | the **tests** (verification) and the **validation** |

---

## 0. Map of the files (so you can point at things)

| Folder / file | What it is |
|---|---|
| `data_raw/mendeley/` | the real dataset (untouched) |
| `python/whsim/` | all the Python: cleaning, fitting, building layouts, optimizer, reports |
| `java/src/wh/` | the "brain" in Java (routing, batching, stock, KPIs), shared by AnyLogic and the reference simulator |
| `anylogic/build_model.py` | a Python script that **writes** the AnyLogic model file |
| `model/WarehouseSim/WarehouseSim.alp` | the AnyLogic model (generated) |
| `model/WarehouseSim/data/` | what the model reads at start-up: layouts, SKU list, day files, config |
| `results/opt/` | optimizer outputs |
| `reports/` | the four reports |
| `tools/check.sh` | runs every check |

---

## 1. The problem and the warehouse

**What we did.** Picked a real problem: a footwear manufacturer's warehouse (one floor, Z = 1). Customers order shoes; workers walk around with carts collecting them; others pack; trucks bring new stock.

**Why.** Walking is the biggest waste in a picking warehouse. If shelves and the drop-off point are placed smartly, workers walk less.

**The real building** (from the data): 2,292 storage locations in **864 shelf bays**, **17 picking aisles**, **3 cross aisles**, and one central pick-up / drop-off point called the **depot** at (40.3 m, 63.1 m).

**The questions we ask.** Where should the depot be? Should we add cross aisles? Which shoe goes on which shelf (slotting)? How many pickers and how big a cart?

**Everyday picture.** A supermarket where a shopper must collect 24 items for several customers at once. If bread and milk (what everyone buys) are far from the checkout, everybody walks far.

**If the teacher asks...**
- *What is being optimised?* The layout (depot position, extra cross aisles, slotting), then staffing and cart size. The main measure is walking distance per order.
- *What is a depot here?* The point where pickers start and finish each trip and where carts are handed over.
- *Why simulation and not a formula?* Orders arrive in bursts, carts wait for pickers, stock runs out, cut-off times exist. Too many interacting random things for a closed formula.

---

## 2. The dataset and what each file gave us

Source: Mendeley Data pf2w725pw3 (R. Furlan de Assis, 2023), CC BY 4.0. Real WMS extract, 2023-01-05 to 2023-10-19.

| File | In plain words | What we used it for |
|---|---|---|
| `Customer_Order.csv` | **122,370 order lines** (who ordered which shoe, quantity, minute created, wave) | when orders come, what is in a basket, how popular each shoe is |
| `Picking_Wave.csv` | **215,192 rows, one per unit picked** (wave, shoe, shelf location, operator) | real carts ("waves"), where shoes really sit, validation |
| `Storage_Location.csv` | **2,292 shelf locations** with x, y, level | building geometry |
| `Product.csv` | 208 references with ABC class | report only |
| Four `*_Storage.csv` files | storage policies suggested by the data's authors | **not used** (our optimizer decides slotting itself) |
| Navigation points, CAD pdf | drawings | not used |

**What the data does NOT have** (important, the examiner may ask): no pick/pack/receive **timestamps**, no inbound trucks, no stock levels, no shift times, no dock positions. Those are **assumptions** (section 5).

**Words.** SKU = one reference x one size (e.g. `8N10W9_9.5`). There are **2,515 SKUs** from 206 references. A *wave* = the batch of orders one picker collects on one cart.

**If the teacher asks...**
- *Where does the data come from?* A public Mendeley dataset of a real footwear warehouse.
- *What can't it tell you?* Time to pick, pack, receive; inbound deliveries; stock; where the dock is.
- *Is it real or synthetic?* The data is real. We also generate synthetic days from models fitted to it.

---

## 3. Cleaning (making the data trustworthy)

**What we did.** `python/whsim/real_data.py` (`load_lines`, `fix_size`, `baskets`, `reconcile`, `waves`) cleans the order file. Full log in `input_analysis.md` section 3.

| Problem found | Rows | Fix |
|---|---|---|
| UTF-8 BOM on header, trailing blanks in customer code | all | stripped |
| Half sizes written without a decimal (`105` means 10.5) | **38,846** | divide by 10 |
| Empty size | 16 | dropped |
| Quantity 0 | 33 | dropped |
| Fully identical rows | 2,555 | **kept** (they are repeated pick tasks) |
| Repeated (order, SKU) lines | 6,667 | merged, quantities added |
| Result | **122,321 clean lines** | |
| Weekend dates | 5 | excluded from fits |
| Weekdays with < 5 orders | 6 | excluded from fits |
| **Regular working days** | **167** | used for fitting |

**Why the size fix is right (a proof, not a guess).** After dividing by 10, every one of the 215,192 picked units matches an ordered (wave, SKU); **zero** units were picked that were not ordered. Removing the 2,555 "duplicates" would break this match, so we kept them.

**If the teacher asks...**
- *How do you know `105` means 10.5?* Picking_Wave writes `10.5`; after the fix all picks reconcile with orders.
- *Why drop weekends?* We simulate a normal working day; 5 weekend dates are not typical.
- *Why were 33 weekdays with no orders ignored?* They are holidays / extraction gaps, not days with zero demand.

---

## 4. Input analysis: teaching the computer how orders behave

Idea: instead of replaying the same 10 days, we want a **generator** of realistic random days. For each random ingredient we pick a statistical model and test it.

### Plain-words dictionary of the tests

- **Distribution**: a rule saying how likely each value is (e.g. 150 orders vs 400 orders).
- **Poisson**: "events happen independently at a steady rate." Its hallmark: **variance = mean**. Like raindrops on a roof.
- **Index of dispersion**: variance / mean. Poisson says 1. Ours is about **88** (way more spread out).
- **Negative binomial**: Poisson whose rate changes from day to day (calm days and mad days). Fits "over-dispersed" counts.
- **Log-likelihood / AIC**: scores of how well a model explains the data. **AIC** = fit score with a penalty for extra knobs. **Lower AIC is better.**
- **Chi-square test**: cut the values into bins, compare how many days *really* fall in each bin with how many the model *expects*. Big gap -> small p-value.
- **KS test (Kolmogorov-Smirnov)**: compare the model's cumulative curve with the data's cumulative curve; the biggest gap is D. Big D -> small p-value.
- **p-value**: if the model were actually true, how often would we see a mismatch this big by luck? **p < 0.05 -> reject** the model. **High p -> "no evidence against it"** (it passes, which is not a proof it is right).
- **Bootstrap**: re-draw samples from the data many times to see what randomness alone would do.

### 4.1 Orders per day -> negative binomial

File: `input_models.py` (`fit_daily_volume`, `fit_count`, `chi2_gof`, `ks_discrete`). Data: 167 regular days, mean **193.2** orders/day, sd 130.4 (min 10, max 823).

| Model | AIC (lower = better) | chi-square p | KS p (bootstrap, B=300) | Verdict |
|---|---|---|---|---|
| Poisson | 14,139.1 | 4.0e-90 | < 1e-300 | rejected hard |
| **Negative binomial** (r = 2.383, p = 0.01218) | **2,041.3** | **0.345** | **0.283** | **passes, chosen** |
| Lognormal | 2,054.9 | 0.004 | 0.013 | rejected |
| Gamma | 2,041.3 | 0.380 | 0.263 | passes, tied |

Why negative binomial over gamma (tied)? It is a *count* distribution, and a "Poisson with a varying daily rate" is a natural story. Sampled values are limited to 5..1,234. Day of week matters (Mon 234, Fri 133 orders/day, Kruskal-Wallis p = 0.016), but day files use the pooled model so each seed is "a random working day".

### 4.2 When orders arrive during the day -> batch releases

Poisson arrivals are **rejected** on three tests (KS p about 1e-300, inter-arrival CV = 18.1 vs 1 for exponential, dispersion index 178). Reason visible in the data: the warehouse system **releases orders in batches**. There are 291 releases over 167 days (1 per day on 75 days, 2 on 67, 3 on 19, 4 on 5, 5 on 1); each lasts about **2.8 minutes**; the first release is at about 07:xx on 49% of days and carries on average 66% of the day's orders.

**Our model.** Pick the release pattern of one of the **15 real days with the closest volume**, split the N orders over its releases in the real proportions, and place each order uniformly inside its release window. This keeps the burstiness without inventing a formula.

Alternative we tested and dropped: "one morning batch + smooth Poisson rest" -> gets busiest-10-minutes badly wrong (KS p = 8.6e-13).

### 4.3 What is in an order -> copy real orders (bootstrap)

Lines per order: mean 3.5, but max 340; 59.5% of orders have a single line. Units per line: mean 2.0, max 635. **Every parametric fit was rejected** (geometric, negative binomial, zeta; all p < 1e-70) because the tails are too heavy. So the generator **bootstraps whole real orders** (draws real orders with their real SKUs and quantities, from the real orders within +-3 calendar days of the pattern day, to respect seasons). Bonus: SKUs that are bought together stay together.

### 4.4 Which shoes are popular
**525 SKUs (20.9%) make 80% of the order lines.** The SKU weights are simply the real share of lines per SKU.

### 4.5 Carts (waves) in the real data
**61% of the 9,707 real waves carry exactly 24 units; 89% at most 24.** So the system fills a cart of about 24 pairs. We use **24-unit carts**, with a release rule: send a cart when it is full **or** the oldest order has waited **15 minutes**.

### 4.6 Staff
6.6 operators active per day on average (range 1-11) -> **7 pickers as-is**.

**Check of the generator.** 1,000 synthetic days vs 167 real days (two-sample KS): orders/day p = 0.421 (model mean 198.3 vs real 193.2), lines/day p = 0.758, units/day p = 0.758, lines/order p = 0.206, busiest-10-minute share p = 0.978 -> not distinguishable. SKU popularity rank correlation rho = 0.99. (A first check on only 30 days gave orders/day 156 vs 193, p = 0.050; that was small-sample noise, see `reports/input_audit.md` section D.)

**If the teacher asks...**
- *Why not Poisson?* Variance is 88x the mean, and arrivals come in WMS batches. Poisson fails every test.
- *What does a high p-value mean?* No evidence against the model, not proof.
- *Why bootstrap the baskets?* Nothing parametric fit (heavy tails); copying real orders keeps the truth, including which SKUs go together.
- *Why chi-square and KS both?* They look at the fit differently (bins vs cumulative curve); the model should pass both.
- *Weakness?* The model can only produce release patterns and SKU mixes that occurred in 2023; and 30 days is a small sample for rare events.

---

## 5. Assumptions (where we had no data)

Honesty table (`input_analysis.md` section 2). Everything here is a **sensitivity parameter**.

| Input | Assumption | Why |
|---|---|---|
| Pick time per line | lognormal, mean **12 s**, sd 5 s (literature: 5-30 s) | no pick timestamps |
| Pack time | triangular(40, 60, 120) s per order + 4 s per unit | no timestamps |
| Receiving | gamma(4, 12) s per line; putaway handling uniform(20, 40) s | no timestamps |
| Walking speed | 1.0 m/s with cart; 1.2 m/s putaway | literature 0.6-1.3 |
| Carrier cut-offs | 13:00, 18:00, 20:30; shift 06:00-21:00 | not in the data |
| Order due time | first cut-off at least **1 hour** after arrival | modelling choice |
| Inbound trucks | one every 2 h from 07:00, top-up rule | no receipts |
| Opening stock | covers the 90th percentile of an SKU's selling-day units; total 22,776 units | no stock data |
| Dock / packing area | the rack-free lower-right quarter | no dock positions |
| Congestion | none (pickers don't block each other) | simplification |

The data gives only an upper bound: busy operator-days imply at most 197 s (p75) and 98 s (p95) per line *including travel*.

**If the teacher asks...**
- *Is 12 s per line a problem?* We tested 0.5x and 1.5x; the conclusion did not change (section 14).
- *Why the stock rule?* Without stock logic nothing is ever "out of stock". The chosen rule leaves a few percent of orders waiting for putaway, which is realistic.

---

## 6. Real building -> grid -> layout JSON

**Analogy.** Put graph paper over the floor plan, mark each square as wall, walkway or shelf, then write the sheet down as a recipe card.

**What we did** (`python/whsim/design.py`, `layout.py`):

1. **Coordinates.** Storage_Location.csv gives each bay's x, y in decimetres -> metres. 864 bays.
2. **Grid.** One column per bay (cell width **5/3 m**), one row per **3 m** (aisle row, rack row, rack row, ...). Every bay lands on its own cell with snapping error **<= 0.37 m**. Grid is 53 x 40 cells.
3. **Cell types** (`layout.py`): `#` wall, `A` aisle, `S` shelf bay, `DI`/`DO` inbound / outbound dock, `R` receiving buffer, `PK` packing station, `G` staging, `H` depot.
4. **Aisle graph.** Every walkable cell is a **node**; neighbouring walkable cells are joined by an **edge** (length 5/3 m across, 3 m along). Walking distance = shortest path on this graph.
5. **Slots.** Each shelf bay has 4 pick slots (levels), picked from a walkable neighbouring cell.
6. **Docks and staging** are placed in the empty lower-right quarter (**assumption**).
7. **Compile** (`compile_layout`) writes the JSON: grid, nodes, edges, facilities, slots (each with its SKU).

**A design is just coordinates:**

| Key | Meaning |
|---|---|
| `depot [x, y]` | pick-up / drop-off point |
| `n_pack` | packing stations (3), placed next to the depot |
| `cross_aisles [x, ...]` | extra cross aisles; each turns a rack column into an aisle (its slots are lost) |
| `slotting` | which SKU goes where |

The id is readable: `D46.6_111.1-P3-X18.27_53.27-abc` = depot at (46.6, 111.1), 3 packers, extra aisles at x = 18.27 and 53.27, abc slotting. As-is = `D40.3_63.1-P3-Xnone-asis`.

**The validator** refuses bad layouts: not connected, a shelf nobody can reach, too few slots for the SKUs.

### Slotting policies (`assign_skus`)
| Policy | In plain words |
|---|---|
| **asis** | the real storage: each SKU goes on the bay it was **really picked from most often** (`export_asis_slotting`; on average 70.6% of its picks are there) |
| **random** | every SKU on a random slot |
| **class** | A/B/C zones by pick frequency: fastest 20% of SKUs in the cheapest zone, next 30%, rest 50%; random inside a zone |
| **abc** | dedicated: the most-picked SKU gets the cheapest slot, the 2nd the next cheapest, and so on. "Cost" of a slot = distance depot -> slot -> nearest packing station |

**If the teacher asks...**
- *What is a "design in coordinates"?* Instead of hand-drawing a new warehouse, a layout is a few numbers (depot x, y; aisle x; policy), and code builds the whole warehouse from them.
- *How is distance computed?* Shortest path on the aisle graph, not straight lines.
- *What does an extra cross aisle cost?* It removes a rack column's slots (the design still has to fit every SKU).
- *How good is the snapping?* At most 0.37 m error.

---

## 7. Automatic model generation (the AnyLogic side)

**Analogy.** The kitchen (AnyLogic model) never changes; you hand it a different recipe card (layout JSON) and it cooks a different warehouse.

**How it works**
1. `anylogic/build_model.py` is a Python program that **writes the `.alp` file** (AnyLogic's XML): agent types (Order, Receipt, Worker, DayClock), the flowchart, resource pools, the dashboard and the 5 experiments.
2. At start-up the model runs `Main.setup()`: it reads the layout JSON, the run config, the SKU list and the day file; sizes the resource pools; **draws the warehouse from the JSON** (aisles, racks, docks, depot); and feeds the orders into the fixed flowchart.
3. The **core Java** (`java/src/wh/*.java`: `Warehouse`, `Router`, `Inventory`, `Kpi` and others) is copied **unchanged** into the model, and the very same classes are used by the plain-Java simulator `RefSim`.

Why share the code? So the optimizer (which needs thousands of fast runs and cannot open AnyLogic) and AnyLogic compute **the same decisions**. That also gives a built-in cross-check.

**If the teacher asks...**
- *What does "automatic generation" mean here?* Changing the warehouse means changing a file, not editing the model. And the model file itself is generated by a script.
- *Why Java twice?* One copy of the logic, two "containers": AnyLogic (animation, experiments) and RefSim (fast, headless).
- *Could you run AnyLogic here?* We verified by compiling every snippet against the AnyLogic 8.9.10 engine jars and loading/re-writing the `.alp` with AnyLogic's own serializer. A run inside the IDE could not be done in this environment (stated in the README).

---

## 8. The flowchart: what happens to an order

Everyday story: a customer orders -> we check the shoes exist -> we wait until a cart can be filled -> a picker walks the aisles -> packing -> waiting for the truck -> shipped. Meanwhile trucks bring new shoes.

**Outbound (an order):**
1. **Arrival** (from the day file).
2. **Stock check** (`Inventory.tryReserve`): are all lines in stock? If yes, reserve them. If not, the order is **held** until a putaway brings the stock.
3. **Waiting for a cart.** Released orders queue. `Warehouse.formBatch` builds a cart by **first-fit**: the oldest order always goes on, then every later order that still fits in **24 units** (a single order bigger than a cart is split into cart-sized trips, like the real system).
4. **Wave release rule** (`Warehouse.releaseNow`): send the cart when full **or** the oldest order has waited **15 min** (checked every 10 s by a ticker).
5. **Picker seized.** One of 7 pickers takes the cart.
6. **Tour** (`Warehouse.planBatch` + `Router.pickTour`): **nearest-neighbour**: from the depot go to the closest needed slot, then the closest next one, and so on; then the nearest packing station; then back to the depot. Time = walking at 1 m/s plus pick time at each stop (12 s per line, random).
7. **Packing** (2 packers): triangular(40, 60, 120) s + 4 s per unit.
8. **Staging** until the **next carrier cut-off** (13:00, 18:00, 20:30), then **shipped**.

**Inbound (a delivery line):** arrival -> **receive** (2 receivers) -> **putaway** (2 workers walk dock -> slot -> dock) -> stock goes up -> held orders whose lines are now all in stock are released.

**Day length.** t = 0 is 06:00; the day ends at 54,000 s (21:00), then KPIs are written.

**If the teacher asks...**
- *What is wave picking?* Collecting several orders on one cart in one tour, then sorting at packing, instead of one tour per order.
- *Why wait up to 15 minutes?* To fill carts. Trade-off: fewer, fuller tours vs waiting.
- *Why nearest-neighbour and not the optimal route?* It is simple, fast, matches how such routes are done; the Java and Python versions give identical lengths. Not optimal (listed as a limitation).
- *What is a held order?* One whose stock isn't there yet; it waits for a putaway.
- *What is on time?* Packed before the cut-off it is due for (first cut-off at least 1 h after arrival).

---

## 9. Random numbers and common random numbers (CRN)

**Analogy.** Two kitchens are given the **same dice rolls** for the same customers, so any difference in results comes from the recipe, not from luck.

**How** (`Warehouse.rng`): every random time is drawn from a stream seeded by **(seed, stream type, order index)**; the seed is scrambled with the SplitMix64 mixer because `java.util.Random` mixes poorly. Result: order #57 gets the same pick and pack times in **every layout and in any event order**.

**Why it matters.** Layout A vs B compared on identical work -> the **paired difference** has a much tighter confidence interval than comparing two independent runs.

Tested: sample means match formulas, and the streams are independent (CoreTest).

**If the teacher asks...**
- *What is a CRN?* Same random inputs across the alternatives being compared.
- *Why per order and not one global stream?* With one global stream, a change in routing changes the order in which random numbers are consumed, and the comparison would be noisy.
- *What is a paired comparison?* Subtract the two layouts day by day, then average the differences.

---

## 10. Verification: "is the code right?" (`tools/check.sh`)

Think of it as a health inspector going through every room.

1. **Python tests (30):** layout compiler and validator, real-building geometry (every bay on its own cell), designs and cross aisles, input file format, determinism, exact replay of a real day.
2. **Java `CoreTest` (2,500+ checks):** JSON parser; each distribution's sample mean vs its formula; independence of streams; batching (first-fit, multi-trip orders, wave release); inventory; **Java router = Python router to the last bit on every order of every layout**; full reference-simulator days (stock balance, every picked order on exactly one cart, shipments at cut-offs).
3. **AnyLogic model:** generate the `.alp`; compile every Java snippet against the AnyLogic 8.9 engine jars; load and re-write with AnyLogic's serializer; a screen preview checks no text overlaps.

**Verification vs validation.** *Verification* = did we build the model right (code does what we meant). *Validation* = did we build the right model (does it match reality).

---

## 11. Validation: "does it match the real warehouse?"

**Test.** The data tells where each unit was **really picked from**. Take the 9,143 historical waves (those with picks on locations we can place; 191,583 of 215,192 units = 89.0%). Route each wave twice with the same nearest-neighbour rule: once over the **real pick locations**, once over the **model's as-is layout**.

| Tours of the same historical waves | mean (m) | median (m) | p95 (m) |
|---|---|---|---|
| **Real pick locations** | **280.7** | 286.7 | 456.0 |
| **Model, asis storage** | **283.1** | 288.7 | 470.7 |
| model, random storage | 464.5 | 508.0 | 694.0 |
| model, class storage | 261.1 | 266.0 | 443.3 |
| model, abc storage | 226.9 | 226.0 | 400.0 |

**Reading it.** The as-is model gives **283.1 vs 280.7 m: within 1%**. A random layout would be far worse (464.5 m): the real warehouse is already roughly class-based. This makes the as-is baseline credible, so the improvements measured on top of it are credible too.

**If the teacher asks...**
- *Why does 283 vs 281 prove anything?* Same waves, same router; the only thing that differs is where the SKUs sit. Matching means the model's layout and distances reproduce the real walking.
- *What is not validated?* Times (pick, pack, receive), inbound and stock: no data. We only validate walking distance.
- *Why is abc shorter than the real one?* Because the real one is not perfectly sorted by turnover.

---

## 12. KPIs (what we measure; `Kpi.java`)

| KPI | Plain meaning |
|---|---|
| **walk per order (m)** | the order's share of its cart's tour. Our headline number |
| tour time (s) | time of one cart's trip |
| **fulfilment** (mean, p95) | arrival -> packed. p95 = 95% of orders are faster than this |
| **on time (%)** | packed before its due cut-off |
| held orders | orders that had to wait for stock |
| utilisation | share of time each worker type is busy (pickers, packers, receivers, putaway) |
| carts, orders / cart, units / cart | how well the carts fill |

Every run writes one summary row to `results/runs.csv` (plus an orders file).

**Surprise to mention.** Picker utilisation is low (**0.05** as-is on real days) yet fulfilment takes about **an hour**, because **most of a day's orders are released at once** in one or two WMS batches. The queue after a release, not the average load, drives fulfilment time.

---

## 13. The optimizer: 4 stages (`python/whsim/optimize.py`)

**Analogy.** A taste-tester has too many recipes to cook them all, so: first a quick sniff test of many (stage 1), then actually cook the best few (stage 2), then tune the kitchen staff (stage 3), then check the verdict survives different assumptions (stage 4).

### Stage 1: static screen on the real waves
Quick score of a layout = **mean tour length of the real historical waves** (about 9.8k carts with real contents) on that layout, routed in fast Java (`wh.Evaluate static`). No clock, no queues.

- **1a. Depot heat map** (`depot_scan`): try the depot on every 3rd open floor cell, with `abc` and `asis` slotting. Gives a map of "where is a good depot spot".
- **1b. Genetic algorithm** (`ga`): "evolution of layouts". Population 24, 14 generations. A design = (depot, 0-2 extra cross aisles, slotting). Fitness = mean tour. Operators: tournament selection (pick the better of 2 random), crossover (child mixes parents' depot / aisles / slotting), mutation (nudge the depot, add/drop/move an aisle, change policy), **elitism** (best 2 survive). It evaluated **251 distinct designs**. Best: `D46.6_111.1-P3-X18.27_53.27-abc`.

As-is layout mean tour per wave (static): asis **275.2**, random 445.8, class 254.6, abc **221.0** m.

### Stage 2: DES ranking with paired Bonferroni CIs
Take the 4 best *distinct* GA designs + the 4 as-is variants (asis, random, class, abc) and run the **full discrete-event simulation** on the **same 10 synthetic days** with CRN. Compute the difference against as-is on each day (**paired**), and a 95% confidence interval. **Bonferroni** = when comparing several designs at once, widen each interval (alpha / number of comparisons) so the chance of a false "win" stays at 5% overall. Recommended = shortest walk per order.

### Stage 3: pickers x cart size
On the recommended layout: pickers 2..8 x cart 0 (one order per trip), 12, 24, 36 units. Rule: **fewest pickers** that still give **on time >= 95%** and **p95 fulfilment <= 120 min**, then least walking.

### Stage 4: robustness
Repeat as-is vs recommended with the (assumed) pick time x0.5, x1.0, x1.5.

**If the teacher asks...**
- *Why two stages (static then DES)?* The static score takes milliseconds, so we can screen hundreds of designs; DES takes longer, so only finalists get it. DES adds queues, waiting and stock.
- *What is a genetic algorithm?* Keep the best, combine and randomly tweak them, repeat; good guesses survive.
- *Is the GA result guaranteed optimal?* No. It is a search heuristic over 251 designs; it reports the best found.
- *Why Bonferroni?* We compare 7 designs against one baseline; without it, one might look significant by luck.
- *Why CRN here?* Paired differences with tight intervals.

---

## 14. Results and recommendation

**Stage 2 table (10 synthetic days):**

| Design | walk/order (m) | tour (s) | fulfil mean (s) | on time (%) | walk vs as-is (95% Bonferroni CI) |
|---|---|---|---|---|---|
| as-is (`...asis`) | **113.2** | 705 | 3,716 | 99.1 | |
| as-is places, random | 173.3 | 975 | 3,803 | 99.4 | +60.1 +- 28.2 |
| as-is places, class | 101.9 | 660 | 3,603 | 99.5 | -11.3 +- 12.3 (not significant) |
| as-is places, abc | 87.1 | 593 | 3,599 | 99.5 | -26.1 +- 16.2 |
| **recommended** `D46.6_111.1-P3-X18.27_53.27-abc` | **68.4** | **508** | **3,569** | 99.2 | **-44.8 +- 23.1** |

**Recommended design:** re-slot by pick frequency (abc), move the depot to **(46.6, 111.1) m**, add extra cross aisles at **x = 18.27 m and 53.27 m**. Walking per order **113.2 -> 68.4 m (-40%)**; cart tour **705 -> 508 s**. Three other near-ties (69.0-69.6 m) show the result is stable, not a fluke of one point.

**Real days replay (10 historical days):** walk per order **69.3 -> 42.1 m** (-27.2 +- 5.9), fulfilment mean 3,246.1 -> 3,119.5 s (-126.6 +- 29.8). On-time % is essentially unchanged (91.2 vs 91.4).

**Cheap first step:** re-slotting alone (abc, no construction) gives 113.2 -> 87.1 m.

**Staffing (Stage 3):** **3 pickers with 36-unit carts** (on time 98.8%, p95 120 min, 9.1 km walked per day). Add pickers only for the morning release.

**Robustness (Stage 4), fulfilment mean as-is vs recommended:**

| pick time x | as-is | recommended | difference |
|---|---|---|---|
| 0.5 | 3,656 | 3,518 | -138 +- 35 |
| 1.0 | 3,716 | 3,569 | -147 +- 39 |
| 1.5 | 3,760 | 3,621 | -139 +- 66 |

The gain holds across the assumed pick times.

**Be honest about this nuance.** Walking drops 40%, but average fulfilment only drops by about 147 s (3,716 -> 3,569 s), because fulfilment is dominated by the queue after big releases. The walking gain is large; the service-time gain is real but smaller.

**If the teacher asks...**
- *What do you recommend?* abc re-slotting + depot at (46.6, 111.1) + cross aisles at 18.27 and 53.27; 3 pickers with 36-unit carts.
- *Is it significant?* Yes: the walk CI is -44.8 +- 23.1 m (excludes 0), fulfilment -147 +- 59 s.
- *Why is on-time % unchanged?* On-time is already ~99% on typical days; the late orders come from huge releases right before a cut-off and from held orders (the inbound rule is an assumption).
- *What does a new aisle cost?* It removes the rack column's slots (less storage capacity).
- *Can I trust 3 pickers?* It depends on the assumed service times and no congestion; measure them first.

---

## 15. The AnyLogic experiments and dashboard

Open `model/WarehouseSim/WarehouseSim.alp` (AnyLogic 8.9 PLE).

| Experiment | What it does |
|---|---|
| **Simulation** | One animated day on `Main.layoutFile` (default as-is). Set `Main.realDay = 1..10` to replay a historical day |
| **CompareLayouts** | every design in `data/layouts/index.txt` (as-is x 4 policies, recommended, runner-up) x synthetic days 1-10, CRN |
| **ValidateRealDays** | as-is on the 10 replayed real days |
| **StaffPickers** | 2-8 pickers x days 1-10 |
| **CartSize** | single-order, 12-, 24- and 36-unit carts x days 1-10 |

Each run appends a row to `model/WarehouseSim/results/runs.csv`; `python3 -m whsim.analyze` summarises it (`--where`, `--by`, `--baseline`).

**Dashboard / animation.** The warehouse is drawn from the JSON (aisles, racks, docks, depot); worker dots walk the real aisles (red pickers, blue putaway, orange packers, yellow receivers; grey idle); live KPI tiles, charts, an order board, and an end-of-day panel.

The optimizer's DES results (`results/opt/*_des.csv`) are the numbers to compare AnyLogic runs with (small differences from simultaneous-event ordering are expected).

**If the teacher asks...**
- *How do I compare layouts in AnyLogic?* Run CompareLayouts, then `python3 -m whsim.analyze`.
- *Why compare with RefSim?* Same decision code; any big gap would indicate a bug.
- *Honest status:* AnyLogic runs themselves were not executed in the build environment; verified by compilation and the serializer.

---

## 16. Limitations (say these before the teacher does)

- Pick, pack, receive times, inbound deliveries and opening stock are **assumptions** (no data); the main one (pick time) was varied 0.5x-1.5x.
- Dock / packing area position is **assumed**.
- **No congestion** between pickers; **one floor** only (Z1); nearest-neighbour routing is not optimal.
- Extra cross aisles **lose storage slots** (capacity for growth shrinks).
- The generator can't produce release patterns or SKU mixes never seen in 2023.
- Validation covers **walking distance** only.
- Not yet verified inside the AnyLogic IDE (see section 15).
- Next steps: measure real times and dock positions, re-run `whsim.optimize`, extend to floors Z2-Z4, add congestion.

---

## 17. Glossary

| Word | Simple meaning |
|---|---|
| **SKU** | one product variant (reference x size) |
| **Order line** | one SKU and a quantity within an order |
| **Wave / cart** | a batch of orders collected in one tour (about 24 units) |
| **Depot** | pick-up / drop-off point; every tour starts and ends there |
| **Slotting** | deciding which SKU sits on which shelf slot |
| **ABC / class / dedicated** | put fast sellers in the best spots (abc = rank by rank; class = 3 zones) |
| **Cross aisle** | a walkway that cuts across the picking aisles (shortcut) |
| **Cut-off** | time the carrier leaves; orders packed before it ship |
| **Staging** | waiting area for packed orders |
| **Putaway** | carrying received goods to their shelf |
| **Held order** | order waiting for stock |
| **WMS** | warehouse management system (the real company's software) |
| **DES** | discrete-event simulation: time jumps from event to event |
| **KPI** | key performance indicator (walk/order, fulfilment, on time...) |
| **Negative binomial** | Poisson with a day-to-day varying rate; for over-dispersed counts |
| **Poisson** | independent random events at a constant rate (variance = mean) |
| **Chi-square test** | compares observed vs expected counts per bin |
| **KS test** | largest gap between two cumulative curves |
| **AIC** | model score with a complexity penalty, lower is better |
| **p-value** | chance of such a mismatch by luck if the model were true |
| **Bootstrap** | resampling real data to simulate or to test |
| **CRN** | common random numbers: the same randomness for every design compared |
| **Paired CI** | confidence interval on day-by-day differences |
| **Bonferroni** | wider CIs so many comparisons together keep 95% confidence |
| **Genetic algorithm** | search by selection, crossover, mutation |
| **Verification** | are we building the model right (tests) |
| **Validation** | is it the right model (matches reality; 283.1 vs 280.7 m) |
| **JSON** | plain-text data format; our layout "recipe card" |
| **p95** | the value 95% of cases stay below |

---

## 18. Cheat sheet of the key numbers

- Data: **122,370** order lines, **32,621** orders, **2,515** SKUs, **215,192** picked units, **9,707** waves, **167** regular days.
- Building: **864** bays, **2,292** locations, **17** aisles, **3** cross aisles, depot (40.3, 63.1).
- Orders/day: negative binomial, mean **193.2** (Poisson dispersion ~88).
- Carts: **24** units (61% of real waves exactly 24); release when full or after **15 min**.
- Staff as-is: **7 pickers**, 2 packers, 2 receivers, 2 putaway.
- Validation: **283.1** (model) vs **280.7** (real) m mean tour.
- Optimiser: **251** designs, GA 14 generations x 24; DES on 10 days.
- Result: **113.2 -> 68.4 m** per order (-40%); tour **705 -> 508 s**.
- Recommendation: depot (46.6, 111.1), cross aisles at 18.27 and 53.27, abc slotting; **3 pickers, 36-unit carts**.
- Tests: **30** Python tests, **2,500+** Java checks.
