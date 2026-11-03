"""Generates the generic AnyLogic model model/WarehouseSim/WarehouseSim.alp.

The .alp holds only what is the same for every warehouse:
  * agent types Order, Receipt, Worker, DayClock
  * the process flowchart (inbound: arrive -> receive -> putaway; outbound: arrive -> stock check / hold
    -> pick -> pack -> stage until cut-off -> ship) and four resource pools
  * the core Java (java/src/wh/*.java, embedded unchanged as static nested classes of Main)
  * the KPI panel, worker dots and experiments

Everything that differs between warehouses comes from the files in data/ at start-up: Main.setup()
loads the layout JSON, run config, SKU master and day file, sizes the resource pools, draws the layout
and feeds the workload into the flowchart. Changing the layout JSON changes the model; no editing.

Every Java snippet is also compiled against the AnyLogic engine jars (build/shadow), see tools/check.sh.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from alpgen import GENERATED_IMPORTS, Model, Shapes, cd  # noqa: E402

PACKAGE = "warehousesim"
NAME = "WarehouseSim"
CORE = ["Json", "Dist", "RunConfig", "LayoutData", "PathGraph", "Router", "ScenarioData", "Inventory",
        "Stats", "Warehouse", "Kpi"]          # RefSim is the reference simulator and stays outside the model
# experiments stop 60 s after the end of the day (horizon_s, when Main.finishRun() writes the KPIs and stops the run),
# so the progress bar spans exactly one day
STOP_TIME = int(__import__("json").loads((ROOT / "model" / "WarehouseSim" / "data" / "config" / "run_config.json")
                                         .read_text())["horizon_s"]) + 60
MAX_DOTS = 80                                # worker dots drawn
# model start date: 2025-10-06 06:00 IST (charts show the clock; the animated run resets it to 06:00 local time)
START_MS = 1759708800000 + 30 * 60 * 1000

# ---- screen design: an operations board (Hallmark "Wayfind" material): cool grey paper, blue-black ink,
# one plain sans face, square 2px ink rules, cobalt for what is live, amber for figures on ink. No rounded cards, no shadows.
UI_FONT = "Lato"         # nominal; Main.pickFont() loads data/fonts/*.ttf and takes the first installed of FONTS
FONTS = ["Lato", "Segoe UI", "Helvetica Neue", "Arial", "Liberation Sans"]
PAPER, PAPER2, PAPER3 = "#EDF0F4", "#DDE2E7", "#FBFEFF"
INK, INK2, MUTED, RULE, INKRULE, INKMUTED = "#0A0D13", "#282B32", "#565B64", "#B9BEC5", "#34383F", "#9A9FA6"
ACCENT, AMBER = "#2055E1", "#F4B522"
PAGE_W, PAGE_H = 1410, 880                   # what fits one screen; the flowchart is below
HEAD_H = 60
COL_A, COL_B, COL_C = 24, 540, 990           # floor map | figures, order board, crew | charts
COL_A_W, COL_B_W, COL_C_W = 476, 420, 396
TOP = 80                                     # first line under the header
FRAME_Y, FRAME_H, KEY_W = 168, 684, 150      # floor map frame; the key sits right of it
FLOW_Y0 = 1000                               # the process flowchart starts here
COL = dict(PAPER=PAPER, PAPER2=PAPER2, PAPER3=PAPER3, INK=INK, INK2=INK2, MUTED=MUTED, RULE=RULE, INKRULE=INKRULE,
           ACCENT=ACCENT, AMBER=AMBER, IDLE=INKMUTED)
# end-of-day panel / console table: (label, Java expression on Main.endS = Kpi.summary(...))
END_ROWS = [
    ("Orders shipped", 'String.format("%d of %d arrived", (int) endD("orders_shipped"), (int) endD("orders_arrived"))'),
    ("Average fulfilment (arrival to packed)", 'String.format("%.1f min", endD("fulfil_mean_s") / 60)'),
    ("95th percentile fulfilment", 'String.format("%.1f min", endD("fulfil_p95_s") / 60)'),
    ("On time (packed by its cut-off)", 'String.format("%.1f %%", endD("on_time_pct"))'),
    ("Walk per picked order", 'String.format("%.1f m", endD("pick_m_per_order"))'),
    ("Total picking walk", 'String.format("%.2f km", endD("pick_m_total") / 1000)'),
    ("Carts", 'String.format("%d  (%.1f orders per cart)", (int) endD("tours"), endD("orders_per_tour"))'),
    ("Orders held for stock", 'String.valueOf((int) endD("held_orders"))'),
    ("Utilisation: pickers / packers", 'String.format("%.0f %% / %.0f %%", 100 * endD("util_pick"), 100 * endD("util_pack"))'),
    ("Utilisation: receivers / putaway", 'String.format("%.0f %% / %.0f %%", 100 * endD("util_recv"), 100 * endD("util_put"))'),
]


def jcolor(hexcol):
    return f"new Color(0x{hexcol.lstrip('#')})"


def jstr(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def layout_names():
    """layout id -> (title, detail) in plain words, from data/config/designs.json, whose order is
    as-is x 4 storage policies, then the recommended and the runner-up design (whsim.optimize)."""
    import json
    data = ROOT / "model" / "WarehouseSim" / "data"
    designs = json.loads((data / "config" / "designs.json").read_text())["designs"]
    files = [ln.strip() for ln in (data / "layouts" / "index.txt").read_text().split() if ln.strip()]
    storage = {"asis": "storage as recorded in the WMS", "random": "random storage",
               "class": "class-based storage (A/B/C zones)", "abc": "ABC storage by turnover"}
    base = designs[0]
    redesign = iter(["Recommended layout", "Runner-up layout"])
    out = {}
    for d, f in zip(designs, files):
        same = d["depot"] == base["depot"] and not d["cross_aisles"]
        if same:
            title = "As-is layout, real storage" if d["slotting"] == "asis" else \
                "As-is building, " + storage[d["slotting"]].split(" (")[0]
        else:
            title = next(redesign, "Candidate layout")
        ca = d["cross_aisles"]
        aisles = (f"{len(ca)} extra cross aisle{'s' if len(ca) > 1 else ''} at x = {' and '.join(f'{x:g}' for x in ca)} m"
                  if ca else "no extra cross aisles")
        st = storage.get(d["slotting"], d["slotting"])
        detail = (f"Picker depot at {d['depot'][0]:g}, {d['depot'][1]:g} m.\n{aisles[0].upper() + aisles[1:]}.\n"
                  f"{st[0].upper() + st[1:]}, {d['n_pack']} packing stations.")
        out[f.removesuffix(".json")] = (title, detail)
    return out


def core_java():
    """java/src/wh/*.java -> one block of static nested classes for Main's additional class code."""
    allowed = {ln.strip() for ln in GENERATED_IMPORTS.splitlines() if ln.startswith("import ")}
    out = []
    for c in CORE:
        src = (ROOT / "java" / "src" / "wh" / f"{c}.java").read_text()
        body = []
        for ln in src.splitlines():
            if ln.startswith("package "):
                continue
            if ln.startswith("import "):
                if ln.strip() not in allowed:
                    raise SystemExit(f"{c}.java: '{ln.strip()}' is not imported by AnyLogic; use the full name instead")
                continue
            body.append(ln)
        text = "\n".join(body).strip()
        text, n = re.subn(rf"^public final class {c}\b", f"public static final class {c}", text, flags=re.M)
        if n != 1:
            raise SystemExit(f"{c}.java must declare 'public final class {c}' at the top level")
        out.append(f"// ===== {c} (from java/src/wh/{c}.java) =====\n{text}")
    return "\n\n".join(out)


def build():
    m = Model(NAME, PACKAGE)
    main = m.agent("Main", entity=False)
    order = m.agent("Order")
    receipt = m.agent("Receipt")
    worker = m.agent("Worker")
    clock = m.agent("DayClock")
    tour = m.agent("PickTour")
    ticker = m.agent("Ticker")

    # ------------------------------------------------------------------ agent types
    # spec is a parameter, passed through the constructor (new Order(s)): Enter.take() creates the agent and
    # re-assigns plain-variable initial values, so a plain variable set before take() would be reset to null
    order.parameter("spec", "Main.ScenarioData.OrderSpec", "null", 20, 20)
    order.shadow.method("Order", "  public Order() {}\n  public Order(Main.ScenarioData.OrderSpec spec) { this.spec = spec; }")
    order.plain_var("reserved", "boolean", "false", 20, 60)
    order.plain_var("admitted", "boolean", "false", 20, 100)
    # one picking tour (cart) = a batch of orders, passed through the constructor like spec
    tour.parameter("orders", "ArrayList<Order>", "null", 20, 20)
    tour.shadow.method("PickTour", "  public PickTour() {}\n  public PickTour(ArrayList<Order> orders) { this.orders = orders; }")
    tour.plain_var("plan", "Main.Warehouse.PickPlan", "null", 20, 40)
    tour.plain_var("picker", "Worker", "null", 20, 60)
    receipt.parameter("spec", "Main.ScenarioData.ReceiptSpec", "null", 20, 20)
    receipt.shadow.method("Receipt", "  public Receipt() {}\n  public Receipt(Main.ScenarioData.ReceiptSpec spec) { this.spec = spec; }")
    receipt.plain_var("put", "Main.Warehouse.PutPlan", "null", 20, 40)
    receipt.plain_var("worker", "Worker", "null", 20, 60)
    worker.plain_var("role", "int", "0", 20, 20)        # 0 picker, 1 packer, 2 receiver, 3 putaway
    worker.plain_var("k", "int", "0", 20, 40)           # index within its role
    worker.plain_var("busyNow", "boolean", "false", 20, 60)
    worker.plain_var("motion", "Main.Router.Motion", "null", 20, 80)

    # ------------------------------------------------------------------ Main: parameters (all inputs are files)
    P = {}
    y = iter(range(20, 1000, 22))
    for name, jt, default in [
        ("layoutFile", "String", '"data/layouts/D40.3_63.1-P3-Xnone-asis.json"'),
        ("layoutIndex", "int", "-1"),
        ("scenarioFile", "String", '"data/scenarios/day_{seed}.csv"'),
        ("realDay", "int", "0"),
        ("skuFile", "String", '"data/skus.csv"'),
        ("configFile", "String", '"data/config/run_config.json"'),
        ("seed", "int", "1"),
        ("nPickers", "int", "-1"),
        ("nPackers", "int", "-1"),
        ("nReceivers", "int", "-1"),
        ("nPutaway", "int", "-1"),
        ("cartUnits", "int", "-1"),
        ("writeOrders", "boolean", "true"),
        ("skipQuietStart", "boolean", "true"),
        ("resultsDir", "String", '"results"'),
    ]:
        P[name] = main.parameter(name, jt, default, 1450, next(y))

    vy = iter(range(20, 1000, 22))
    for name, jt, init in [
        ("wh", "Warehouse", "null"),
        ("kpi", "Kpi", "null"),
        ("staff", "int[]", "new int[4]"),
        ("busy", "Stats.TimeLevel[]", "new Stats.TimeLevel[]{ new Stats.TimeLevel(), new Stats.TimeLevel(), new Stats.TimeLevel(), new Stats.TimeLevel() }"),
        ("workers", "ArrayList<Worker>", "new ArrayList<Worker>()"),
        ("roleCount", "int[]", "new int[4]"),
        ("layoutPath", "String", '""'),
        ("scenarioPath", "String", '""'),
        ("px", "double", "10"),
        ("ox", "double", str(COL_A + 8)),
        ("oy", "double", str(FRAME_Y + 8)),
        ("nArrived", "int", "0"),
        ("nPicked", "int", "0"),
        ("nPacked", "int", "0"),
        ("nShipped", "int", "0"),
        ("nTours", "int", "0"),
        ("animScale", "double", "60"),
        ("pending", "ArrayList<Order>", "new ArrayList<Order>()"),
        ("done", "boolean", "false"),
        ("uiFont", "String", '"SansSerif"'),
        ("liveT", "double", "-1"),
        ("liveV", "double[]", "null"),
        ("endS", "Map<String, Object>", "null"),
    ]:
        main.plain_var(name, jt, init, 1650, next(vy))
    # the generated agent class has this field; the shadow class needs it to compile the drawing code
    main.shadow.field("Main", "public ShapeTopLevelPresentationGroup presentation;")

    fy = iter(range(20, 2000, 22))

    def fn(name, ret, args, body, doc=""):
        body = re.sub(r"\bC_([A-Z0-9]+)\b", lambda mo: jcolor(COL[mo.group(1)]), body)     # palette colours
        main.function(name, ret, args, body.strip("\n"), 1850, next(fy), doc=doc)

    fn("setup", None, [], r"""
// 1. which files: layoutIndex >= 0 picks line layoutIndex of data/layouts/index.txt (used by the experiments)
layoutPath = layoutFile;
if (layoutIndex >= 0) {
	List<String> names = new ArrayList<String>();
	try {
		for (String s : java.nio.file.Files.readAllLines(java.nio.file.Paths.get("data/layouts/index.txt")))
			if (!s.trim().isEmpty()) names.add(s.trim());
	} catch (java.io.IOException e) {
		throw new IllegalArgumentException("cannot read data/layouts/index.txt: " + e.getMessage());
	}
	if (layoutIndex >= names.size())
		throw new IllegalArgumentException("layoutIndex = " + layoutIndex + " but data/layouts/index.txt lists " + names.size() + " layouts");
	layoutPath = "data/layouts/" + names.get(layoutIndex);
}
scenarioPath = scenarioFile.replace("{seed}", String.valueOf(seed));
// realDay k >= 1: replay the k-th historical day listed in data/scenarios/real_index.txt instead
if (realDay > 0) {
	List<String> days = new ArrayList<String>();
	try {
		for (String s : java.nio.file.Files.readAllLines(java.nio.file.Paths.get("data/scenarios/real_index.txt")))
			if (!s.trim().isEmpty()) days.add(s.trim());
	} catch (java.io.IOException e) {
		throw new IllegalArgumentException("cannot read data/scenarios/real_index.txt: " + e.getMessage());
	}
	if (realDay > days.size())
		throw new IllegalArgumentException("realDay = " + realDay + " but real_index.txt lists " + days.size() + " days");
	scenarioPath = "data/scenarios/" + days.get(realDay - 1);
}
// 2. load every input file and check them against each other (clear error message if anything is wrong)
wh = Warehouse.load(layoutPath, configFile, scenarioPath, skuFile, seed);
kpi = new Kpi(wh);
// 3. resources: from the run config unless a parameter (> 0) overrides it
staff[0] = nPickers > 0 ? nPickers : wh.cfg.pickers;
staff[1] = nPackers > 0 ? nPackers : wh.cfg.packers;
staff[2] = nReceivers > 0 ? nReceivers : wh.cfg.receivers;
staff[3] = nPutaway > 0 ? nPutaway : wh.cfg.putaway;
pickerPool.set_capacity(staff[0]);
packerPool.set_capacity(staff[1]);
receiverPool.set_capacity(staff[2]);
putawayPool.set_capacity(staff[3]);
if (cartUnits >= 0) wh.cfg.cartUnits = cartUnits;      // what-if: cart size (0 = single-order picking)
// 4. build the warehouse picture from the layout
drawLayout();
// 5. the workload enters the flowchart; each order / receipt line waits in its arrival delay until its time
// (the spec goes in through the agent's parameter constructor, as in AnyLogic's own examples)
for (ScenarioData.OrderSpec s : wh.scenario.orders) orderIn.take(new Order(s));
for (ScenarioData.ReceiptSpec s : wh.scenario.receipts) receiptIn.take(new Receipt(s));
dayClockIn.take(new DayClock());
tickIn.take(new Ticker());
// animation: nothing happens before the first WMS release (often ~07:30), so fast-forward to 5 min before it
// (only in a real-time run, i.e. the animated Simulation experiment; the experiments without animation are untouched)
if (skipQuietStart && getEngine().getRealTimeMode() && !wh.scenario.orders.isEmpty()
		&& wh.scenario.orders.get(0).t - 300 > time()) {
	animScale = getEngine().getRealTimeScale();
	getEngine().setRealTimeMode(false);
	wakeIn.take(new DayClock());
	traceln(String.format("fast-forwarding to %02d:%02d (5 min before the first order release)",
		6 + (int) (wh.scenario.orders.get(0).t - 300) / 3600, (int) (wh.scenario.orders.get(0).t - 300) % 3600 / 60));
}
traceln("WarehouseSim: layout " + wh.layout.id + " (" + layoutPath + "), " + wh.scenario.orders.size() + " orders and "
	+ wh.scenario.receipts.size() + " receipt lines from " + scenarioPath + ", seed " + seed
	+ ", staff pick/pack/receive/putaway = " + staff[0] + "/" + staff[1] + "/" + staff[2] + "/" + staff[3]);
""", "Loads the input files, sizes the resource pools, draws the layout and starts the workload.")

    fn("registerWorker", None, [("Worker", "u"), ("int", "role")], """
u.role = role;
u.k = roleCount[role]++;
workers.add(u);
""", "Called by each pool for every new unit.")

    fn("admit", "boolean", [("Order", "a")], """
// runs once per order (the flag makes it safe if the condition is evaluated again)
if (!a.admitted) {
	a.admitted = true;
	nArrived++;
	kpi.orderArrived(a.spec, time());
	a.reserved = wh.inv.tryReserve(a.spec);
	if (a.reserved) kpi.orderReleased(a.spec, time());
	else kpi.orderHeld(a.spec, time());
}
return a.reserved;
""", "Stock check when the order arrives: reserve every line now (true), or hold the order until a putaway brings the missing stock (false).")

    fn("retryHeld", None, [], """
// first decide (oldest order first), then release: the Wait block changes while agents leave it
ArrayList<Order> go = new ArrayList<Order>();
for (int i = 0; i < holdWait.size(); i++) {
	Order o = holdWait.get(i);
	if (wh.inv.tryReserve(o.spec)) go.add(o);
}
for (Order o : go) {
	kpi.orderReleased(o.spec, time());
	holdWait.free(o);
}
""", "After every putaway: release the held orders whose lines are now all in stock.")

    fn("dispatch", None, [], """
// a free picker takes the next cart (Warehouse.formBatch) as soon as the wave release rule allows it;
// pending = released orders that are waiting in pickPool and are not on a cart yet, oldest first
while (!pending.isEmpty()) {
	if (pickerPool.idle() <= tourSeize.size()) return;      // every free picker already has a cart waiting
	List<ScenarioData.OrderSpec> specs = new ArrayList<ScenarioData.OrderSpec>();
	for (Order o : pending) specs.add(o.spec);
	if (!wh.releaseNow(specs, kpi.oRel[specs.get(0).index], time())) return;
	int[] pos = wh.formBatch(specs);
	ArrayList<Order> batch = new ArrayList<Order>();
	for (int i = pos.length - 1; i >= 0; i--) batch.add(0, pending.remove(pos[i]));
	tourIn.take(new PickTour(batch));
}
""", "Wave release: forms picking carts from the waiting orders and starts them on free pickers.")

    fn("beginTour", "double", [("PickTour", "a")], """
if (a.plan == null) {       // plan once (the delay time may be evaluated more than once)
	List<ScenarioData.OrderSpec> specs = new ArrayList<ScenarioData.OrderSpec>();
	for (Order o : a.orders) {
		specs.add(o.spec);
		kpi.pickStarted(o.spec, time());
	}
	a.plan = wh.planBatch(specs, time());
	// the picker this cart seized (asked from the pool, so it does not depend on callback order)
	if (a.picker == null) a.picker = (Worker) a.resourceUnitOfPool(pickerPool);
	if (a.picker != null) a.picker.motion = a.plan.motion;
	if (nTours == 0 && pickerPool.busy() == 1)
		traceln(String.format("first cart at %02d:%02d: %d orders, %d stops, %.0f m, %.0f s, picker %s",
			6 + (int) time() / 3600, (int) time() % 3600 / 60, a.orders.size(), a.plan.stops, a.plan.length, a.plan.duration,
			a.picker == null ? "NOT FOUND (no animation)" : "#" + (a.picker.k + 1)));
}
return a.plan.duration;
""", "Plans the cart's tour (depot -> all its slots -> packing station -> depot); returns its duration in seconds.")

    fn("endTour", None, [("PickTour", "a")], """
for (Order o : a.orders) {
	nPicked++;
	wh.inv.consume(o.spec);
	kpi.pickEnded(o.spec, time(), a.plan);
}
kpi.tourEnded(a.plan);
nTours++;
if (a.picker != null) a.picker.motion = null;
for (Order o : a.orders) pickPool.free(o);      // the picked orders go on to packing
""")

    fn("stageTime", "double", [("Order", "a")], """
if (Double.isNaN(kpi.oPacked[a.spec.index])) {     // once per order
	nPacked++;
	kpi.orderPacked(a.spec, time());
}
double c = wh.cfg.nextCutoff(time());
return c < Double.POSITIVE_INFINITY ? c - time() : 10 * STOP_TIME;
""".replace("STOP_TIME", str(STOP_TIME)), "Packed: wait in staging until the next carrier cut-off.")

    fn("orderShipped", None, [("Order", "a")], """
nShipped++;
kpi.orderShipped(a.spec, time());
""")

    fn("beginPutaway", "double", [("Receipt", "a")], """
if (a.put == null) {
	kpi.putawayStarted(a.spec, time());
	a.put = wh.planPutaway(a.spec, time());
	if (a.worker == null) a.worker = (Worker) a.resourceUnitOfPool(putawayPool);
	if (a.worker != null) a.worker.motion = a.put.motion;
}
return a.put.duration;
""", "Plans the putaway trip (inbound dock -> slot -> dock); returns its duration in seconds.")

    fn("endPutaway", None, [("Receipt", "a")], """
wh.inv.receive(a.spec.sku, a.spec.qty);
kpi.putawayEnded(a.spec, time(), a.put);
if (a.worker != null) a.worker.motion = null;
retryHeld();
""")

    fn("finishRun", None, [], """
if (done) return;
done = true;
double T = time();
double[] util = new double[4];
for (int k = 0; k < 4; k++) util[k] = busy[k].mean(T) / staff[k];
Map<String, Object> s = kpi.summary(T, new java.io.File(scenarioPath).getName(), staff, util);
Kpi.appendSummary(resultsDir + "/runs.csv", s);
if (writeOrders) kpi.writeOrders(resultsDir + "/orders_" + wh.layout.id + "_s" + seed + ".csv");
endS = s;                                  // shown by the end-of-day panel
StringBuilder tb = new StringBuilder();
String rule = "+" + "-".repeat(66) + "+";
tb.append(rule).append(String.format("%n| %-64s |%n| %-64s |%n", "End of day: " + layoutTitle(),
	wh.layout.id + ", " + new java.io.File(scenarioPath).getName() + ", seed " + seed)).append(rule);
for (int i = 0; i < END_ROWS_N; i++) tb.append(String.format("%n| %-38s %25s |", endLabel(i), endText(i)));
tb.append(String.format("%n")).append(rule).append(String.format("%n  appended to %s/runs.csv", resultsDir));
traceln(tb.toString());
traceln(String.format("WarehouseSim done: %s seed %d | shipped %s of %s | fulfil mean %.0f s, p95 %.0f s | on time %.1f%% | pick %.1f m/order | util pick %.2f pack %.2f recv %.2f put %.2f",
	wh.layout.id, seed, Kpi.fmt(s.get("orders_shipped")), Kpi.fmt(s.get("orders_arrived")), (Double) s.get("fulfil_mean_s"),
	(Double) s.get("fulfil_p95_s"), (Double) s.get("on_time_pct"), (Double) s.get("pick_m_per_order"), util[0], util[1], util[2], util[3]));
finishSimulation();
""".replace("END_ROWS_N", str(len(END_ROWS))), "End of the day (horizon_s): writes results/runs.csv (+ the per-order file) and stops the run.")

    # ---- drawing (runtime-built picture of the layout)
    fn("cellColor", "Color", [("String", "t")], """
switch (t) {
	case "#": return C_INK;                     // wall
	case "A": return C_PAPER3;                  // aisle
	case "S": return new Color(0xA7ADB6);       // shelf
	case "DI": return C_INK2;                   // inbound dock
	case "DO": return C_INK2;                   // outbound dock
	case "R": return new Color(0xF6DC97);       // receiving
	case "PK": return C_AMBER;                  // packing station
	case "G": return new Color(0xC3CFF3);       // staging
	case "H": return C_ACCENT;                  // picker depot
	default: return C_PAPER3;
}
""")

    fn("sx", "double", [("double", "x")], "return ox + (x - wh.layout.originX) * px;", "Screen x of a layout x (metres).")
    fn("sy", "double", [("double", "y")], "return oy + (wh.layout.originY + wh.layout.heightM() - y) * px;",
       "Screen y of a layout y (metres); y points up, so the front of the building is at the bottom.")

    fn("drawLayout", None, [], """
if (presentation == null) return;          // no animation in this experiment
pickFont();
// the charts label their time axis with the clock: model time 0 = 06:00 of the simulated day (local time zone)
try {
	Calendar c = Calendar.getInstance();
	c.setTime(getEngine().getStartDate());
	c.set(Calendar.HOUR_OF_DAY, 6); c.set(Calendar.MINUTE, 0); c.set(Calendar.SECOND, 0); c.set(Calendar.MILLISECOND, 0);
	getEngine().setStartDate(c.getTime());
} catch (RuntimeException e) {
	traceln("chart clock labels: start date kept (" + e.getMessage() + ")");
}
LayoutData L = wh.layout;
// the floor map fills its column: the frame is FRAME_H tall, the key takes KEY_W on its right
px = Math.min((COL_A_W - 16 - 18 - KEY_W) / L.widthM(), (FRAME_H - 16) / L.heightM());
double W = L.widthM() * px, H = L.heightM() * px;
double cw = L.cellW * px, ch = L.cellH * px;
int k = 0;                                 // insert at the bottom so the dashboard and the worker dots stay on top
presentation.insert(k++, box(0, 0, PAGE_W, PAGE_H, C_PAPER, null, 0));
presentation.insert(k++, box(COL_A, FRAME_Y, W + 16, H + 16, C_PAPER3, C_INK, 2));
for (int r = 0; r < L.rows; r++) {
	for (int q = 0; q < L.cols; q++) {
		ShapeRectangle s = new ShapeRectangle();
		s.setPos(sx(L.originX + q * L.cellW), sy(L.originY + (r + 1) * L.cellH));
		s.setSize(cw, ch);
		s.setFillColor(cellColor(L.grid[r][q]));
		s.setLineColor(C_PAPER3);
		s.setLineWidth(0.5);
		presentation.insert(k++, s);
	}
}
// key, right of the map: what the cell colours and the worker dots mean
String[] cell = {"A", "S", "#", "R", "PK", "G", "DI", "H"};
String[] cellName = {"aisle", "shelf", "wall", "receiving", "packing station", "staging", "dock", "picker depot"};
double x = COL_A + W + 16 + 18, y = FRAME_Y;
presentation.insert(k++, label(x, y, "Floor", C_INK, 12, true));
y += 24;
for (int i = 0; i < cell.length; i++) {
	presentation.insert(k++, box(x, y + 1, 12, 12, cellColor(cell[i]), C_INK, 1));
	presentation.insert(k++, label(x + 20, y, cellName[i], C_INK2, 11, false));
	y += 20;
}
y += 16;
presentation.insert(k++, label(x, y, "Workers", C_INK, 12, true));
y += 24;
String[] who = {"picker", "putaway", "packer", "receiver", "idle"};
int[] whoRole = {0, 3, 1, 2, -1};
String[] how = {"walks a cart tour", "walks to the slot", "works at a packing station", "works at receiving", "waits at its station"};
for (int i = 0; i < who.length; i++) {
	ShapeOval o = new ShapeOval();
	o.setPos(x + 6, y + 7);
	o.setRadius(5.5);
	o.setFillColor(whoRole[i] >= 0 ? roleColor(whoRole[i]) : C_IDLE);
	o.setLineColor(C_PAPER3);
	o.setLineWidth(1.5);
	presentation.insert(k++, o);
	presentation.insert(k++, label(x + 20, y, who[i], C_INK2, 11, false));
	presentation.insert(k++, label(x + 20, y + 14, how[i], C_MUTED, 9, false));
	y += 32;
}
y += 16;
presentation.insert(k++, label(x, y, L.cols + " x " + L.rows + " cells\\n" + String.format("%.2f x %.2f m each", L.cellW, L.cellH)
	+ "\\n" + L.slotId.length + " slots", C_MUTED, 10, false));
""".replace("COL_A_W", f"{COL_A_W:.1f}").replace("FRAME_H", f"{FRAME_H:.1f}").replace("KEY_W", f"{KEY_W:.1f}")
       .replace("COL_A", str(COL_A)).replace("FRAME_Y", str(FRAME_Y)).replace("PAGE_W", str(PAGE_W)).replace("PAGE_H", str(PAGE_H)),
       "Draws the layout read from the JSON file (page, framed floor map, facility labels, the key).")

    fn("box", "ShapeRectangle", [("double", "x"), ("double", "y"), ("double", "w"), ("double", "h"), ("Color", "fill"),
                                 ("Color", "line"), ("double", "lw")], """
ShapeRectangle s = new ShapeRectangle();
s.setPos(x, y);
s.setSize(w, h);
s.setFillColor(fill);
s.setLineColor(line);
s.setLineWidth(line == null ? 0 : lw);
return s;
""", "A square filled rectangle for the runtime-drawn picture; line null = no rule.")

    fn("label", "ShapeText", [("double", "x"), ("double", "y"), ("String", "text"), ("Color", "c"), ("int", "size"),
                              ("boolean", "bold")], """
ShapeText t = new ShapeText();
t.setPos(x, y);
t.setText(text);
t.setColor(c);
t.setFont(new Font(uiFont, bold ? Font.BOLD : Font.PLAIN, size));
return t;
""", "A text in the board typeface.")

    fn("pickFont", None, [], """
// one typeface for the whole screen: fonts shipped in data/fonts are registered first, then the first installed one wins
java.io.File[] files = new java.io.File("data/fonts").listFiles();
if (files != null) {
	for (java.io.File f : files) {
		String n = f.getName().toLowerCase();
		if (!n.endsWith(".ttf") && !n.endsWith(".otf")) continue;
		try {
			java.awt.GraphicsEnvironment.getLocalGraphicsEnvironment().registerFont(Font.createFont(Font.TRUETYPE_FONT, f));
		} catch (Exception e) {
			traceln("font " + f.getName() + " not loaded: " + e.getMessage());
		}
	}
}
String[] want = FONTS;
Set<String> have = new HashSet<String>(Arrays.asList(java.awt.GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames()));
for (String f : want) {
	if (have.contains(f)) {
		uiFont = f;
		break;
	}
}
restyle(presentation);
""".replace("FONTS", "{" + ", ".join(jstr(f) for f in FONTS) + "}"),
       "Chooses the board typeface and applies it to every text drawn by the model.")

    fn("restyle", None, [("ShapeGroup", "g")], """
for (int i = 0; i < g.size(); i++) {
	Object o = g.get(i);
	if (o instanceof ShapeText) {
		ShapeText t = (ShapeText) o;
		Font f = t.getFont();
		if (f != null) t.setFont(new Font(uiFont, f.getStyle(), f.getSize()));
	} else if (o instanceof ShapeGroup) {
		restyle((ShapeGroup) o);
	}
}
""")

    fn("homeXY", "double[]", [("Worker", "u")], """
LayoutData L = wh.layout;
List<LayoutData.Facility> list;
switch (u.role) {
	case 1: list = wh.facilities("PK"); break;
	case 2: list = wh.facilities("R"); break;
	case 3: list = wh.facilities("DI"); break;
	default: return wh.depotXY();
}
LayoutData.Facility f = list.get(u.k % list.size());
return new double[]{f.x, f.y};
""", "Where an idle worker is drawn: pickers at the depot, packers at stations, receivers at R, putaway at DI.")

    fn("workerXY", "double[]", [("int", "i")], """
Worker u = workers.get(i);
if (u.motion != null) {                    // walking: exactly on its route (an offset would put it in a rack or a wall)
	double[] p = u.motion.at(time());
	return new double[]{sx(p[0]), sy(p[1])};
}
// at its station: workers that share one stand side by side, 4 to a row, in screen pixels
double[] p = homeXY(u);
int n = u.k / homeShare(u.role);
return new double[]{sx(p[0]) + (n % 4 - 1.5) * 8, sy(p[1]) + (n / 4) * 8};
""")

    fn("homeShare", "int", [("int", "role")], """
switch (role) {
	case 1: return Math.max(1, wh.facilities("PK").size());
	case 2: return Math.max(1, wh.facilities("R").size());
	case 3: return Math.max(1, wh.facilities("DI").size());
	default: return 1;
}
""", "How many stations the workers of a role are shared over (homeXY puts unit k at station k % n).")

    fn("workerVisible", "boolean", [("int", "i")], "return wh != null && i < workers.size();")

    fn("roleColor", "Color", [("int", "role")], """
switch (role) {
	case 0: return C_ACCENT;                   // picker
	case 1: return new Color(0xE8590C);        // packer
	case 2: return C_AMBER;                    // receiver
	default: return new Color(0x12A150);       // putaway
}
""")

    fn("workerColor", "Color", [("int", "i")], """
Worker u = workers.get(i);
return u.busyNow ? roleColor(u.role) : C_IDLE;
""")

    # ---- the board: header, three comparison figures, the order board, the crew, the end-of-day panel
    names = layout_names()
    fn("layoutTitle", "String", [], "if (wh == null) return \"Loading the layout\";\nswitch (wh.layout.id) {\n"
       + "".join(f"\tcase {jstr(i)}: return {jstr(t)};\n" for i, (t, _) in names.items())
       + "\tdefault: return \"Layout \" + wh.layout.id;\n}", "The layout in plain words (from data/config/designs.json).")
    fn("layoutDetail", "String", [], "if (wh == null) return \"\";\nswitch (wh.layout.id) {\n"
       + "".join(f"\tcase {jstr(i)}: return {jstr(d)};\n" for i, (_, d) in names.items())
       + "\tdefault: return \"Slotting \" + wh.layout.slotting + \".\";\n}")

    fn("clockText", "String", [], "return clockOf(time());", "Time of day (model time 0 = 06:00).")

    fn("clockOf", "String", [("double", "t")], """
long s = (long) t;
return String.format("%02d:%02d", (6 + s / 3600) % 24, (s / 60) % 60);
""")

    fn("dayText", "String", [], """
if (wh == null) return "";
String day = new java.io.File(scenarioPath).getName().replace(".csv", "").replace("_", " ");
day = day.substring(0, 1).toUpperCase() + day.substring(1);
return day + ", seed " + seed + ", 06:00 to " + clockOf(wh.cfg.horizon);
""")

    fn("fastText", "String", [], """
return wh != null && !done && time() > 0 && !getEngine().getRealTimeMode() ? "Skipping ahead to the first order release" : "";
""")

    fn("dayProgress", "double", [], "return wh == null ? 0 : Math.max(0, Math.min(1, time() / wh.cfg.horizon));")

    fn("liveKpi", "double[]", [], """
// {mean fulfilment so far (min), on time so far (%), orders due so far, orders ever held, orders released};
// computed once per model time
if (kpi == null) return new double[]{Double.NaN, Double.NaN, 0, 0, 0};
double t = time();
if (liveV != null && t == liveT) return liveV;
double sum = 0;
int n = 0, due = 0, ok = 0, everHeld = 0, released = 0;
for (int i = 0; i < kpi.oArr.length; i++) {
	if (Double.isNaN(kpi.oArr[i])) continue;
	if (kpi.oHeld[i]) everHeld++;
	if (!Double.isNaN(kpi.oRel[i])) released++;
	if (!Double.isNaN(kpi.oPacked[i])) {
		sum += kpi.oPacked[i] - kpi.oArr[i];
		n++;
	}
	if (kpi.oDue[i] <= t) {          // due at a cut-off that has passed (as in Kpi.summary)
		due++;
		if (!Double.isNaN(kpi.oPacked[i]) && kpi.oPacked[i] <= kpi.oDue[i]) ok++;
	}
}
liveT = t;
liveV = new double[]{n > 0 ? sum / n / 60 : Double.NaN, due > 0 ? 100.0 * ok / due : Double.NaN, due, everHeld, released};
return liveV;
""", "Running KPIs for the board and the charts.")

    fn("walkPerOrder", "double", [], "return kpi == null || kpi.tourOrders == 0 ? Double.NaN : kpi.tourM / kpi.tourOrders;",
       "Picking walk per picked order so far (m) = the orders' share of their carts' tours.")
    fn("utilSoFar", "double", [("int", "k")], "return time() > 0 && staff[k] > 0 ? busy[k].mean(time()) / staff[k] : 0;",
       "Utilisation of role k since 06:00 (0 pickers, 1 packers, 2 receivers, 3 putaway).")

    fn("plotValue", "double", [("double", "x")], "return Double.isNaN(x) || Double.isInfinite(x) ? 0 : x;",
       "Every chart value goes through this: AnyLogic's charts do not handle NaN (no value yet) and the run breaks.")

    fn("figValue", "String", [("int", "i")], """
if (wh == null) return "\\u2013";
double[] v = liveKpi();
switch (i) {
	case 0: return Double.isNaN(walkPerOrder()) ? "\\u2013" : String.format("%.0f m", walkPerOrder());
	case 1: return Double.isNaN(v[0]) ? "\\u2013" : String.format("%.0f min", v[0]);
	default: return Double.isNaN(v[1]) ? "\\u2013" : String.format("%.0f%%", v[1]);
}
""", "The three figures layouts are compared on.")

    fn("figNote", "String", [("int", "i")], """
if (wh == null) return "";
double[] v = liveKpi();
switch (i) {
	case 0: return kpi.tours > 0 ? String.format("%.1f km, %d carts", kpi.tourM / 1000, kpi.tours) : "no cart back yet";
	case 1: return nPacked > 0 ? "mean of " + nPacked + " orders" : "none packed yet";
	default: return (int) v[2] > 0 ? "of " + (int) v[2] + " orders due" : "no cut-off yet";
}
""")

    fn("boardNow", "int", [("int", "i")], """
if (wh == null) return 0;
switch (i) {
	case 0: return (int) kpi.held.value();
	case 1: return pending.size();
	case 2: return pickPool.size() - pending.size();
	case 3: return nPicked - nPacked;
	default: return (int) kpi.staging.value();
}
""", "Orders at board row i now: held, waiting for a cart, on a cart, packing, staging.")

    fn("boardSoFar", "String", [("int", "i")], """
if (wh == null) return "";
double[] v = liveKpi();
switch (i) {
	case 0: return (int) v[3] + " held today";
	case 1: return (int) v[4] + " released";
	case 2: return nPicked + " picked";
	case 3: return nPacked + " packed";
	default: return nShipped + " shipped";
}
""")

    fn("crewText", "String", [("int", "k")], """
if (wh == null) return "";
ResourcePool[] pools = {pickerPool, packerPool, receiverPool, putawayPool};
return pools[k].busy() + " of " + staff[k] + " busy";
""")

    fn("crewBusyNow", "double", [("int", "k")], """
if (wh == null || staff[k] == 0) return 0;
ResourcePool[] pools = {pickerPool, packerPool, receiverPool, putawayPool};
return (double) pools[k].busy() / staff[k];
""")

    fn("inboundText", "String", [], """
if (wh == null) return "";
return String.format("Receiving buffer holds %d of %d lines.%n%,d units on the shelves.",
	(int) kpi.recvBuffer.value(), wh.recvBufferCapacity(), wh.inv.totalOnHand());
""")

    fn("endD", "double", [("String", "key")], """
Object o = endS == null ? null : endS.get(key);
return o instanceof Number ? ((Number) o).doubleValue() : Double.NaN;
""")
    fn("endLabel", "String", [("int", "i")], "switch (i) {\n"
       + "".join(f"\tcase {i}: return {jstr(lab)};\n" for i, (lab, _) in enumerate(END_ROWS)) + "\tdefault: return \"\";\n}")
    fn("endText", "String", [("int", "i")], "if (endS == null) return \"\";\nswitch (i) {\n"
       + "".join(f"\tcase {i}: return {expr};\n" for i, (_, expr) in enumerate(END_ROWS)) + "\tdefault: return \"\";\n}",
       "Value column of the end-of-day panel (and the console table).")

    # ------------------------------------------------------------------ flowchart
    X0, Y0 = 40, FLOW_Y0
    xs = lambda i: X0 + 90 * i   # noqa: E731
    sec = lambda code: ("unit", code, "TimeUnits", "SECOND")   # noqa: E731
    # outbound
    main.block("orderIn", "Enter", xs(0), Y0, "Order")
    main.block("orderArrive", "Delay", xs(1), Y0, "Order", delayTime=sec("max(0, agent.spec.t - time())"),
               maximumCapacity=True)
    main.block("stockCheck", "SelectOutput", xs(2), Y0, "Order", conditionIsProbabilistic=False, condition="admit(agent)")
    main.block("holdWait", "Wait", xs(2) + 45, Y0 + 70, "Order", maximumCapacity=True)
    # released orders wait here until their cart's tour is over (Main.dispatch / endTour)
    main.block("pickPool", "Wait", xs(4), Y0, "Order", maximumCapacity=True,
               onEnter="pending.add(agent);\ndispatch();")
    main.block("pack", "Service", xs(6), Y0, "Order", seizeFromOnePool=True, resourcePool="packerPool",
               resourceQuantity="1", maximumCapacity=True, movingGoHome=False, delayTime=sec("wh.packTime(agent.spec)"))
    main.block("staging", "Delay", xs(7), Y0, "Order", delayTime=sec("stageTime(agent)"), maximumCapacity=True,
               onExit="orderShipped(agent);")
    main.block("shipped", "Sink", xs(8), Y0, "Order")
    for a, pa, b, pb in [("orderIn", "out", "orderArrive", "in"), ("orderArrive", "out", "stockCheck", "in"),
                         ("stockCheck", "outT", "pickPool", "in"), ("stockCheck", "outF", "holdWait", "in"),
                         ("holdWait", "out", "pickPool", "in"), ("pickPool", "out", "pack", "in"),
                         ("pack", "out", "staging", "in"), ("staging", "out", "shipped", "in")]:
        main.connect(a, pa, b, pb)
    # picking tours (one agent per cart)
    YT = Y0 + 110
    main.block("tourIn", "Enter", xs(3), YT, "PickTour")
    main.block("tourSeize", "Seize", xs(4), YT, "PickTour", seizeFromOnePool=True, resourcePool="pickerPool",
               resourceQuantity="1", maximumCapacity=True, onSeizeUnit="agent.picker = (Worker) unit;")
    main.block("tourWalk", "Delay", xs(5), YT, "PickTour", delayTime=sec("beginTour(agent)"), maximumCapacity=True,
               onExit="endTour(agent);")
    main.block("tourRelease", "Release", xs(6), YT, "PickTour", movingGoHome=False, onExit="dispatch();")
    main.block("tourDone", "Sink", xs(7), YT, "PickTour")
    for a, pa, b, pb in [("tourIn", "out", "tourSeize", "in"), ("tourSeize", "out", "tourWalk", "in"),
                         ("tourWalk", "out", "tourRelease", "in"), ("tourRelease", "out", "tourDone", "in")]:
        main.connect(a, pa, b, pb)
    # inbound
    Y1 = YT + 120
    main.block("receiptIn", "Enter", xs(0), Y1, "Receipt")
    main.block("receiptArrive", "Delay", xs(1), Y1, "Receipt", delayTime=sec("max(0, agent.spec.t - time())"),
               maximumCapacity=True, onExit="kpi.receiptArrived(agent.spec, time());")
    main.block("receive", "Service", xs(2), Y1, "Receipt", seizeFromOnePool=True, resourcePool="receiverPool",
               resourceQuantity="1", maximumCapacity=True, movingGoHome=False,
               delayTime=sec("wh.receiveTime(agent.spec)"), onExit="kpi.received(agent.spec, time());")
    main.block("putSeize", "Seize", xs(3), Y1, "Receipt", seizeFromOnePool=True, resourcePool="putawayPool",
               resourceQuantity="1", maximumCapacity=True, onSeizeUnit="agent.worker = (Worker) unit;")
    main.block("putWalk", "Delay", xs(4), Y1, "Receipt", delayTime=sec("beginPutaway(agent)"), maximumCapacity=True,
               onExit="endPutaway(agent);")
    main.block("putRelease", "Release", xs(5), Y1, "Receipt", movingGoHome=False)
    main.block("stored", "Sink", xs(6), Y1, "Receipt")
    for a, pa, b, pb in [("receiptIn", "out", "receiptArrive", "in"), ("receiptArrive", "out", "receive", "in"),
                         ("receive", "out", "putSeize", "in"), ("putSeize", "out", "putWalk", "in"),
                         ("putWalk", "out", "putRelease", "in"), ("putRelease", "out", "stored", "in")]:
        main.connect(a, pa, b, pb)
    # end of day
    Y2 = Y1 + 110
    main.block("dayClockIn", "Enter", xs(0), Y2, "DayClock")
    main.block("endOfDay", "Delay", xs(1), Y2, "DayClock", delayTime=sec("max(0, wh.cfg.horizon - time())"),
               maximumCapacity=True, onExit="finishRun();")
    main.block("dayEnd", "Sink", xs(2), Y2, "DayClock")
    main.connect("dayClockIn", "out", "endOfDay", "in")
    # animation only: back to the chosen real-time speed 5 min before the first order release
    main.block("wakeIn", "Enter", xs(8), Y2, "DayClock")
    main.block("wakeUp", "Delay", xs(9), Y2, "DayClock",
               delayTime=sec("max(0, wh.scenario.orders.get(0).t - 300 - time())"), maximumCapacity=True,
               onExit="getEngine().setRealTimeMode(true);\ngetEngine().setRealTimeScale(animScale);")
    main.block("wakeOut", "Sink", xs(10), Y2, "DayClock")
    main.connect("wakeIn", "out", "wakeUp", "in")
    main.connect("wakeUp", "out", "wakeOut", "in")
    main.connect("endOfDay", "out", "dayEnd", "in")
    # wave release re-check every tick_s (orders that have waited max_wait_s get a cart)
    main.block("tickIn", "Enter", xs(4), Y2, "Ticker")
    main.block("tick", "Delay", xs(5), Y2, "Ticker", delayTime=sec("wh.cfg.tick"), maximumCapacity=True,
               onExit="dispatch();\nif (time() + wh.cfg.tick <= wh.cfg.horizon) tickIn.take(new Ticker());")
    main.block("tickOut", "Sink", xs(6), Y2, "Ticker")
    main.connect("tickIn", "out", "tick", "in")
    main.connect("tick", "out", "tickOut", "in")
    # resource pools (sized in setup())
    for i, (pool, label) in enumerate([("pickerPool", "pickers"), ("packerPool", "packers"),
                                       ("receiverPool", "receivers"), ("putawayPool", "putaway workers")]):
        main.block(pool, "ResourcePool", xs(10) + 90 * (i % 2), Y0 + 90 * (i // 2), "Worker", capacity="0",
                   newUnit=("entity", worker), showDefaultAnimationStatic=False,
                   onNewUnit=f"registerWorker(unit, {i});",
                   onSeize=f"busy[{i}].add(time(), 1);\nunit.busyNow = true;",
                   onRelease=f"busy[{i}].add(time(), -1);\nunit.busyNow = false;")

    main.startup = "setup();"
    main.shadow.method("Main", "  void _startup() {\n" + main.startup + "\n  }")
    core = core_java()
    main.additional = core
    main.shadow.cls("Main")["extra"].append(core)

    # ------------------------------------------------------------------ presentation
    # static board; the page, the framed floor map and its key are drawn at start-up by drawLayout(), under these
    sh = Shapes(main, font=UI_FONT)
    # header: what this is, which day, the clock (amber figure on ink), day progress (cobalt = live)
    sh.rect(0, 0, PAGE_W, HEAD_H, fill=INK, line=None, name="headerBar")
    sh.text(COL_A, 10, "Warehouse floor simulation", size=18, bold=True, col=PAPER3)
    sh.text(COL_A, 36, "", size=11, col=INKMUTED, name="dayInfo", TextCode="dayText()")
    sh.text(PAGE_W - 24, 9, "", size=30, bold=True, col=AMBER, align="RIGHT", name="clock", TextCode="clockText()")
    sh.text(PAGE_W - 140, 24, "", size=11, col=PAPER3, align="RIGHT", name="fastForward", TextCode="fastText()")
    sh.rect(0, HEAD_H - 3, PAGE_W, 3, fill=ACCENT, line=None, name="dayBar", WidthCode=f"{PAGE_W} * dayProgress()")
    # column A: the layout in words above its map
    sh.text(COL_A, TOP, "", size=20, bold=True, col=INK, name="layoutName", TextCode="layoutTitle()")
    sh.text(COL_A, TOP + 30, "", size=11, col=MUTED, name="layoutWords", TextCode="layoutDetail()")
    # column B, 1: the three figures layouts are compared on, in ruled cells joined edge to edge
    figs = ["Walk per order", "Arrival to packed", "Packed by cut-off"]
    cw = COL_B_W / len(figs)
    sh.rect(COL_B, TOP, COL_B_W, 104, fill=PAPER3, line=INK, lw=2)
    for i, lab in enumerate(figs):
        x = COL_B + i * cw
        if i:
            sh.rect(x - 1, TOP, 2, 104, fill=INK, line=None)
        sh.text(x + 12, TOP + 10, lab, size=11, col=MUTED)
        sh.text(x + 12, TOP + 30, "", size=28, bold=True, col=INK, name=f"fig{i}", TextCode=f"figValue({i})")
        sh.text(x + 12, TOP + 76, "", size=10, col=MUTED, TextCode=f"figNote({i})")
    # column B, 2: the order board, stage by stage like a departures board (amber figures on ink)
    bx, by, bw = COL_B, TOP + 124, COL_B_W
    rows = ["Waiting for stock", "Waiting for a cart", "On a cart", "Packing", "In staging"]
    rh, r0 = 42, by + 74
    sh.rect(bx, by, bw, 74 + rh * len(rows) + 10, fill=INK, line=INK, lw=2)
    sh.text(bx + 16, by + 14, "Orders", size=14, bold=True, col=PAPER3)
    sh.text(bx + bw - 16, by + 17, "", size=11, col=INKMUTED, align="RIGHT",
            TextCode='wh == null ? "" : nArrived + " of " + wh.scenario.orders.size() + " arrived"')
    sh.rect(bx + 16, by + 42, bw - 32, 2, fill=PAPER3, line=None)
    sh.text(bx + 16, by + 52, "Stage", size=10, col=INKMUTED)
    sh.text(bx + 262, by + 52, "Now", size=10, col=INKMUTED, align="RIGHT")
    sh.text(bx + bw - 16, by + 52, "Today", size=10, col=INKMUTED, align="RIGHT")
    for i, lab in enumerate(rows):
        ry = r0 + rh * i
        alarm = "boardNow(0) > 0" if i == 0 else None       # held orders: the row turns amber, like a late train
        if alarm:
            sh.rect(bx + 2, ry, bw - 4, rh, fill=AMBER, line=None, VisibleCode=alarm)
        on = lambda c_on, c_off: {"ColorCode": f"{alarm} ? {jcolor(c_on)} : {jcolor(c_off)}"} if alarm else {}  # noqa: E731
        sh.text(bx + 16, ry + 13, lab, size=12, col=PAPER3, **on(INK, PAPER3))
        sh.text(bx + 262, ry + 7, "", size=22, bold=True, col=AMBER, align="RIGHT", TextCode=f"boardNow({i})",
                **on(INK, AMBER))
        sh.text(bx + bw - 16, ry + 14, "", size=11, col=INKMUTED, align="RIGHT", TextCode=f"boardSoFar({i})",
                **on(INK2, INKMUTED))
        if i < len(rows) - 1:
            sh.rect(bx + 16, ry + rh, bw - 32, 1, fill=INKRULE, line=None)
    # column B, 3: the crew, busy now as a cobalt bar, utilisation since 06:00 beside the name
    cy = by + 74 + rh * len(rows) + 10 + 22
    sh.text(COL_B, cy, "Crew", size=14, bold=True, col=INK)
    sh.rect(COL_B, cy + 24, COL_B_W, 2, fill=INK, line=None)
    for k, lab in enumerate(["Pickers", "Packers", "Receivers", "Putaway"]):
        ry = cy + 34 + 40 * k
        sh.text(COL_B, ry + 4, lab, size=12, col=INK)
        sh.text(COL_B + 104, ry + 6, "", size=10, col=MUTED,
                TextCode=f'String.format("%.0f%% of the day", 100 * utilSoFar({k}))')
        sh.text(COL_B + COL_B_W, ry + 4, "", size=12, bold=True, col=INK, align="RIGHT", TextCode=f"crewText({k})")
        sh.rect(COL_B, ry + 24, COL_B_W, 4, fill=PAPER2, line=None)
        sh.rect(COL_B, ry + 24, COL_B_W, 4, fill=ACCENT, line=None, WidthCode=f"{COL_B_W} * crewBusyNow({k})")
    sh.text(COL_B, cy + 34 + 40 * 4 + 8, "", size=11, col=MUTED, TextCode="inboundText()")
    # column C: one argument per chart, the accent on the series that matters, context in grey
    style = dict(window=STOP_TIME, recurrence=300, area=PAPER3, border=RULE, grid=PAPER2, text=MUTED, legend_text=INK2,
                 label_format="MODEL_DATE_TIME_ONLY")
    charts = [
        ("Orders through the day", "Cumulative, since 06:00.", TOP, 254, "throughput", True,
         [("arrived", "nArrived", INKMUTED), ("picked", "nPicked", INK2), ("shipped", "nShipped", ACCENT)]),
        ("Walk per picked order", "Running mean, metres. Lower is better.", TOP + 270, 250, "walk", False,
         [("walk per order (m)", "walkPerOrder()", ACCENT)]),
        ("Arrival to packed", "Running mean, minutes. Lower is better.", TOP + 536, 236, "fulfil", False,
         [("fulfilment (min)", "liveKpi()[0]", ACCENT)]),
    ]
    for title, sub, y, ch, name, legend, series in charts:
        sh.text(COL_C, y, title, size=14, bold=True, col=INK)
        sh.text(COL_C, y + 21, sub, size=10, col=MUTED)
        sh.rect(COL_C, y + 40, COL_C_W, 2, fill=INK, line=None)
        series = [(t, f"plotValue({e})", c) for t, e, c in series]     # never NaN into a chart
        sh.time_plot(name, COL_C - 14, y + 44, COL_C_W + 14, ch - 44, series, legend=legend, **style)
    # worker dots (on top of the floor map)
    sh.oval(0, 0, 5.5, fill=INKMUTED, line=PAPER3, lw=1.5, name="workerDot", rep=str(MAX_DOTS),
            VisibleCode="workerVisible(index)", XCode="workerXY(index)[0]", YCode="workerXY(index)[1]",
            FillColorCode="workerColor(index)")
    # end of day: the results sheet replaces the figures, the board and the charts (the floor stays visible)
    ex, ey, ew, eh = COL_B, TOP, PAGE_W - 24 - COL_B, FRAME_Y + FRAME_H - TOP
    tw = 640                                     # the table's width; the rest of the sheet stays empty
    sh.rect(ex, ey, ew, eh, fill=PAPER3, line=INK, lw=2, VisibleCode="done")
    sh.text(ex + 32, ey + 28, "End of day", size=24, bold=True, col=INK, VisibleCode="done")
    sh.text(ex + 32, ey + 64, "", size=12, col=MUTED, VisibleCode="done", TextCode="layoutTitle()")
    sh.text(ex + 32, ey + 82, "", size=12, col=MUTED, VisibleCode="done", TextCode="dayText()")
    sh.rect(ex + 32, ey + 112, tw, 2, fill=INK, line=None, VisibleCode="done")
    for i in range(len(END_ROWS)):
        ry = ey + 120 + 38 * i
        sh.text(ex + 32, ry + 11, "", size=13, col=INK2, VisibleCode="done", TextCode=f"endLabel({i})")
        sh.text(ex + 32 + tw, ry + 10, "", size=14, bold=True, col=INK, align="RIGHT", VisibleCode="done",
                TextCode=f"endText({i})")
        if i < len(END_ROWS) - 1:
            sh.rect(ex + 32, ry + 38, tw, 1, fill=RULE, line=None, VisibleCode="done")
    sh.text(ex + 32, ey + 120 + 38 * len(END_ROWS) + 28, "Added to results/runs.csv. To compare layouts, set "
            "Main.layoutFile to another\nlayout and run the same day again.", size=11, col=MUTED, VisibleCode="done")
    # flowchart section
    sh.text(20, Y0 - 52, "Process flowchart", size=16, bold=True, col=INK)
    sh.text(20, Y0 - 30, "The same for every layout. Outbound: arrive, stock check (hold if short), wait for a cart "
            "(wave release), cart tour by a picker, pack, staging until cut-off, ship. Inbound: arrive, receive, "
            "putaway trip, stock up (releases held orders).", size=11, col=MUTED)

    # ------------------------------------------------------------------ experiments
    m.experiments = [
        simulation_xml(m, main),
        pv_xml(m, main, P, "CompareLayouts", "Every design in data/layouts/index.txt x synthetic days 1-10 "
               "(layoutIndex x seed, common random numbers). Results: results/runs.csv.",
               [("layoutIndex", 0, "N_LAYOUTS-1"), ("seed", 1, 10)]),
        pv_xml(m, main, P, "ValidateRealDays", "The as-is layout on the 10 replayed historical days "
               "(data/scenarios/real_index.txt). Results: results/runs.csv.", [("realDay", 1, 10)]),
        pv_xml(m, main, P, "StaffPickers", "Pickers 2..8 x synthetic days 1-10 on Main.layoutFile. Results: results/runs.csv.",
               [("nPickers", 2, 8), ("seed", 1, 10)]),
        pv_xml(m, main, P, "CartSize", "Cart size 0 (single-order picking), 12, 24, 36 units x days 1-10 on "
               "Main.layoutFile. Results: results/runs.csv.", [("cartUnits", 0, 36, 12), ("seed", 1, 10)]),
    ]
    return m


def _time_props():
    return (f'<ModelTimeProperties>\n<StopOption>{cd("Stop at specified time")}</StopOption>\n'
            f'<InitialDate>{cd(str(START_MS))}</InitialDate>\n<InitialTime>{cd("0.0")}</InitialTime>\n'
            f'<FinalDate>{cd(str(START_MS + STOP_TIME * 1000))}</FinalDate>\n<FinalTime>{cd(f"{STOP_TIME:.1f}")}</FinalTime>\n'
            '</ModelTimeProperties>\n')


def _text(m, name, x, y, txt, size, code=None, bold=False):
    return (f'<Text>\n<Id>{m.ids()}</Id>\n<Name>{cd(name)}</Name>\n<X>{x}</X><Y>{y}</Y>\n<Label><X>10</X><Y>0</Y></Label>\n'
            '<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n<ShowLabel>false</ShowLabel>\n'
            '<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<EmbeddedIcon>false</EmbeddedIcon>\n<Z>0</Z>\n<Rotation>0.0</Rotation>\n'
            f'<Color>-12490271</Color>\n<Text>{cd(txt)}</Text>\n' + (f'<TextCode>{cd(code)}</TextCode>\n' if code else '')
            + f'<Font>\n<Name>{UI_FONT}</Name>\n<Size>{size}</Size>\n<Style>{1 if bold else 0}</Style>\n</Font>\n'
            '<Alignment>LEFT</Alignment>\n</Text>\n')


def simulation_xml(m, main):
    return (f'<SimulationExperiment ActiveObjectClassId="{main.id}">\n<Id>{m.ids()}</Id>\n<Name>{cd("Simulation")}</Name>\n'
            f'<CommandLineArguments>{cd("")}</CommandLineArguments>\n<MaximumMemory>1024</MaximumMemory>\n'
            '<RandomNumberGenerationType>fixedSeed</RandomNumberGenerationType>\n<CustomGeneratorCode>new Random()</CustomGeneratorCode>\n'
            '<SeedValue>1</SeedValue>\n<SelectionModeForSimultaneousEvents>LIFO</SelectionModeForSimultaneousEvents>\n'
            f'<VmArgs>{cd("")}</VmArgs>\n<LoadRootFromSnapshot>false</LoadRootFromSnapshot>\n<Presentation>\n'
            + _text(m, "title", 40, 30, "WarehouseSim: one day on one layout. Inputs are the files named in Main's parameters "
                    "(layoutFile, scenarioFile, configFile, skuFile, seed).", 16) +
            '</Presentation>\n<Parameters>\n</Parameters>\n<PresentationProperties>\n<EnableZoomAndPanning>true</EnableZoomAndPanning>\n'
            f'<ExecutionMode>{cd("realTimeScaled")}</ExecutionMode>\n<Title>{cd(NAME + " : Simulation")}</Title>\n'
            '<EnableDeveloperPanel>true</EnableDeveloperPanel>\n<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>\n'
            '<RealTimeScale>60.0</RealTimeScale>\n</PresentationProperties>\n' + _time_props() +
            '<BypassInitialScreen>true</BypassInitialScreen>\n</SimulationExperiment>\n')


def pv_xml(m, main, P, name, desc, ranges):
    """Parameters Variation over integer ranges [(param, from, to[, step])], one replication per combination."""
    n_runs = 1
    vals = ""
    for rg in ranges:
        pname, lo, hi = rg[:3]
        step = rg[3] if len(rg) > 3 else 1
        if isinstance(hi, str):
            hi = eval(hi.replace("N_LAYOUTS", str(N_LAYOUTS)))
        n_runs *= (hi - lo) // step + 1
        vals += (f'<FreeformParamValue>\n<Id>{P[pname]}</Id>\n</FreeformParamValue>\n'
                 f'<RangeVariationParamValue>\n<Id>{P[pname]}</Id>\n<Type>RANGE</Type>\n'
                 f'<From Class="CodeValue">\n<Code>{cd(lo)}</Code>\n</From>\n<To Class="CodeValue">\n<Code>{cd(hi)}</Code>\n</To>\n'
                 f'<Step Class="CodeValue">\n<Code>{cd(step)}</Code>\n</Step>\n</RangeVariationParamValue>\n')
    after = 'runs++;\ntraceln("run " + runs + " of ' + str(n_runs) + ' done");'
    main.shadow.method("Main", f"  void _pv{name}(Main root) {{ int runs = 0;\n{after}\n Object t = \"runs done: \" + runs; }}")
    var = (f'<Variable Class="PlainVariable">\n<Id>{m.ids()}</Id>\n<Name>{cd("runs")}</Name>\n<X>40</X><Y>300</Y>\n'
           '<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>false</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
           '<ShowLabel>true</ShowLabel>\n<Properties SaveInSnapshot="true" Constant="false" AccessType="public" StaticVariable="false">\n'
           f'<Type>{cd("int")}</Type>\n<InitialValue Class="CodeValue">\n<Code>{cd("0")}</Code>\n</InitialValue>\n</Properties>\n</Variable>\n')
    return (f'<ParamVariationExperiment ActiveObjectClassId="{main.id}">\n<Id>{m.ids()}</Id>\n<Name>{cd(name)}</Name>\n'
            f'<Description>{cd(desc)}</Description>\n<CommandLineArguments>{cd("")}</CommandLineArguments>\n'
            '<MaximumMemory>1024</MaximumMemory>\n<RandomNumberGenerationType>fixedSeed</RandomNumberGenerationType>\n'
            f'<CustomGeneratorCode>new Random()</CustomGeneratorCode>\n<AfterSimulationRunCode>{cd(after)}</AfterSimulationRunCode>\n'
            '<SeedValue>1</SeedValue>\n<SelectionModeForSimultaneousEvents>LIFO</SelectionModeForSimultaneousEvents>\n'
            f'<VmArgs>{cd("")}</VmArgs>\n<LoadRootFromSnapshot>false</LoadRootFromSnapshot>\n<Variables>\n{var}</Variables>\n'
            '<Presentation>\n' + _text(m, "title", 40, 30, desc, 14)
            + _text(m, "progress", 40, 70, "?", 16, code='"runs done: " + runs + " of ' + str(n_runs) + '"', bold=True)
            + '</Presentation>\n<AllowParallelEvaluations>false</AllowParallelEvaluations>\n'
            f'<UseFreeformParameters>false</UseFreeformParameters>\n<NumberOfRuns>{n_runs}</NumberOfRuns>\n'
            + vals + _time_props() +
            '<PresentationProperties>\n<EnableZoomAndPanning>true</EnableZoomAndPanning>\n'
            f'<Title>{cd(NAME + " : " + name)}</Title>\n<EnableDeveloperPanel>true</EnableDeveloperPanel>\n'
            '<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>\n</PresentationProperties>\n'
            '<ReplicationsProperties>\n<UseReplication>false</UseReplication>\n<FixedReplicationsNumber>true</FixedReplicationsNumber>\n'
            '<ReplicationPerIteration>1</ReplicationPerIteration>\n<MinimumReplication>2</MinimumReplication>\n'
            '<MaximumReplication>20</MaximumReplication>\n<ConfidenceLevel>LEVEL_95</ConfidenceLevel>\n<ErrorPercent>0.5</ErrorPercent>\n'
            f'<ExpressionForConfidenceComputation>{cd("0")}</ExpressionForConfidenceComputation>\n</ReplicationsProperties>\n'
            '</ParamVariationExperiment>\n')


N_LAYOUTS = None


def write():
    global N_LAYOUTS
    model_dir = ROOT / "model" / NAME
    idx = model_dir / "data" / "layouts" / "index.txt"
    N_LAYOUTS = len([ln for ln in idx.read_text().split() if ln.strip()])
    m = build()
    alp = ROOT / "build" / f"{NAME}.generated.alp"
    alp.parent.mkdir(parents=True, exist_ok=True)
    alp.write_text(m.xml(), encoding="utf-8")
    sdir = ROOT / "build" / "shadow" / PACKAGE
    sdir.mkdir(parents=True, exist_ok=True)
    for old in sdir.glob("*.java"):
        old.unlink()
    for c in m.shadow.classes:
        (sdir / f"{c}.java").write_text(m.shadow.source(c))
    print(f"wrote {alp} ({N_LAYOUTS} layouts in CompareLayouts) and shadow sources in {sdir}")


if __name__ == "__main__":
    write()
