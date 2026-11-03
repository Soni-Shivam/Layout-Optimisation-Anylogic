# Context for the "Input Data Analysis" slides: IE305 warehouse simulation

You are making presentation slides about the **input data analysis** of a simulation project. This file is your only source. Use **only the numbers below**: do not invent values, tests or datasets. If a slide needs something that is not here, leave a placeholder like `[TBD]`.

---

## 1. Project in one paragraph

**Course:** IE305 Simulation Lab, IEOR, IIT Bombay. **Team:** Shivam Soni and Siddhesh Phadke.

We simulate the order-fulfilment warehouse of a real footwear manufacturer in **AnyLogic** (free PLE). One simulation run is one working day:
- orders arrive;
- pickers push carts (about 24 units per cart) through the aisles;
- orders are packed and leave at carrier cut-offs.

The layout (depot position, extra cross aisles, slotting) and the staffing are then optimised. The **input data analysis** turns the real warehouse data into the random inputs that drive each simulated day.

---

## 2. The data

| Item | Value |
|---|---|
| Dataset | R. Furlan de Assis, *Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company*, Mendeley Data v1 (2024), doi:10.17632/pf2w725pw3.1, licence CC BY 4.0 |
| Type | real WMS (warehouse management system) extract, anonymised |
| Period | 5 Jan 2023 – 19 Oct 2023 |
| Size | 122,370 order lines; 215,192 picked units; 9,707 picking waves; 2,292 storage locations; 208 product references |
| After cleaning | 122,321 order lines, 32,621 orders, 2,515 SKUs (SKU = reference × shoe size) |
| Days | 178 dates with data; **167 regular working days** (Mon–Fri, ≥ 5 orders) used for fitting |

**Key limitation (from the data audit).** The only timestamp is the order creation time, to the minute: 768 distinct values in the whole period, and every picking wave carries a single timestamp. There are **no pick, pack or receipt timestamps**, so service times cannot be estimated from the data. They are **assumed** and varied in a sensitivity analysis.

A second dataset named in the project spec (a B2FIND / KIT order-picking benchmark) could not be obtained, so it is **not** used in the input analysis.

---

## 3. Data cleaning (the main rules)

| Rule | Rows affected | Action |
|---|---|---|
| Half shoe sizes written without the decimal point (`105` = 10.5) | 38,846 | divided by 10 |
| Empty size | 16 | dropped |
| Quantity 0 | 33 | dropped |
| Fully identical rows (they are real repeated pick tasks) | 2,555 | kept |
| Same SKU repeated inside one order | 6,667 | merged (quantities summed) |
| Weekend dates and fragment days (< 5 orders) | 5 + 6 dates | excluded from the volume and arrival fits |

**Proof the cleaning is right.** After fixing the half sizes, every one of the 215,192 picked units matches an ordered line, and **0 units were picked that were not ordered**.

---

## 4. Real or assumed: every simulation input

