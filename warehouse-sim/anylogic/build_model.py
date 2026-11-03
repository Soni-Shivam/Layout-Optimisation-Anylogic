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

# ---- screen design: one typeface, one accent colour, status colours only where a KPI is good / bad
UI_FONT = "Roboto"       # nominal; Main.pickFont() swaps in the first installed of FONTS at start-up
FONTS = ["Roboto", "Segoe UI", "Lato", "Open Sans", "Noto Sans", "Helvetica Neue", "Arial"]
PAGE, CARD, LINE, SHADOW = "#F3F5F8", "#FFFFFF", "#E2E6EC", "#E6E9EE"
INK, MUTED, HEADER = "#1F2937", "#6B7280", "#1E293B"
ACCENT, GOOD, WARN, BAD = "#2563EB", "#16A34A", "#D97706", "#DC2626"
PAGE_W = 1410
TILE_Y, TILE_W, TILE_H, TILE_GAP = 68, 128, 84, 10
FLOOR_X, FLOOR_Y = 20, 164                   # warehouse floor card (sized at start-up to the layout)
FLOOR_W, FLOOR_H = 890, 640                  # largest picture of the layout; the card ends above the flowchart
CHART_X, CHART_W = 950, 440
FLOW_Y0 = 1000                               # the process flowchart starts here
COL = dict(PAGE=PAGE, CARD=CARD, LINE=LINE, SHADOW=SHADOW, INK=INK, MUTED=MUTED, HEADER=HEADER, ACCENT=ACCENT,
           GOOD=GOOD, WARN=WARN, BAD=BAD, IDLE="#9E9E9E")
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
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


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
        detail = (f"picker depot at ({d['depot'][0]:g}, {d['depot'][1]:g}) m  ·  "
                  + (f"{len(ca)} extra cross aisle{'s' if len(ca) > 1 else ''} at x = {', '.join(f'{x:g}' for x in ca)} m"
                     if ca else "no extra cross aisles")
                  + f"  ·  {storage.get(d['slotting'], d['slotting'])}  ·  {d['n_pack']} packing stations")
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
        ("ox", "double", str(FLOOR_X + 14)),
        ("oy", "double", str(FLOOR_Y + 52)),
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
        body = re.sub(r"\bC_([A-Z]+)\b", lambda mo: jcolor(COL[mo.group(1)]), body)     # palette colours
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
	case "#": return new Color(55, 71, 79);
	case "A": return new Color(236, 239, 241);
	case "S": return new Color(161, 136, 127);
	case "DI": return new Color(46, 125, 50);
	case "DO": return new Color(21, 101, 192);
	case "R": return new Color(255, 224, 130);
	case "PK": return new Color(255, 152, 0);
	case "G": return new Color(179, 157, 219);
	case "H": return new Color(0, 137, 123);
	default: return Color.WHITE;
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
px = Math.min(FLOOR_W / L.widthM(), FLOOR_H / L.heightM());
double W = L.widthM() * px, H = L.heightM() * px;
double cw = L.cellW * px, ch = L.cellH * px;
int k = 0;                                 // insert at the bottom so the dashboard and the worker dots stay on top
// page background and the floor card (the card fits the layout picture + its key)
presentation.insert(k++, box(0, 0, PAGE_W, PAGE_H, C_PAGE, null, 0));
presentation.insert(k++, box(FLOOR_X, FLOOR_Y + 2, W + 28, H + 124, C_SHADOW, null, 10));
presentation.insert(k++, box(FLOOR_X, FLOOR_Y, W + 28, H + 124, C_CARD, C_LINE, 10));
presentation.insert(k++, label(ox, FLOOR_Y + 10, "Warehouse floor", C_INK, 14, true));
presentation.insert(k++, label(ox, FLOOR_Y + 30, String.format("%d x %d cells of %.2f x %.2f m  \\u00b7  %d storage slots  \\u00b7  layout %s",
	L.cols, L.rows, L.cellW, L.cellH, L.slotId.length, L.id), C_MUTED, 10, false));
