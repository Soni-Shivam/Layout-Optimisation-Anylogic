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
STOP_TIME = 400000                           # experiments stop at Main.finishRun() (= horizon_s); this is a backstop
MAX_DOTS = 80                                # worker dots drawn


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
        ("ox", "double", "20"),
        ("oy", "double", "160"),
        ("nArrived", "int", "0"),
        ("nPicked", "int", "0"),
        ("nPacked", "int", "0"),
        ("nShipped", "int", "0"),
        ("nTours", "int", "0"),
        ("pending", "ArrayList<Order>", "new ArrayList<Order>()"),
        ("done", "boolean", "false"),
    ]:
        main.plain_var(name, jt, init, 1650, next(vy))
    # the generated agent class has this field; the shadow class needs it to compile the drawing code
    main.shadow.field("Main", "public ShapeTopLevelPresentationGroup presentation;")

    fy = iter(range(20, 2000, 22))

    def fn(name, ret, args, body, doc=""):
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
	if (a.picker != null) a.picker.motion = a.plan.motion;
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
traceln(String.format("WarehouseSim done: %s seed %d | shipped %s of %s | fulfil mean %.0f s, p95 %.0f s | on time %.1f%% | pick %.1f m/order | util pick %.2f pack %.2f recv %.2f put %.2f",
	wh.layout.id, seed, Kpi.fmt(s.get("orders_shipped")), Kpi.fmt(s.get("orders_arrived")), (Double) s.get("fulfil_mean_s"),
	(Double) s.get("fulfil_p95_s"), (Double) s.get("on_time_pct"), (Double) s.get("pick_m_per_order"), util[0], util[1], util[2], util[3]));