| Input | Source | Model used in the simulation |
|---|---|---|
| Orders per day | **real** | Negative binomial, r = 2.38, mean 193.2 orders/day |
| Arrival times within the day | **real** | Real batch-release patterns, copied from the 15 real days with the closest volume |
| Order contents (SKUs + quantities) | **real** | Whole real orders, bootstrapped from orders within ±3 days of the copied day |
| SKU popularity | **real** | Share of order lines per SKU |
| Historical picking waves | **real** | 9,707 real waves (the optimiser's workload) |
| Pick time per line | **assumed** | Lognormal, mean 12 s, sd 5 s (literature range 5–30 s) |
| Pack time | **assumed** | Triangular(40, 60, 120) s per order + 4 s per unit |
| Receiving / put-away | **assumed** | Gamma(4, 12) s per receipt line; Uniform(20, 40) s handling |
| Walking speed | **assumed** | 1.0 m/s with a cart; 1.2 m/s for put-away |
| Opening stock, inbound trucks | **assumed** | Truck every 2 h from 07:00 with a top-up rule; opening stock = max(2, 1.5 days of mean demand, 90th percentile of the SKU's units on days it sells) |

---

## 5. Key findings and fitted models

### 5.1 Orders per day: variable, and not Poisson
- **Volume:** mean 193 orders/day, sd 130, CV 0.68. Range 10–823; median 168.
- **Lines and units:** 686 lines/day and 1,287 units/day on average.
- **Fits, ranked:**

| Family | KS p (bootstrap) | χ² p | Anderson–Darling p (bootstrap) | Verdict |
|---|---|---|---|---|
| Poisson | < 0.001 | 4e-90 | 0.003 | rejected (variance/mean = 88) |
| **Negative binomial** (r = 2.38, mean 193.2) | **0.28** | **0.35** | **0.26** | **chosen** |
| Gamma (discretised) | 0.26 | 0.38 | 0.21 | passes (tied on AIC) |
| Lognormal (discretised) | 0.013 | 0.004 | 0.003 | rejected |

- **Why NB:** the variance is 88× the mean, far beyond Poisson. The NB is the classical "Poisson day whose rate changes from day to day".
- **Weekday effect:** Kruskal–Wallis p = 0.016. Mon 234, Tue 209, Wed 179, Thu 200, Fri 133 orders/day.
- Figures: `figures/daily_volume.png`, `figures/daily_volume_qq_pp.png`, `figures/day_of_week.png`

### 5.2 Arrivals come in batches, not as a Poisson stream
Tests on 32,265 orders (minute stamps jittered within the minute):

| Hypothesis | Result | Verdict |
|---|---|---|
| Uniform within the hour (Poisson) | KS D = 0.104, p ≈ 5e-305 | rejected |
| Exponential inter-arrival times | CV = 18.1 (exponential would be 1) | rejected |
| 10-minute counts are Poisson | dispersion index 178 (Poisson would be 1) | rejected |

- **Mechanism:** the WMS releases orders in **1–5 batches per day**, each about 3 minutes long. Batches per day were 1 on 75 days, 2 on 67, 3 on 19, 4 on 5 and 5 on 1.
- **Morning batch:** 49% of days start with a 07:xx batch, which carries 66% of that day's orders on average.
- **Model:** copy a real day's release pattern (from the 15 days with the closest volume) and split the N orders across its batches.
- Figures: `figures/interarrival_check.png`, `figures/hour_profile.png`

### 5.3 Order contents
- **Lines per order:** mean 3.5, median 1. **59.5% of orders have a single line**; the maximum is 340.
- **Units per line:** mean 2.0, median 1. Units per order: mean 7.0.
- **Fits:** geometric, negative binomial and zeta are all rejected by χ². The tails are heavier than NB and lighter than zeta.
- **Model:** bootstrap whole real orders. This keeps the size distribution and which SKUs are ordered together.
- **SKU concentration:** 525 of 2,515 SKUs (21%) make 80% of the order lines.
- Figures: `figures/lines_per_order.png`, `figures/units_per_line.png`, `figures/sku_pareto.png`

### 5.4 Picking waves and operators
- **Cart size:** a wave carries 22.2 units on average, and **61% of waves carry exactly 24 units**. The WMS fills a cart of about 24 pairs, so the model uses a 24-unit cart.
- **Operators:** 6.6 active per day on average (range 1–11). Lines per operator-day: median 74.5, 95th percentile 294.
- **Upper bound on pick time:** the p95 operator-day implies at most 98 s per line **including walking**. This is consistent with the assumed 12 s of non-walking pick time.
- Figure: `figures/wave_sizes.png`

---

## 6. Validation and audit (spec §3.2 checks)

### 6.1 Are simulated days independent? Yes, but the level moves by month
- **No day-to-day memory:** Ljung–Box (10 lags) p = 0.26 and runs test p = 0.21. After removing the month and weekday levels, the residual is white noise (p = 0.19).
- **Seasonal level:** the month explains 13% of the variance (Kruskal–Wallis p = 0.010). Month means range from 138 (Jun) to 259 (Feb), i.e. 0.71× to 1.33× the average month.
- **So:** drawing each one-day replication independently is correct, and peak scenarios can be anchored on real month levels.
- Figure: `figures/audit_volume_acf.png`

### 6.2 Is the day generator unbiased? Yes
Validation on **1,000 synthetic days** vs the 167 real days (`input_analysis.md` §7):

| Per day | Real mean | Generator mean | KS p |
|---|---|---|---|
| Orders | 193.2 | 198.3 | 0.42 |
| Lines | 686.2 | 694.8 | 0.76 |
| Units | 1,287 | 1,335 | 0.76 |
| Lines per order | 3.58 | 3.64 | 0.21 |
| Busiest-10-min share of the day | 0.761 | 0.758 | 0.98 |

- An earlier check on only 30 synthetic days gave 156 orders/day (KS p = 0.050) and looked like a bias.
- The audit showed it was sample noise: the mean of 30 generator days falls anywhere between 163 and 237, and even 200-day blocks give KS p from 0.05 to 0.88. Validation was therefore moved to 1,000 days.
- Figures: `figures/validation.png`, `figures/audit_generator.png`

### 6.3 Is the ±3-day order bootstrap justified? Yes
- **Product mix drifts:** the similarity of the SKU mix between two weeks falls from 0.55 (1 week apart) to 0.42 (30 weeks apart).
- **Whole-year bootstrap would be wrong:** it would give 384 distinct SKUs per day against 320 in reality (+20%).
- **Basket size moves with the month:** the mean rises from 2.6 lines (Feb) to 4.4 (May, Oct). Successive orders are independent (lag-1 correlation ≈ 0).
- Figure: `figures/audit_sku_drift.png`

### 6.4 Other validation results
- **Hour-of-day profile and burstiness:** the busiest 10 minutes hold 76% of a day's orders in reality and in the model; total variation distance of the hour profile 0.04.
- **SKU popularity:** Spearman ρ = 0.99 between real and simulated popularity; 95 of the real top-100 SKUs are in the model's top 100.
- **Operators:** only 7% of the variation in lines per operator-day is between operators (intraclass correlation 0.07). A per-picker speed factor is an optional sensitivity case.
- Figure: `figures/validation.png`

---

## 7. Limitations (say these honestly)
1. **Service times are assumed.** There are no pick, pack or receipt timestamps, so these times are varied in a sensitivity analysis.
2. **Inbound and stock are assumed.** There is no receipt or stock data, so opening stock and trucks come from a documented rule.
3. **Only patterns seen in 2023.** Release patterns and order contents are empirical, so the model cannot produce patterns never seen in 2023.
4. **One year of data.** Seasonality is estimated from a single year (Jan–Oct).

---

## 8. Suggested slide outline (6–8 slides)

1. **Data source and audit:** the dataset, its size, the cleaning proof (0 unmatched units), and "no pick timestamps".
2. **Real vs assumed inputs:** the table from §4, colour-coded real / assumed.
3. **Orders per day:** histogram + Q-Q plot; Poisson rejected; NB chosen (KS 0.28, χ² 0.35, AD 0.26).
4. **Arrivals are batches:** the three rejected Poisson tests; batch-release model; 49% of days start with a 07:xx batch carrying 66% of orders.
5. **Order contents:** 59.5% single-line orders; parametric fits rejected → bootstrap real orders; 24-unit carts.
6. **Validation:** 1,000 generator days vs 167 real days (198 vs 193 orders/day, all KS p ≥ 0.2); burstiness and SKU popularity (ρ = 0.99) reproduced.
7. **Assumption checks:** days independent (Ljung–Box p = 0.26) but monthly level 0.71×–1.33×; SKU mix drift justifies the ±3-day window.
8. **Limitations and next steps:** §7, plus sensitivity on pick time (8–20 s).

**Style notes.**
- One message per slide; put the verdict in the slide title (e.g. "Orders arrive in batches, not as a Poisson stream").
- Use the figures listed above (paths relative to `warehouse-sim/reports/`) rather than redrawing charts.
- Mark real inputs and assumed inputs consistently: same colour and same label on every slide.