for (int r = 0; r < L.rows; r++) {
	for (int q = 0; q < L.cols; q++) {
		ShapeRectangle s = new ShapeRectangle();
		s.setPos(sx(L.originX + q * L.cellW), sy(L.originY + (r + 1) * L.cellH));
		s.setSize(cw, ch);
		s.setFillColor(cellColor(L.grid[r][q]));
		s.setLineColor(new Color(255, 255, 255));
		s.setLineWidth(0.5);
		presentation.insert(k++, s);
	}
}
for (LayoutData.Facility f : L.facilities) {
	if (f.type.equals("R") || f.type.equals("G")) continue;
	ShapeText t = label(sx(f.x), sy(f.y) - 5, f.id, Color.WHITE, 8, true);
	t.setAlignment(ALIGNMENT_CENTER);
	presentation.insert(k++, t);
}
// key: what the cell colours and the worker dots mean
String[] cell = {"A", "S", "#", "DI", "R", "PK", "G", "DO", "H"};
String[] cellName = {"aisle", "shelf", "wall", "inbound dock", "receiving", "packing station", "staging", "outbound dock", "picker depot"};
double y = oy + H + 14, x = ox;
presentation.insert(k++, label(x, y - 1, "Floor", C_MUTED, 10, true));
x += 48;
for (int i = 0; i < cell.length; i++) {
	presentation.insert(k++, box(x, y, 11, 11, cellColor(cell[i]), new Color(0xCFD6DE), 2));
	presentation.insert(k++, label(x + 16, y - 1, cellName[i], C_INK, 10, false));
	x += 16 + 5.6 * cellName[i].length() + 18;
}
y += 22; x = ox;
presentation.insert(k++, label(x, y - 1, "Workers", C_MUTED, 10, true));
x += 48;
String[] who = {"picker", "packer", "receiver", "putaway", "idle (any role)"};
for (int i = 0; i < who.length; i++) {
	ShapeOval o = new ShapeOval();
	o.setPos(x + 5.5, y + 5.5);
	o.setRadius(5.5);
	o.setFillColor(i < 4 ? roleColor(i) : C_IDLE);
	o.setLineColor(Color.WHITE);
	o.setLineWidth(1.5);
	presentation.insert(k++, o);
	presentation.insert(k++, label(x + 16, y - 1, who[i], C_INK, 10, false));
	x += 16 + 5.6 * who[i].length() + 18;
}
""".replace("FLOOR_W", f"{FLOOR_W:.1f}").replace("FLOOR_H", f"{FLOOR_H:.1f}").replace("FLOOR_X", str(FLOOR_X))
       .replace("FLOOR_Y", str(FLOOR_Y)).replace("PAGE_W", str(PAGE_W)).replace("PAGE_H", str(FLOW_Y0 - 70)),
       "Draws the layout read from the JSON file (page background, floor card, cells, facility labels, colour key).")

    fn("box", "ShapeRoundedRectangle", [("double", "x"), ("double", "y"), ("double", "w"), ("double", "h"), ("Color", "fill"),
                                        ("Color", "line"), ("double", "radius")], """
ShapeRoundedRectangle s = new ShapeRoundedRectangle();
s.setPos(x, y);
s.setSize(w, h);
s.setRadius(radius);
s.setFillColor(fill);
s.setLineColor(line);
s.setLineWidth(line == null ? 0 : 1);
return s;
""", "A filled (rounded) rectangle for the runtime-drawn picture; line null = no outline.")

    fn("label", "ShapeText", [("double", "x"), ("double", "y"), ("String", "text"), ("Color", "c"), ("int", "size"),
                              ("boolean", "bold")], """
ShapeText t = new ShapeText();
t.setPos(x, y);
t.setText(text);
t.setColor(c);
t.setFont(new Font(uiFont, bold ? Font.BOLD : Font.PLAIN, size));
return t;
""", "A text in the dashboard typeface.")

    fn("pickFont", None, [], """
// one typeface for the whole screen: the first of these that is installed (Linux and Windows have different ones)
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
       "Chooses the dashboard typeface and applies it to every text drawn by the model.")

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
double[] p = u.motion != null ? u.motion.at(time()) : homeXY(u);
double off = ((u.k % 3) - 1) * 0.35 * wh.layout.cellW;     // spread workers that share a spot
return new double[]{sx(p[0] + off), sy(p[1] + off)};
""")

    fn("workerVisible", "boolean", [("int", "i")], "return wh != null && i < workers.size();")

    fn("roleColor", "Color", [("int", "role")], """