finishSimulation();
""", "End of the day (horizon_s): writes results/runs.csv (+ the per-order file) and stops the run.")

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
LayoutData L = wh.layout;
px = Math.min(900.0 / L.widthM(), 700.0 / L.heightM());
double cw = L.cellW * px, ch = L.cellH * px;
int k = 0;                                 // insert at the bottom so the worker dots stay on top
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
	ShapeText t = new ShapeText();
	t.setPos(sx(f.x), sy(f.y) - 4);
	t.setText(f.id);
	t.setColor(Color.WHITE);
	t.setFont(new Font("SansSerif", Font.BOLD, 8));
	t.setAlignment(ALIGNMENT_CENTER);
	presentation.insert(k++, t);
}
ShapeText title = new ShapeText();
title.setPos(ox, oy + L.heightM() * px + 6);
title.setText("Layout " + L.id + "\\n" + L.cols + " x " + L.rows + " cells of " + String.format("%.2f x %.2f", L.cellW, L.cellH)
	+ " m, " + L.slotId.length + " slots, slotting " + L.slotting + "\\ngrey = aisle, brown = shelf, green DI = inbound dock, "
	+ "blue DO = outbound dock,\\nyellow = receiving, orange PK = packing, purple = staging, teal H = picker depot");
title.setColor(new Color(69, 90, 100));
title.setFont(new Font("SansSerif", Font.PLAIN, 11));
presentation.insert(k++, title);
""", "Draws the layout read from the JSON file (cells, facility labels).")

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

    fn("workerColor", "Color", [("int", "i")], """
Worker u = workers.get(i);
Color[] busyC = {new Color(229, 57, 53), new Color(255, 111, 0), new Color(253, 216, 53), new Color(30, 136, 229)};
return u.busyNow ? busyC[u.role] : new Color(158, 158, 158);
""")

    fn("statusText", "String", [], """
if (wh == null) return "loading ...";
long t = (long) time();
return String.format("%s   seed %d   day file %s%n"
	+ "clock %02d:%02d:%02d (day ends at %s s)%n"
	+ "orders: arrived %d   held now %d   waiting for a cart %d   picked %d (%d carts)   packed %d   shipped %d   in system %d%n"
	+ "busy: pickers %d/%d   packers %d/%d   receivers %d/%d   putaway %d/%d%n"
	+ "receiving buffer %d / %d lines   staging %d orders   stock on hand %d units",
	wh.layout.id, seed, scenarioPath, t / 3600, (t / 60) % 60, t % 60, Kpi.fmt(wh.cfg.horizon),
	nArrived, (int) kpi.held.value(), pending.size(), nPicked, nTours, nPacked, nShipped, (int) kpi.inSystem.value(),
	pickerPool.busy(), staff[0], packerPool.busy(), staff[1], receiverPool.busy(), staff[2], putawayPool.busy(), staff[3],
	(int) kpi.recvBuffer.value(), wh.recvBufferCapacity(), (int) kpi.staging.value(), wh.inv.totalOnHand());
""")

    # ------------------------------------------------------------------ flowchart
    X0, Y0 = 40, 900
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
    sh = Shapes(main)
    sh.text(20, 12, "Warehouse simulation - model generated at start-up from the layout JSON", size=20, bold=True, col="#1A237E")
    sh.text(20, 44, "", size=12, col="#263238", name="status", TextCode="statusText()")
    sh.oval(0, 0, 4, fill="#9E9E9E", line="#212121", name="workerDot", rep=str(MAX_DOTS),
            VisibleCode="workerVisible(index)", XCode="workerXY(index)[0]", YCode="workerXY(index)[1]",
            FillColorCode="workerColor(index)")
    sh.text(960, 160, "Worker dots: red = picker, orange = packer, yellow = receiver, blue = putaway (grey = idle).",
            size=11, col="#455A64")
    sh.time_plot("levels", 960, 190, 460, 300,
                 [("orders in system", "kpi == null ? 0 : kpi.inSystem.value()", "#1565C0"),
                  ("held (no stock)", "kpi == null ? 0 : kpi.held.value()", "#C62828"),
                  ("in staging", "kpi == null ? 0 : kpi.staging.value()", "#6A1B9A"),
                  ("receiving buffer", "kpi == null ? 0 : kpi.recvBuffer.value()", "#F9A825")],
                 window=60000, recurrence=300)
    sh.text(20, Y0 - 50, "Process flowchart (generic: the same for every layout)", size=16, bold=True, col="#37474F")
    sh.text(20, Y0 - 28, "Outbound: arrive, stock check (hold if short), wait for a cart (wave release), cart tour by a picker, "
            "pack, staging until cut-off, ship.   Inbound: arrive, receive, putaway trip, stock up (releases held orders).",
            size=11, col="#546E7A")

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
            f'<InitialDate>{cd("1759708800000")}</InitialDate>\n<InitialTime>{cd("0.0")}</InitialTime>\n'
            f'<FinalDate>{cd(str(1759708800000 + STOP_TIME * 1000))}</FinalDate>\n<FinalTime>{cd(f"{STOP_TIME:.1f}")}</FinalTime>\n'
            '</ModelTimeProperties>\n')


def _text(m, name, x, y, txt, size, code=None, bold=False):
    return (f'<Text>\n<Id>{m.ids()}</Id>\n<Name>{cd(name)}</Name>\n<X>{x}</X><Y>{y}</Y>\n<Label><X>10</X><Y>0</Y></Label>\n'
            '<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n<ShowLabel>false</ShowLabel>\n'
            '<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<EmbeddedIcon>false</EmbeddedIcon>\n<Z>0</Z>\n<Rotation>0.0</Rotation>\n'
            f'<Color>-12490271</Color>\n<Text>{cd(txt)}</Text>\n' + (f'<TextCode>{cd(code)}</TextCode>\n' if code else '')
            + f'<Font>\n<Name>SansSerif</Name>\n<Size>{size}</Size>\n<Style>{1 if bold else 0}</Style>\n</Font>\n'
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
            '<RealTimeScale>120.0</RealTimeScale>\n</PresentationProperties>\n' + _time_props() +
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