switch (role) {
	case 0: return new Color(229, 57, 53);     // picker
	case 1: return new Color(255, 111, 0);     // packer
	case 2: return new Color(253, 216, 53);    // receiver
	default: return new Color(30, 136, 229);   // putaway
}
""")

    fn("workerColor", "Color", [("int", "i")], """
Worker u = workers.get(i);
return u.busyNow ? roleColor(u.role) : C_IDLE;
""")

    # ---- dashboard: header, KPI tiles, end-of-day panel (values from the live model state)
    names = layout_names()
    fn("layoutTitle", "String", [], "if (wh == null) return \"loading ...\";\nswitch (wh.layout.id) {\n"
       + "".join(f"\tcase {jstr(i)}: return {jstr(t)};\n" for i, (t, _) in names.items())
       + "\tdefault: return \"Layout \" + wh.layout.id;\n}", "The layout in plain words (from data/config/designs.json).")
    fn("layoutDetail", "String", [], "if (wh == null) return \"\";\nswitch (wh.layout.id) {\n"
       + "".join(f"\tcase {jstr(i)}: return {jstr(d)};\n" for i, (_, d) in names.items())
       + "\tdefault: return \"slotting \" + wh.layout.slotting;\n}")

    fn("clockText", "String", [], """
long t = (long) time();
return String.format("%02d:%02d", (6 + t / 3600) % 24, (t / 60) % 60);
""", "Time of day (model time 0 = 06:00).")

    fn("dayText", "String", [], """
if (wh == null) return "";
String day = new java.io.File(scenarioPath).getName().replace(".csv", "").replace("_", " ");
String mode = !done && time() > 0 && !getEngine().getRealTimeMode() ? "fast-forwarding the quiet morning  \\u00b7  " : "";
return mode + day + "  \\u00b7  seed " + seed + "  \\u00b7  06:00 to " + clockOf(wh.cfg.horizon);
""")

    fn("clockOf", "String", [("double", "t")], """
long s = (long) t;
return String.format("%02d:%02d", (6 + s / 3600) % 24, (s / 60) % 60);
""")

    fn("dayProgress", "double", [], "return wh == null ? 0 : Math.max(0, Math.min(1, time() / wh.cfg.horizon));")

    fn("liveKpi", "double[]", [], """
// {mean fulfilment so far (min), on time so far (%), orders due so far, orders ever held}; computed once per time
if (kpi == null) return new double[]{Double.NaN, Double.NaN, 0, 0};
double t = time();
if (liveV != null && t == liveT) return liveV;
double sum = 0;
int n = 0, due = 0, ok = 0, everHeld = 0;
for (int i = 0; i < kpi.oArr.length; i++) {
	if (Double.isNaN(kpi.oArr[i])) continue;
	if (kpi.oHeld[i]) everHeld++;
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
liveV = new double[]{n > 0 ? sum / n / 60 : Double.NaN, due > 0 ? 100.0 * ok / due : Double.NaN, due, everHeld};
return liveV;
""", "Running KPIs for the tiles and charts.")

    fn("walkPerOrder", "double", [], "return kpi == null || kpi.tourOrders == 0 ? Double.NaN : kpi.tourM / kpi.tourOrders;",
       "Picking walk per picked order so far (m) = the orders' share of their carts' tours.")
    fn("utilSoFar", "double", [("int", "k")], "return time() > 0 && staff[k] > 0 ? busy[k].mean(time()) / staff[k] : 0;",
       "Utilisation of role k since 06:00 (0 pickers, 1 packers, 2 receivers, 3 putaway).")
    fn("orZero", "double", [("double", "x")], "return Double.isNaN(x) ? 0 : x;")

    fn("tileValue", "String", [("int", "i")], """
if (wh == null) return "\\u2013";
double[] v = liveKpi();
switch (i) {
	case 0: return String.valueOf(nArrived);
	case 1: return String.valueOf(nShipped);
	case 2: return String.valueOf(pending.size());
	case 3: return String.valueOf((int) kpi.held.value());
	case 4: return String.valueOf(nTours);
	case 5: return Double.isNaN(walkPerOrder()) ? "\\u2013" : String.format("%.0f m", walkPerOrder());
	case 6: return Double.isNaN(v[0]) ? "\\u2013" : String.format("%.0f min", v[0]);
	case 7: return Double.isNaN(v[1]) ? "\\u2013" : String.format("%.0f%%", v[1]);
	case 8: return String.format("%.0f%%", 100 * utilSoFar(0));
	default: return String.format("%.0f%%", 100 * utilSoFar(1));
}
""", "Big number of KPI tile i.")

    fn("tileSub", "String", [("int", "i")], """
if (wh == null) return "";
double[] v = liveKpi();
switch (i) {
	case 0: return "of " + wh.scenario.orders.size() + " in the day";
	case 1: return nPacked + " packed, " + (int) kpi.staging.value() + " staged";
	case 2: return pickerPool.busy() + " carts out now";
	case 3: return (int) v[3] + " held at some point";
	case 4: return kpi.tours > 0 ? String.format("%.1f orders per cart", (double) kpi.tourOrders / kpi.tours) : "no cart back yet";
	case 5: return String.format("%.1f km in total", kpi.tourM / 1000);
	case 6: return "arrival to packed";
	case 7: return (int) v[2] > 0 ? "of " + (int) v[2] + " due so far" : "no cut-off yet";
	case 8: return "busy now " + pickerPool.busy() + " of " + staff[0];
	default: return "busy now " + packerPool.busy() + " of " + staff[1];
}
""")

    fn("tileColor", "Color", [("int", "i")], """
if (wh == null) return C_INK;
if (i == 3) return kpi.held.value() > 0 ? C_BAD : C_INK;
if (i == 7) {
	double p = liveKpi()[1];
	return Double.isNaN(p) ? C_INK : p >= 95 ? C_GOOD : p >= 80 ? C_WARN : C_BAD;
}
return C_INK;
""", "Status colour of a tile's number: only held orders and on-time % change colour.")

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
    # static dashboard (the floor card, the layout picture and its key are drawn at start-up by drawLayout(), under these)
    sh = Shapes(main, font=UI_FONT)
    # header bar: title, layout in plain words, clock, day progress
    sh.rect(0, 0, PAGE_W, 56, fill=HEADER, line=None, name="headerBar")
    sh.text(24, 8, "Footwear warehouse  ·  one-day simulation", size=19, bold=True, col="#FFFFFF")
    sh.text(24, 34, "", size=12, col="#CBD5E1", name="layoutName", TextCode='layoutTitle() + "     " + layoutDetail()')
    sh.text(PAGE_W - 24, 4, "", size=24, bold=True, col="#FFFFFF", align="RIGHT", name="clock", TextCode="clockText()")
    sh.text(PAGE_W - 24, 36, "", size=10, col="#94A3B8", align="RIGHT", name="dayInfo", TextCode="dayText()")
    sh.rect(0, 53, PAGE_W, 3, fill="#334155", line=None, name="dayTrack")
    sh.rect(0, 53, PAGE_W, 3, fill=ACCENT, line=None, name="dayBar", WidthCode=f"{PAGE_W} * dayProgress()")
    # KPI tiles
    tiles = ["Orders arrived", "Orders shipped", "Waiting for a cart", "Held, no stock", "Carts done",
             "Walk per order", "Avg fulfilment", "On time so far", "Pickers busy", "Packers busy"]
    for i, lab in enumerate(tiles):
        x = FLOOR_X + i * (TILE_W + TILE_GAP)
        sh.rrect(x, TILE_Y + 2, TILE_W, TILE_H, fill=SHADOW, radius=8)
        sh.rrect(x, TILE_Y, TILE_W, TILE_H, fill=CARD, line=LINE, radius=8)
        sh.text(x + 12, TILE_Y + 9, lab, size=11, col=MUTED)
        sh.text(x + 12, TILE_Y + 25, "", size=22, bold=True, col=INK, name=f"tileValue{i}",
                TextCode=f"tileValue({i})", ColorCode=f"tileColor({i})")
        if i >= 8:          # utilisation since 06:00 as a bar
            sh.rect(x + 12, TILE_Y + 56, TILE_W - 24, 5, fill="#E5E7EB", line=None)
            sh.rect(x + 12, TILE_Y + 56, TILE_W - 24, 5, fill=ACCENT, line=None, name=f"tileBar{i}",
                    WidthCode=f"{TILE_W - 24} * Math.min(1, utilSoFar({i - 8}))")
            sh.text(x + 12, TILE_Y + 65, "", size=10, col=MUTED, TextCode=f"tileSub({i})")
        else:
            sh.text(x + 12, TILE_Y + 60, "", size=10, col=MUTED, TextCode=f"tileSub({i})")
    # charts for comparing layouts (time axis = clock time)
    style = dict(window=STOP_TIME, recurrence=300, area=CARD, border=LINE, grid="#EEF1F4", text=MUTED, legend_text=INK,
                 label_format="MODEL_DATE_TIME_ONLY")
    charts = [
        ("Orders through the day", "cumulative count since 06:00", 164, 246, "throughput",
         [("arrived", "nArrived", "#94A3B8"), ("picked", "nPicked", ACCENT), ("shipped", "nShipped", GOOD)]),
        ("Work in progress", "orders / receipt lines waiting at each stage", 420, 246, "levels",
         [("orders in system", "kpi == null ? 0 : kpi.inSystem.value()", ACCENT),
          ("held (no stock)", "kpi == null ? 0 : kpi.held.value()", BAD),
          ("in staging", "kpi == null ? 0 : kpi.staging.value()", "#7C3AED"),
          ("receiving buffer", "kpi == null ? 0 : kpi.recvBuffer.value()", WARN)]),
        ("Picking efficiency", "running averages: lower is better", 676, 244, "efficiency",
         [("walk per order (m)", "orZero(walkPerOrder())", ACCENT),
          ("fulfilment, arrival to packed (min)", "orZero(liveKpi()[0])", "#0D9488")]),
    ]
    for title, sub, cy, chh, name, series in charts:
        sh.rrect(CHART_X, cy + 2, CHART_W, chh, fill=SHADOW, radius=10)
        sh.rrect(CHART_X, cy, CHART_W, chh, fill=CARD, line=LINE, radius=10)
        sh.text(CHART_X + 14, cy + 10, title, size=14, bold=True, col=INK)
        sh.text(CHART_X + 14, cy + 30, sub, size=10, col=MUTED)
        sh.time_plot(name, CHART_X + 4, cy + 44, CHART_W - 8, chh - 48, series, **style)
    # worker dots (on top of the floor picture)
    sh.oval(0, 0, 5.5, fill="#9E9E9E", line="#FFFFFF", lw=1.5, name="workerDot", rep=str(MAX_DOTS),
            VisibleCode="workerVisible(index)", XCode="workerXY(index)[0]", YCode="workerXY(index)[1]",
            FillColorCode="workerColor(index)")
    # end-of-day results panel, over the floor once the day is done
    ex, ey, ew = FLOOR_X + 150, FLOOR_Y + 72, 600
    eh = 84 + 30 * len(END_ROWS) + 40
    sh.rrect(ex - 2, ey + 4, ew + 4, eh, fill="#CBD2DA", radius=12, VisibleCode="done")
    sh.rrect(ex, ey, ew, eh, fill=CARD, line=LINE, radius=12, VisibleCode="done")
    sh.rect(ex, ey + 12, 4, 40, fill=ACCENT, line=None, VisibleCode="done")
    sh.text(ex + 22, ey + 14, "End of day results", size=18, bold=True, col=INK, VisibleCode="done")
    sh.text(ex + 22, ey + 40, "", size=12, col=MUTED, VisibleCode="done",
            TextCode='layoutTitle() + "  ·  " + new java.io.File(scenarioPath).getName() + "  ·  seed " + seed')
    for i in range(len(END_ROWS)):
        ry = ey + 74 + 30 * i
        if i % 2 == 0:
            sh.rect(ex + 12, ry, ew - 24, 30, fill="#F6F8FA", line=None, VisibleCode="done")
        sh.text(ex + 24, ry + 7, "", size=12, col=INK, VisibleCode="done", TextCode=f"endLabel({i})")
        sh.text(ex + ew - 24, ry + 6, "", size=13, bold=True, col=INK, align="RIGHT", VisibleCode="done",
                TextCode=f"endText({i})")
    sh.text(ex + 24, ey + eh - 30, "Appended to results/runs.csv.  To compare, set Main.layoutFile to another layout "
            "and run the same day again.", size=10, col=MUTED, VisibleCode="done")
    # flowchart section
    sh.text(20, Y0 - 52, "Process flowchart", size=16, bold=True, col=INK)
    sh.text(20, Y0 - 30, "The same for every layout.  Outbound: arrive, stock check (hold if short), wait for a cart "
            "(wave release), cart tour by a picker, pack, staging until cut-off, ship.   Inbound: arrive, receive, "
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
