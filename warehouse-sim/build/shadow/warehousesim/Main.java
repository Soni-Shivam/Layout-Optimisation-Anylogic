package warehousesim;
import java.io.Serializable;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Currency;
import java.util.Date;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Hashtable;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.Set;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.Stack;
import java.util.Timer;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.Vector;
import java.awt.Color;
import java.awt.Font;
import com.anylogic.engine.connectivity.ResultSet;
import com.anylogic.engine.connectivity.Statement;
import com.anylogic.engine.elements.*;
import com.anylogic.engine.markup.Network;
import com.anylogic.engine.Position;
import com.anylogic.engine.markup.PedFlowStatistics;
import com.anylogic.engine.markup.DensityMap;
import static java.lang.Math.*;
import static com.anylogic.engine.UtilitiesArray.*;
import static com.anylogic.engine.UtilitiesCollection.*;
import static com.anylogic.engine.presentation.UtilitiesColor.*;
import static com.anylogic.engine.HyperArray.*;
import com.anylogic.engine.*;
import com.anylogic.engine.analysis.*;
import com.anylogic.engine.connectivity.*;
import com.anylogic.engine.database.*;
import com.anylogic.engine.gis.*;
import com.anylogic.engine.markup.*;
import com.anylogic.engine.routing.*;
import com.anylogic.engine.presentation.*;
import com.anylogic.engine.gui.*;
import com.anylogic.libraries.processmodeling.*;

@SuppressWarnings("all")
public class Main extends Agent {
  public String layoutFile = "data/layouts/D40.3_63.1-P3-Xnone-asis.json";
  public int layoutIndex = -1;
  public String scenarioFile = "data/scenarios/day_{seed}.csv";
  public int realDay = 0;
  public String skuFile = "data/skus.csv";
  public String configFile = "data/config/run_config.json";
  public int seed = 1;
  public int nPickers = -1;
  public int nPackers = -1;
  public int nReceivers = -1;
  public int nPutaway = -1;
  public int cartUnits = -1;
  public boolean writeOrders = true;
  public boolean skipQuietStart = true;
  public String resultsDir = "results";
  public Warehouse wh = null;
  public Kpi kpi = null;
  public int[] staff = new int[4];
  public Stats.TimeLevel[] busy = new Stats.TimeLevel[]{ new Stats.TimeLevel(), new Stats.TimeLevel(), new Stats.TimeLevel(), new Stats.TimeLevel() };
  public ArrayList<Worker> workers = new ArrayList<Worker>();
  public int[] roleCount = new int[4];
  public String layoutPath = "";
  public String scenarioPath = "";
  public double px = 10;
  public double ox = 32;
  public double oy = 176;
  public int nArrived = 0;
  public int nPicked = 0;
  public int nPacked = 0;
  public int nShipped = 0;
  public int nTours = 0;
  public double animScale = 60;
  public ArrayList<Order> pending = new ArrayList<Order>();
  public boolean done = false;
  public String uiFont = "SansSerif";
  public double liveT = -1;
  public double[] liveV = null;
  public Map<String, Object> endS = null;
  public ShapeTopLevelPresentationGroup presentation;
  public com.anylogic.libraries.processmodeling.Enter<Order> orderIn;
  public com.anylogic.libraries.processmodeling.Delay<Order> orderArrive;
  public com.anylogic.libraries.processmodeling.SelectOutput<Order> stockCheck;
  public com.anylogic.libraries.processmodeling.Wait<Order> holdWait;
  public com.anylogic.libraries.processmodeling.Wait<Order> pickPool;
  public com.anylogic.libraries.processmodeling.Service<Order> pack;
  public com.anylogic.libraries.processmodeling.Delay<Order> staging;
  public com.anylogic.libraries.processmodeling.Sink<Order> shipped;
  public com.anylogic.libraries.processmodeling.Enter<PickTour> tourIn;
  public com.anylogic.libraries.processmodeling.Seize<PickTour> tourSeize;
  public com.anylogic.libraries.processmodeling.Delay<PickTour> tourWalk;
  public com.anylogic.libraries.processmodeling.Release<PickTour> tourRelease;
  public com.anylogic.libraries.processmodeling.Sink<PickTour> tourDone;
  public com.anylogic.libraries.processmodeling.Enter<Receipt> receiptIn;
  public com.anylogic.libraries.processmodeling.Delay<Receipt> receiptArrive;
  public com.anylogic.libraries.processmodeling.Service<Receipt> receive;
  public com.anylogic.libraries.processmodeling.Seize<Receipt> putSeize;
  public com.anylogic.libraries.processmodeling.Delay<Receipt> putWalk;
  public com.anylogic.libraries.processmodeling.Release<Receipt> putRelease;
  public com.anylogic.libraries.processmodeling.Sink<Receipt> stored;
  public com.anylogic.libraries.processmodeling.Enter<DayClock> dayClockIn;
  public com.anylogic.libraries.processmodeling.Delay<DayClock> endOfDay;
  public com.anylogic.libraries.processmodeling.Sink<DayClock> dayEnd;
  public com.anylogic.libraries.processmodeling.Enter<DayClock> wakeIn;
  public com.anylogic.libraries.processmodeling.Delay<DayClock> wakeUp;
  public com.anylogic.libraries.processmodeling.Sink<DayClock> wakeOut;
  public com.anylogic.libraries.processmodeling.Enter<Ticker> tickIn;
  public com.anylogic.libraries.processmodeling.Delay<Ticker> tick;
  public com.anylogic.libraries.processmodeling.Sink<Ticker> tickOut;
  public com.anylogic.libraries.processmodeling.ResourcePool<Worker> pickerPool;
  public com.anylogic.libraries.processmodeling.ResourcePool<Worker> packerPool;
  public com.anylogic.libraries.processmodeling.ResourcePool<Worker> receiverPool;
  public com.anylogic.libraries.processmodeling.ResourcePool<Worker> putawayPool;
  void setup() {
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
  }
  void registerWorker(Worker u, int role) {
u.role = role;
u.k = roleCount[role]++;
workers.add(u);
  }
  boolean admit(Order a) {
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
  }
  void retryHeld() {
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
  }
  void dispatch() {
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
  }
  double beginTour(PickTour a) {
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
  }
  void endTour(PickTour a) {
for (Order o : a.orders) {
	nPicked++;
	wh.inv.consume(o.spec);
	kpi.pickEnded(o.spec, time(), a.plan);
}
kpi.tourEnded(a.plan);
nTours++;
if (a.picker != null) a.picker.motion = null;
for (Order o : a.orders) pickPool.free(o);      // the picked orders go on to packing
  }
  double stageTime(Order a) {
if (Double.isNaN(kpi.oPacked[a.spec.index])) {     // once per order
	nPacked++;
	kpi.orderPacked(a.spec, time());
}
double c = wh.cfg.nextCutoff(time());
return c < Double.POSITIVE_INFINITY ? c - time() : 10 * 54060;
  }
  void orderShipped(Order a) {
nShipped++;
kpi.orderShipped(a.spec, time());
  }
  double beginPutaway(Receipt a) {
if (a.put == null) {
	kpi.putawayStarted(a.spec, time());
	a.put = wh.planPutaway(a.spec, time());
	if (a.worker == null) a.worker = (Worker) a.resourceUnitOfPool(putawayPool);
	if (a.worker != null) a.worker.motion = a.put.motion;
}
return a.put.duration;
  }
  void endPutaway(Receipt a) {
wh.inv.receive(a.spec.sku, a.spec.qty);
kpi.putawayEnded(a.spec, time(), a.put);
if (a.worker != null) a.worker.motion = null;
retryHeld();
  }
  void finishRun() {
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
for (int i = 0; i < 10; i++) tb.append(String.format("%n| %-38s %25s |", endLabel(i), endText(i)));
tb.append(String.format("%n")).append(rule).append(String.format("%n  appended to %s/runs.csv", resultsDir));
traceln(tb.toString());
traceln(String.format("WarehouseSim done: %s seed %d | shipped %s of %s | fulfil mean %.0f s, p95 %.0f s | on time %.1f%% | pick %.1f m/order | util pick %.2f pack %.2f recv %.2f put %.2f",
	wh.layout.id, seed, Kpi.fmt(s.get("orders_shipped")), Kpi.fmt(s.get("orders_arrived")), (Double) s.get("fulfil_mean_s"),
	(Double) s.get("fulfil_p95_s"), (Double) s.get("on_time_pct"), (Double) s.get("pick_m_per_order"), util[0], util[1], util[2], util[3]));
finishSimulation();
  }
  Color cellColor(String t) {
switch (t) {
	case "#": return new Color(0x0A0D13);                     // wall
	case "A": return new Color(0xFBFEFF);                  // aisle
	case "S": return new Color(0xA7ADB6);       // shelf
	case "DI": return new Color(0x282B32);                   // inbound dock
	case "DO": return new Color(0x282B32);                   // outbound dock
	case "R": return new Color(0xF6DC97);       // receiving
	case "PK": return new Color(0xF4B522);                  // packing station
	case "G": return new Color(0xC3CFF3);       // staging
	case "H": return new Color(0x2055E1);                  // picker depot
	default: return new Color(0xFBFEFF);
}
  }
  double sx(double x) {
return ox + (x - wh.layout.originX) * px;
  }
  double sy(double y) {
return oy + (wh.layout.originY + wh.layout.heightM() - y) * px;
  }
  void drawLayout() {
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
// the floor map fills its column: the frame is 684.0 tall, the key takes 150.0 on its right
px = Math.min((476.0 - 16 - 18 - 150.0) / L.widthM(), (684.0 - 16) / L.heightM());
double W = L.widthM() * px, H = L.heightM() * px;
double cw = L.cellW * px, ch = L.cellH * px;
int k = 0;                                 // insert at the bottom so the dashboard and the worker dots stay on top
presentation.insert(k++, box(0, 0, 1410, 880, new Color(0xEDF0F4), null, 0));
presentation.insert(k++, box(24, 168, W + 16, H + 16, new Color(0xFBFEFF), new Color(0x0A0D13), 2));
for (int r = 0; r < L.rows; r++) {
	for (int q = 0; q < L.cols; q++) {
		ShapeRectangle s = new ShapeRectangle();
		s.setPos(sx(L.originX + q * L.cellW), sy(L.originY + (r + 1) * L.cellH));
		s.setSize(cw, ch);
		s.setFillColor(cellColor(L.grid[r][q]));
		s.setLineColor(new Color(0xFBFEFF));
		s.setLineWidth(0.5);
		presentation.insert(k++, s);
	}
}
for (LayoutData.Facility f : L.facilities) {
	if (f.type.equals("R") || f.type.equals("G")) continue;
	boolean dark = f.type.equals("DI") || f.type.equals("DO") || f.type.equals("H");
	ShapeText t = label(sx(f.x), sy(f.y) - 5, f.id, dark ? new Color(0xFBFEFF) : new Color(0x0A0D13), 8, true);
	t.setAlignment(ALIGNMENT_CENTER);
	presentation.insert(k++, t);
}
// key, right of the map: what the cell colours and the worker dots mean
String[] cell = {"A", "S", "#", "R", "PK", "G", "DI", "H"};
String[] cellName = {"aisle", "shelf", "wall", "receiving", "packing station", "staging", "dock", "picker depot"};
double x = 24 + W + 16 + 18, y = 168;
presentation.insert(k++, label(x, y, "Floor", new Color(0x0A0D13), 12, true));
y += 24;
for (int i = 0; i < cell.length; i++) {
	presentation.insert(k++, box(x, y + 1, 12, 12, cellColor(cell[i]), new Color(0x0A0D13), 1));
	presentation.insert(k++, label(x + 20, y, cellName[i], new Color(0x282B32), 11, false));
	y += 20;
}
y += 16;
presentation.insert(k++, label(x, y, "Workers", new Color(0x0A0D13), 12, true));
y += 24;
String[] who = {"picker", "packer", "receiver", "putaway", "idle"};
for (int i = 0; i < who.length; i++) {
	ShapeOval o = new ShapeOval();
	o.setPos(x + 6, y + 7);
	o.setRadius(5.5);
	o.setFillColor(i < 4 ? roleColor(i) : new Color(0x9A9FA6));
	o.setLineColor(new Color(0xFBFEFF));
	o.setLineWidth(1.5);
	presentation.insert(k++, o);
	presentation.insert(k++, label(x + 20, y, who[i], new Color(0x282B32), 11, false));
	y += 20;
}
y += 16;
presentation.insert(k++, label(x, y, L.cols + " x " + L.rows + " cells\n" + String.format("%.2f x %.2f m each", L.cellW, L.cellH)
	+ "\n" + L.slotId.length + " slots", new Color(0x565B64), 10, false));
  }
  ShapeRectangle box(double x, double y, double w, double h, Color fill, Color line, double lw) {
ShapeRectangle s = new ShapeRectangle();
s.setPos(x, y);
s.setSize(w, h);
s.setFillColor(fill);
s.setLineColor(line);
s.setLineWidth(line == null ? 0 : lw);
return s;
  }
  ShapeText label(double x, double y, String text, Color c, int size, boolean bold) {
ShapeText t = new ShapeText();
t.setPos(x, y);
t.setText(text);
t.setColor(c);
t.setFont(new Font(uiFont, bold ? Font.BOLD : Font.PLAIN, size));
return t;
  }
  void pickFont() {
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
String[] want = {"Lato", "Segoe UI", "Helvetica Neue", "Arial", "Liberation Sans"};
Set<String> have = new HashSet<String>(Arrays.asList(java.awt.GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames()));
for (String f : want) {
	if (have.contains(f)) {
		uiFont = f;
		break;
	}
}
restyle(presentation);
  }
  void restyle(ShapeGroup g) {
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
  }
  double[] homeXY(Worker u) {
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
  }
  double[] workerXY(int i) {
Worker u = workers.get(i);
double[] p = u.motion != null ? u.motion.at(time()) : homeXY(u);
double off = ((u.k % 3) - 1) * 0.35 * wh.layout.cellW;     // spread workers that share a spot
return new double[]{sx(p[0] + off), sy(p[1] + off)};
  }
  boolean workerVisible(int i) {
return wh != null && i < workers.size();
  }
  Color roleColor(int role) {
switch (role) {
	case 0: return new Color(0x2055E1);                   // picker
	case 1: return new Color(0xE8590C);        // packer
	case 2: return new Color(0xF4B522);                    // receiver
	default: return new Color(0x12A150);       // putaway
}
  }
  Color workerColor(int i) {
Worker u = workers.get(i);
return u.busyNow ? roleColor(u.role) : new Color(0x9A9FA6);
  }
  String layoutTitle() {
if (wh == null) return "Loading the layout";
switch (wh.layout.id) {
	case "D40.3_63.1-P3-Xnone-asis": return "As-is layout, real storage";
	case "D40.3_63.1-P3-Xnone-random": return "As-is building, random storage";
	case "D40.3_63.1-P3-Xnone-class": return "As-is building, class-based storage";
	case "D40.3_63.1-P3-Xnone-abc": return "As-is building, ABC storage by turnover";
	case "D46.6_111.1-P3-X18.27_53.27-abc": return "Recommended layout";
	case "D34.93_102.1-P3-X14.93_23.27-abc": return "Runner-up layout";
	default: return "Layout " + wh.layout.id;
}
  }
  String layoutDetail() {
if (wh == null) return "";
switch (wh.layout.id) {
	case "D40.3_63.1-P3-Xnone-asis": return "Picker depot at 40.3, 63.1 m.\nNo extra cross aisles.\nStorage as recorded in the WMS, 3 packing stations.";
	case "D40.3_63.1-P3-Xnone-random": return "Picker depot at 40.3, 63.1 m.\nNo extra cross aisles.\nRandom storage, 3 packing stations.";
	case "D40.3_63.1-P3-Xnone-class": return "Picker depot at 40.3, 63.1 m.\nNo extra cross aisles.\nClass-based storage (A/B/C zones), 3 packing stations.";
	case "D40.3_63.1-P3-Xnone-abc": return "Picker depot at 40.3, 63.1 m.\nNo extra cross aisles.\nABC storage by turnover, 3 packing stations.";
	case "D46.6_111.1-P3-X18.27_53.27-abc": return "Picker depot at 46.6, 111.1 m.\n2 extra cross aisles at x = 18.27 and 53.27 m.\nABC storage by turnover, 3 packing stations.";
	case "D34.93_102.1-P3-X14.93_23.27-abc": return "Picker depot at 34.93, 102.1 m.\n2 extra cross aisles at x = 14.93 and 23.27 m.\nABC storage by turnover, 3 packing stations.";
	default: return "Slotting " + wh.layout.slotting + ".";
}
  }
  String clockText() {
return clockOf(time());
  }
  String clockOf(double t) {
long s = (long) t;
return String.format("%02d:%02d", (6 + s / 3600) % 24, (s / 60) % 60);
  }
  String dayText() {
if (wh == null) return "";
String day = new java.io.File(scenarioPath).getName().replace(".csv", "").replace("_", " ");
day = day.substring(0, 1).toUpperCase() + day.substring(1);
return day + ", seed " + seed + ", 06:00 to " + clockOf(wh.cfg.horizon);
  }
  String fastText() {
return wh != null && !done && time() > 0 && !getEngine().getRealTimeMode() ? "Skipping ahead to the first order release" : "";
  }
  double dayProgress() {
return wh == null ? 0 : Math.max(0, Math.min(1, time() / wh.cfg.horizon));
  }
  double[] liveKpi() {
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
  }
  double walkPerOrder() {
return kpi == null || kpi.tourOrders == 0 ? Double.NaN : kpi.tourM / kpi.tourOrders;
  }
  double utilSoFar(int k) {
return time() > 0 && staff[k] > 0 ? busy[k].mean(time()) / staff[k] : 0;
  }
  double plotValue(double x) {
return Double.isNaN(x) || Double.isInfinite(x) ? 0 : x;
  }
  String figValue(int i) {
if (wh == null) return "\u2013";
double[] v = liveKpi();
switch (i) {
	case 0: return Double.isNaN(walkPerOrder()) ? "\u2013" : String.format("%.0f m", walkPerOrder());
	case 1: return Double.isNaN(v[0]) ? "\u2013" : String.format("%.0f min", v[0]);
	default: return Double.isNaN(v[1]) ? "\u2013" : String.format("%.0f%%", v[1]);
}
  }
  String figNote(int i) {
if (wh == null) return "";
double[] v = liveKpi();
switch (i) {
	case 0: return kpi.tours > 0 ? String.format("%.1f km, %d carts", kpi.tourM / 1000, kpi.tours) : "no cart back yet";
	case 1: return nPacked > 0 ? "mean of " + nPacked + " orders" : "none packed yet";
	default: return (int) v[2] > 0 ? "of " + (int) v[2] + " orders due" : "no cut-off yet";
}
  }
  int boardNow(int i) {
if (wh == null) return 0;
switch (i) {
	case 0: return (int) kpi.held.value();
	case 1: return pending.size();
	case 2: return pickPool.size() - pending.size();
	case 3: return nPicked - nPacked;
	default: return (int) kpi.staging.value();
}
  }
  String boardSoFar(int i) {
if (wh == null) return "";
double[] v = liveKpi();
switch (i) {
	case 0: return (int) v[3] + " held today";
	case 1: return (int) v[4] + " released";
	case 2: return nPicked + " picked";
	case 3: return nPacked + " packed";
	default: return nShipped + " shipped";
}
  }
  String crewText(int k) {
if (wh == null) return "";
ResourcePool[] pools = {pickerPool, packerPool, receiverPool, putawayPool};
return pools[k].busy() + " of " + staff[k] + " busy";
  }
  double crewBusyNow(int k) {
if (wh == null || staff[k] == 0) return 0;
ResourcePool[] pools = {pickerPool, packerPool, receiverPool, putawayPool};
return (double) pools[k].busy() / staff[k];
  }
  String inboundText() {
if (wh == null) return "";
return String.format("Receiving buffer holds %d of %d lines.%n%,d units on the shelves.",
	(int) kpi.recvBuffer.value(), wh.recvBufferCapacity(), wh.inv.totalOnHand());
  }
  double endD(String key) {
Object o = endS == null ? null : endS.get(key);
return o instanceof Number ? ((Number) o).doubleValue() : Double.NaN;
  }
  String endLabel(int i) {
switch (i) {
	case 0: return "Orders shipped";
	case 1: return "Average fulfilment (arrival to packed)";
	case 2: return "95th percentile fulfilment";
	case 3: return "On time (packed by its cut-off)";
	case 4: return "Walk per picked order";
	case 5: return "Total picking walk";
	case 6: return "Carts";
	case 7: return "Orders held for stock";
	case 8: return "Utilisation: pickers / packers";
	case 9: return "Utilisation: receivers / putaway";
	default: return "";
}
  }
  String endText(int i) {
if (endS == null) return "";
switch (i) {
	case 0: return String.format("%d of %d arrived", (int) endD("orders_shipped"), (int) endD("orders_arrived"));
	case 1: return String.format("%.1f min", endD("fulfil_mean_s") / 60);
	case 2: return String.format("%.1f min", endD("fulfil_p95_s") / 60);
	case 3: return String.format("%.1f %%", endD("on_time_pct"));
	case 4: return String.format("%.1f m", endD("pick_m_per_order"));
	case 5: return String.format("%.2f km", endD("pick_m_total") / 1000);
	case 6: return String.format("%d  (%.1f orders per cart)", (int) endD("tours"), endD("orders_per_tour"));
	case 7: return String.valueOf((int) endD("held_orders"));
	case 8: return String.format("%.0f %% / %.0f %%", 100 * endD("util_pick"), 100 * endD("util_pack"));
	case 9: return String.format("%.0f %% / %.0f %%", 100 * endD("util_recv"), 100 * endD("util_put"));
	default: return "";
}
  }
  // orderArrive.delayTime
  double _snippet1(Order agent) {
return max(0, agent.spec.t - time());
  }
  // stockCheck.condition
  boolean _snippet2(Order agent) {
return admit(agent);
  }
  // pickPool.onEnter
  void _snippet3(Order agent) {
pending.add(agent);
dispatch();
  }
  // pack.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet4(Order agent) {
return packerPool;
  }
  // pack.delayTime
  double _snippet5(Order agent) {
return wh.packTime(agent.spec);
  }
  // staging.delayTime
  double _snippet6(Order agent) {
return stageTime(agent);
  }
  // staging.onExit
  void _snippet7(Order agent) {
orderShipped(agent);
  }
  // tourSeize.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet8(PickTour agent) {
return pickerPool;
  }
  // tourSeize.onSeizeUnit
  void _snippet9(PickTour agent, Agent unit) {
agent.picker = (Worker) unit;
  }
  // tourWalk.delayTime
  double _snippet10(PickTour agent) {
return beginTour(agent);
  }
  // tourWalk.onExit
  void _snippet11(PickTour agent) {
endTour(agent);
  }
  // tourRelease.onExit
  void _snippet12(PickTour agent) {
dispatch();
  }
  // receiptArrive.delayTime
  double _snippet13(Receipt agent) {
return max(0, agent.spec.t - time());
  }
  // receiptArrive.onExit
  void _snippet14(Receipt agent) {
kpi.receiptArrived(agent.spec, time());
  }
  // receive.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet15(Receipt agent) {
return receiverPool;
  }
  // receive.delayTime
  double _snippet16(Receipt agent) {
return wh.receiveTime(agent.spec);
  }
  // receive.onExit
  void _snippet17(Receipt agent) {
kpi.received(agent.spec, time());
  }
  // putSeize.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet18(Receipt agent) {
return putawayPool;
  }
  // putSeize.onSeizeUnit
  void _snippet19(Receipt agent, Agent unit) {
agent.worker = (Worker) unit;
  }
  // putWalk.delayTime
  double _snippet20(Receipt agent) {
return beginPutaway(agent);
  }
  // putWalk.onExit
  void _snippet21(Receipt agent) {
endPutaway(agent);
  }
  // endOfDay.delayTime
  double _snippet22(DayClock agent) {
return max(0, wh.cfg.horizon - time());
  }
  // endOfDay.onExit
  void _snippet23(DayClock agent) {
finishRun();
  }
  // wakeUp.delayTime
  double _snippet24(DayClock agent) {
return max(0, wh.scenario.orders.get(0).t - 300 - time());
  }
  // wakeUp.onExit
  void _snippet25(DayClock agent) {
getEngine().setRealTimeMode(true);
getEngine().setRealTimeScale(animScale);
  }
  // tick.delayTime
  double _snippet26(Ticker agent) {
return wh.cfg.tick;
  }
  // tick.onExit
  void _snippet27(Ticker agent) {
dispatch();
if (time() + wh.cfg.tick <= wh.cfg.horizon) tickIn.take(new Ticker());
  }
  // pickerPool.onNewUnit
  void _snippet28(Worker unit) {
registerWorker(unit, 0);
  }
  // pickerPool.onSeize
  void _snippet29(Worker unit, Agent agent) {
busy[0].add(time(), 1);
unit.busyNow = true;
  }
  // pickerPool.onRelease
  void _snippet30(Worker unit, Agent agent) {
busy[0].add(time(), -1);
unit.busyNow = false;
  }
  // packerPool.onNewUnit
  void _snippet31(Worker unit) {
registerWorker(unit, 1);
  }
  // packerPool.onSeize
  void _snippet32(Worker unit, Agent agent) {
busy[1].add(time(), 1);
unit.busyNow = true;
  }
  // packerPool.onRelease
  void _snippet33(Worker unit, Agent agent) {
busy[1].add(time(), -1);
unit.busyNow = false;
  }
  // receiverPool.onNewUnit
  void _snippet34(Worker unit) {
registerWorker(unit, 2);
  }
  // receiverPool.onSeize
  void _snippet35(Worker unit, Agent agent) {
busy[2].add(time(), 1);
unit.busyNow = true;
  }
  // receiverPool.onRelease
  void _snippet36(Worker unit, Agent agent) {
busy[2].add(time(), -1);
unit.busyNow = false;
  }
  // putawayPool.onNewUnit
  void _snippet37(Worker unit) {
registerWorker(unit, 3);
  }
  // putawayPool.onSeize
  void _snippet38(Worker unit, Agent agent) {
busy[3].add(time(), 1);
unit.busyNow = true;
  }
  // putawayPool.onRelease
  void _snippet39(Worker unit, Agent agent) {
busy[3].add(time(), -1);
unit.busyNow = false;
  }
  void _startup() {
setup();
  }
  // dayInfo.TextCode
  Object _snippet40() {
return dayText();
  }
  // clock.TextCode
  Object _snippet41() {
return clockText();
  }
  // fastForward.TextCode
  Object _snippet42() {
return fastText();
  }
  // dayBar.WidthCode
  double _snippet43() {
return 1410 * dayProgress();
  }
  // layoutName.TextCode
  Object _snippet44() {
return layoutTitle();
  }
  // layoutWords.TextCode
  Object _snippet45() {
return layoutDetail();
  }
  // fig0.TextCode
  Object _snippet46() {
return figValue(0);
  }
  // text4.TextCode
  Object _snippet47() {
return figNote(0);
  }
  // fig1.TextCode
  Object _snippet48() {
return figValue(1);
  }
  // text7.TextCode
  Object _snippet49() {
return figNote(1);
  }
  // fig2.TextCode
  Object _snippet50() {
return figValue(2);
  }
  // text10.TextCode
  Object _snippet51() {
return figNote(2);
  }
  // text13.TextCode
  Object _snippet52() {
return wh == null ? "" : nArrived + " of " + wh.scenario.orders.size() + " arrived";
  }
  // rectangle18.VisibleCode
  boolean _snippet53() {
return boardNow(0) > 0;
  }
  // text19.ColorCode
  Color _snippet54() {
return boardNow(0) > 0 ? new Color(0x0A0D13) : new Color(0xFBFEFF);
  }
  // text20.ColorCode
  Color _snippet55() {
return boardNow(0) > 0 ? new Color(0x0A0D13) : new Color(0xF4B522);
  }
  // text20.TextCode
  Object _snippet56() {
return boardNow(0);
  }
  // text21.ColorCode
  Color _snippet57() {
return boardNow(0) > 0 ? new Color(0x282B32) : new Color(0x9A9FA6);
  }
  // text21.TextCode
  Object _snippet58() {
return boardSoFar(0);
  }
  // text24.TextCode
  Object _snippet59() {
return boardNow(1);
  }
  // text25.TextCode
  Object _snippet60() {
return boardSoFar(1);
  }
  // text28.TextCode
  Object _snippet61() {
return boardNow(2);
  }
  // text29.TextCode
  Object _snippet62() {
return boardSoFar(2);
  }
  // text32.TextCode
  Object _snippet63() {
return boardNow(3);
  }
  // text33.TextCode
  Object _snippet64() {
return boardSoFar(3);
  }
  // text36.TextCode
  Object _snippet65() {
return boardNow(4);
  }
  // text37.TextCode
  Object _snippet66() {
return boardSoFar(4);
  }
  // text41.TextCode
  Object _snippet67() {
return String.format("%.0f%% of the day", 100 * utilSoFar(0));
  }
  // text42.TextCode
  Object _snippet68() {
return crewText(0);
  }
  // rectangle44.WidthCode
  double _snippet69() {
return 420 * crewBusyNow(0);
  }
  // text46.TextCode
  Object _snippet70() {
return String.format("%.0f%% of the day", 100 * utilSoFar(1));
  }
  // text47.TextCode
  Object _snippet71() {
return crewText(1);
  }
  // rectangle49.WidthCode
  double _snippet72() {
return 420 * crewBusyNow(1);
  }
  // text51.TextCode
  Object _snippet73() {
return String.format("%.0f%% of the day", 100 * utilSoFar(2));
  }
  // text52.TextCode
  Object _snippet74() {
return crewText(2);
  }
  // rectangle54.WidthCode
  double _snippet75() {
return 420 * crewBusyNow(2);
  }
  // text56.TextCode
  Object _snippet76() {
return String.format("%.0f%% of the day", 100 * utilSoFar(3));
  }
  // text57.TextCode
  Object _snippet77() {
return crewText(3);
  }
  // rectangle59.WidthCode
  double _snippet78() {
return 420 * crewBusyNow(3);
  }
  // text60.TextCode
  Object _snippet79() {
return inboundText();
  }
  // throughput.arrived
  double _snippet80() {
return plotValue(nArrived);
  }
  // throughput.picked
  double _snippet81() {
return plotValue(nPicked);
  }
  // throughput.shipped
  double _snippet82() {
return plotValue(nShipped);
  }
  // walk.walk per order (m)
  double _snippet83() {
return plotValue(walkPerOrder());
  }
  // fulfil.fulfilment (min)
  double _snippet84() {
return plotValue(liveKpi()[0]);
  }
  // workerDot.XCode
  double _snippet85(int index) {
return workerXY(index)[0];
  }
  // workerDot.YCode
  double _snippet86(int index) {
return workerXY(index)[1];
  }
  // workerDot.VisibleCode
  boolean _snippet87(int index) {
return workerVisible(index);
  }
  // workerDot.replication
  int _snippet88() {
return 80;
  }
  // workerDot.FillColorCode
  Color _snippet89(int index) {
return workerColor(index);
  }
  // rectangle70.VisibleCode
  boolean _snippet90() {
return done;
  }
  // text71.VisibleCode
  boolean _snippet91() {
return done;
  }
  // text72.VisibleCode
  boolean _snippet92() {
return done;
  }
  // text72.TextCode
  Object _snippet93() {
return layoutTitle();
  }
  // text73.VisibleCode
  boolean _snippet94() {
return done;
  }
  // text73.TextCode
  Object _snippet95() {
return dayText();
  }
  // rectangle74.VisibleCode
  boolean _snippet96() {
return done;
  }
  // text75.VisibleCode
  boolean _snippet97() {
return done;
  }
  // text75.TextCode
  Object _snippet98() {
return endLabel(0);
  }
  // text76.VisibleCode
  boolean _snippet99() {
return done;
  }
  // text76.TextCode
  Object _snippet100() {
return endText(0);
  }
  // rectangle77.VisibleCode
  boolean _snippet101() {
return done;
  }
  // text78.VisibleCode
  boolean _snippet102() {
return done;
  }
  // text78.TextCode
  Object _snippet103() {
return endLabel(1);
  }
  // text79.VisibleCode
  boolean _snippet104() {
return done;
  }
  // text79.TextCode
  Object _snippet105() {
return endText(1);
  }
  // rectangle80.VisibleCode
  boolean _snippet106() {
return done;
  }
  // text81.VisibleCode
  boolean _snippet107() {
return done;
  }
  // text81.TextCode
  Object _snippet108() {
return endLabel(2);
  }
  // text82.VisibleCode
  boolean _snippet109() {
return done;
  }
  // text82.TextCode
  Object _snippet110() {
return endText(2);
  }
  // rectangle83.VisibleCode
  boolean _snippet111() {
return done;
  }
  // text84.VisibleCode
  boolean _snippet112() {
return done;
  }
  // text84.TextCode
  Object _snippet113() {
return endLabel(3);
  }
  // text85.VisibleCode
  boolean _snippet114() {
return done;
  }
  // text85.TextCode
  Object _snippet115() {
return endText(3);
  }
  // rectangle86.VisibleCode
  boolean _snippet116() {
return done;
  }
  // text87.VisibleCode
  boolean _snippet117() {
return done;
  }
  // text87.TextCode
  Object _snippet118() {
return endLabel(4);
  }
  // text88.VisibleCode
  boolean _snippet119() {
return done;
  }
  // text88.TextCode
  Object _snippet120() {
return endText(4);
  }
  // rectangle89.VisibleCode
  boolean _snippet121() {
return done;
  }
  // text90.VisibleCode
  boolean _snippet122() {
return done;
  }
  // text90.TextCode
  Object _snippet123() {
return endLabel(5);
  }
  // text91.VisibleCode
  boolean _snippet124() {
return done;
  }
  // text91.TextCode
  Object _snippet125() {
return endText(5);
  }
  // rectangle92.VisibleCode
  boolean _snippet126() {
return done;
  }
  // text93.VisibleCode
  boolean _snippet127() {
return done;
  }
  // text93.TextCode
  Object _snippet128() {
return endLabel(6);
  }
  // text94.VisibleCode
  boolean _snippet129() {
return done;
  }
  // text94.TextCode
  Object _snippet130() {
return endText(6);
  }
  // rectangle95.VisibleCode
  boolean _snippet131() {
return done;
  }
  // text96.VisibleCode
  boolean _snippet132() {
return done;
  }
  // text96.TextCode
  Object _snippet133() {
return endLabel(7);
  }
  // text97.VisibleCode
  boolean _snippet134() {
return done;
  }
  // text97.TextCode
  Object _snippet135() {
return endText(7);
  }
  // rectangle98.VisibleCode
  boolean _snippet136() {
return done;
  }
  // text99.VisibleCode
  boolean _snippet137() {
return done;
  }
  // text99.TextCode
  Object _snippet138() {
return endLabel(8);
  }
  // text100.VisibleCode
  boolean _snippet139() {
return done;
  }
  // text100.TextCode
  Object _snippet140() {
return endText(8);
  }
  // rectangle101.VisibleCode
  boolean _snippet141() {
return done;
  }
  // text102.VisibleCode
  boolean _snippet142() {
return done;
  }
  // text102.TextCode
  Object _snippet143() {
return endLabel(9);
  }
  // text103.VisibleCode
  boolean _snippet144() {
return done;
  }
  // text103.TextCode
  Object _snippet145() {
return endText(9);
  }
  // text104.VisibleCode
  boolean _snippet146() {
return done;
  }
  void _pvCompareLayouts(Main root) { int runs = 0;
runs++;
traceln("run " + runs + " of 60 done");
 Object t = "runs done: " + runs; }
  void _pvValidateRealDays(Main root) { int runs = 0;
runs++;
traceln("run " + runs + " of 10 done");
 Object t = "runs done: " + runs; }
  void _pvStaffPickers(Main root) { int runs = 0;
runs++;
traceln("run " + runs + " of 70 done");
 Object t = "runs done: " + runs; }
  void _pvCartSize(Main root) { int runs = 0;
runs++;
traceln("run " + runs + " of 40 done");
 Object t = "runs done: " + runs; }
// ===== Json (from java/src/wh/Json.java) =====
/** Minimal JSON reader: objects -> LinkedHashMap, arrays -> ArrayList, numbers -> Double. */
public static final class Json {
  private final String s;
  private int i;

  private Json(String s) { this.s = s; }

  public static Object parse(String text) {
    Json p = new Json(text);
    p.ws();
    Object v = p.value();
    p.ws();
    if (p.i != p.s.length()) throw p.err("unexpected trailing text");
    return v;
  }

  public static Object read(String path) {
    try {
      return parse(new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(path)), java.nio.charset.StandardCharsets.UTF_8));
    } catch (java.io.IOException e) {
      throw new IllegalArgumentException("cannot read " + path + ": " + e.getMessage());
    }
  }

  // ---- typed access helpers
  @SuppressWarnings("unchecked")
  public static Map<String, Object> obj(Object o, String what) {
    if (!(o instanceof Map)) throw new IllegalArgumentException(what + ": expected a JSON object");
    return (Map<String, Object>) o;
  }

  @SuppressWarnings("unchecked")
  public static List<Object> arr(Object o, String what) {
    if (!(o instanceof List)) throw new IllegalArgumentException(what + ": expected a JSON array");
    return (List<Object>) o;
  }

  public static Object get(Map<String, Object> m, String key) {
    if (!m.containsKey(key)) throw new IllegalArgumentException("missing key \"" + key + "\"");
    return m.get(key);
  }

  public static double num(Object o, String what) {
    if (!(o instanceof Double)) throw new IllegalArgumentException(what + ": expected a number");
    return (Double) o;
  }

  public static int integer(Object o, String what) {
    double d = num(o, what);
    if (d != Math.rint(d)) throw new IllegalArgumentException(what + ": expected an integer, got " + d);
    return (int) d;
  }

  public static String str(Object o, String what) {
    if (!(o instanceof String)) throw new IllegalArgumentException(what + ": expected a string");
    return (String) o;
  }

  // ---- parser
  private Object value() {
    if (i >= s.length()) throw err("unexpected end");
    char c = s.charAt(i);
    if (c == '{') return object();
    if (c == '[') return array();
    if (c == '"') return string();
    if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
    if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
    if (s.startsWith("null", i)) { i += 4; return null; }
    return number();
  }

  private Map<String, Object> object() {
    Map<String, Object> m = new LinkedHashMap<String, Object>();
    i++;
    ws();
    if (peek() == '}') { i++; return m; }
    while (true) {
      ws();
      if (peek() != '"') throw err("expected a key");
      String k = string();
      ws();
      expect(':');
      ws();
      m.put(k, value());
      ws();
      char c = next();
      if (c == '}') return m;
      if (c != ',') throw err("expected ',' or '}'");
    }
  }

  private List<Object> array() {
    List<Object> a = new ArrayList<Object>();
    i++;
    ws();
    if (peek() == ']') { i++; return a; }
    while (true) {
      ws();
      a.add(value());
      ws();
      char c = next();
      if (c == ']') return a;
      if (c != ',') throw err("expected ',' or ']'");
    }
  }

  private String string() {
    expect('"');
    StringBuilder b = new StringBuilder();
    while (true) {
      char c = next();
      if (c == '"') return b.toString();
      if (c == '\\') {
        char e = next();
        switch (e) {
          case '"': b.append('"'); break;
          case '\\': b.append('\\'); break;
          case '/': b.append('/'); break;
          case 'b': b.append('\b'); break;
          case 'f': b.append('\f'); break;
          case 'n': b.append('\n'); break;
          case 'r': b.append('\r'); break;
          case 't': b.append('\t'); break;
          case 'u':
            if (i + 4 > s.length()) throw err("bad \\u escape");
            int cp = 0;
            for (int k = 0; k < 4; k++) {
              int dgt = Character.digit(s.charAt(i + k), 16);
              if (dgt < 0) throw err("bad \\u escape");
              cp = cp * 16 + dgt;
            }
            b.append((char) cp);
            i += 4;
            break;
          default: throw err("bad escape \\" + e);
        }
      } else {
        b.append(c);
      }
    }
  }

  private Double number() {
    int st = i;
    while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
    if (st == i) throw err("unexpected character '" + s.charAt(i) + "'");
    try {
      return Double.valueOf(s.substring(st, i));
    } catch (NumberFormatException e) {
      throw err("bad number " + s.substring(st, i));
    }
  }

  private void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }
  private char peek() { if (i >= s.length()) throw err("unexpected end"); return s.charAt(i); }
  private char next() { char c = peek(); i++; return c; }
  private void expect(char c) { if (next() != c) throw err("expected '" + c + "'"); }
  private IllegalArgumentException err(String m) { return new IllegalArgumentException("JSON: " + m + " at position " + i); }
}

// ===== Dist (from java/src/wh/Dist.java) =====
/**
 * A service-time distribution read from the run config, e.g. {"dist": "gamma", "shape": 4, "scale": 12}.
 *
 *   const(value)  uniform(min, max)  triangular(min, mode, max)  exponential(mean)
 *   normal(mean, sd, min = 0; truncated)  lognormal(mean, sd; of the variable itself)
 *   gamma(shape, scale)  weibull(shape, scale)  empirical(values: resampled uniformly)
 *
 * Samples are never negative. The random stream is passed in, so the caller controls common random numbers.
 */
public static final class Dist {
  public final String kind;
  private final double a, b, c;
  private final double[] values;

  private Dist(String kind, double a, double b, double c, double[] values) {
    this.kind = kind; this.a = a; this.b = b; this.c = c; this.values = values;
  }

  public static Dist constant(double v) { return new Dist("const", v, 0, 0, null); }

  public static Dist of(Object o, String what) {
    Map<String, Object> m = Json.obj(o, what);
    String k = Json.str(Json.get(m, "dist"), what + ".dist");
    try {
      switch (k) {
        case "const": return check(new Dist(k, p(m, "value"), 0, 0, null), p(m, "value") >= 0, what, "value >= 0");
        case "uniform": return check(new Dist(k, p(m, "min"), p(m, "max"), 0, null), 0 <= p(m, "min") && p(m, "min") <= p(m, "max"), what, "0 <= min <= max");
        case "triangular": {
          double lo = p(m, "min"), mo = p(m, "mode"), hi = p(m, "max");
          return check(new Dist(k, lo, mo, hi, null), 0 <= lo && lo <= mo && mo <= hi && lo < hi, what, "0 <= min <= mode <= max, min < max");
        }
        case "exponential": return check(new Dist(k, p(m, "mean"), 0, 0, null), p(m, "mean") > 0, what, "mean > 0");
        case "normal": {
          double lo = m.containsKey("min") ? p(m, "min") : 0.0;
          return check(new Dist(k, p(m, "mean"), p(m, "sd"), lo, null), p(m, "sd") >= 0 && lo >= 0, what, "sd >= 0, min >= 0");
        }
        case "lognormal": return check(new Dist(k, p(m, "mean"), p(m, "sd"), 0, null), p(m, "mean") > 0 && p(m, "sd") >= 0, what, "mean > 0, sd >= 0");
        case "gamma": return check(new Dist(k, p(m, "shape"), p(m, "scale"), 0, null), p(m, "shape") > 0 && p(m, "scale") > 0, what, "shape > 0, scale > 0");
        case "weibull": return check(new Dist(k, p(m, "shape"), p(m, "scale"), 0, null), p(m, "shape") > 0 && p(m, "scale") > 0, what, "shape > 0, scale > 0");
        case "empirical": {
          List<Object> l = Json.arr(Json.get(m, "values"), what + ".values");
          if (l.isEmpty()) throw new IllegalArgumentException(what + ": empirical needs at least one value");
          double[] v = new double[l.size()];
          for (int i = 0; i < v.length; i++) {
            v[i] = Json.num(l.get(i), what + ".values");
            if (v[i] < 0) throw new IllegalArgumentException(what + ": empirical values must be >= 0");
          }
          return new Dist(k, 0, 0, 0, v);
        }
        default: throw new IllegalArgumentException(what + ": unknown distribution \"" + k + "\"");
      }
    } catch (IllegalArgumentException e) {
      if (e.getMessage().startsWith(what)) throw e;
      throw new IllegalArgumentException(what + ": " + e.getMessage());
    }
  }

  private static double p(Map<String, Object> m, String key) { return Json.num(Json.get(m, key), key); }

  private static Dist check(Dist d, boolean ok, String what, String rule) {
    if (!ok) throw new IllegalArgumentException(what + ": " + d.kind + " needs " + rule);
    return d;
  }

  public double sample(Random r) {
    double x;
    switch (kind) {
      case "const": x = a; break;
      case "uniform": x = a + (b - a) * r.nextDouble(); break;
      case "triangular": {
        double u = r.nextDouble(), f = (b - a) / (c - a);
        x = u < f ? a + Math.sqrt(u * (c - a) * (b - a)) : c - Math.sqrt((1 - u) * (c - a) * (c - b));
        break;
      }
      case "exponential": x = -a * Math.log(1 - r.nextDouble()); break;
      case "normal": x = truncatedNormal(a, b, c, r); break;
      case "lognormal": {
        double s2 = Math.log(1 + (b * b) / (a * a));
        x = Math.exp(Math.log(a) - s2 / 2 + Math.sqrt(s2) * r.nextGaussian());
        break;
      }
      case "gamma": x = b * gamma(a, r); break;
      case "weibull": x = b * Math.pow(-Math.log(1 - r.nextDouble()), 1 / a); break;
      case "empirical": x = values[r.nextInt(values.length)]; break;
      default: throw new IllegalStateException(kind);
    }
    return Math.max(0, x);
  }

  /** Theoretical mean (empirical: sample mean; normal: of the untruncated distribution). */
  public double mean() {
    switch (kind) {
      case "const": return a;
      case "uniform": return (a + b) / 2;
      case "triangular": return (a + b + c) / 3;
      case "exponential": case "lognormal": case "normal": return a;
      case "gamma": return a * b;
      case "weibull": return b * Math.exp(lgamma(1 + 1 / a));
      default: { double s = 0; for (double v : values) s += v; return s / values.length; }
    }
  }

  /**
   * Normal(mean, sd) conditioned on x >= min, exactly: plain rejection when min is at most half an sd above
   * the mean (acceptance >= 31%), otherwise Robert's (1995) exponential-proposal rejection for the tail.
   */
  private static double truncatedNormal(double mean, double sd, double min, Random r) {
    if (sd == 0) return Math.max(mean, min);
    double lo = (min - mean) / sd;
    if (lo <= 0.5) {
      while (true) {
        double z = r.nextGaussian();
        if (z >= lo) return mean + sd * z;
      }
    }
    double alpha = (lo + Math.sqrt(lo * lo + 4)) / 2;
    while (true) {
      double z = lo - Math.log(1 - r.nextDouble()) / alpha;
      if (r.nextDouble() <= Math.exp(-(z - alpha) * (z - alpha) / 2)) return mean + sd * z;
    }
  }

  /** Marsaglia-Tsang (2000); shape < 1 via the Gamma(shape + 1) * U^(1/shape) boost. */
  private static double gamma(double k, Random r) {
    if (k < 1) return gamma(k + 1, r) * Math.pow(r.nextDouble(), 1 / k);
    double d = k - 1.0 / 3, cc = 1 / Math.sqrt(9 * d);
    while (true) {
      double z = r.nextGaussian(), v = 1 + cc * z;
      if (v <= 0) continue;
      v = v * v * v;
      double u = r.nextDouble();
      if (Math.log(u) < 0.5 * z * z + d - d * v + d * Math.log(v)) return d * v;
    }
  }

  /** Lanczos log-gamma (for the Weibull mean only). */
  private static double lgamma(double x) {
    double[] g = {676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
        12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7};
    if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x);
    x -= 1;
    double s = 0.99999999999980993;
    for (int i = 0; i < g.length; i++) s += g[i] / (x + i + 1);
    double t = x + g.length - 0.5;
    return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(s);
  }

  @Override public String toString() { return kind + "(mean " + String.format("%.2f", mean()) + ")"; }
}

// ===== RunConfig (from java/src/wh/RunConfig.java) =====
/** data/config/run_config.json (schema whsim.run/1): horizon, cut-offs, resources, speeds, batching, service times. */
public static final class RunConfig {
  public double horizon, promiseLead, walkSpeed, putawaySpeed;
  public double[] cutoffs;
  public int pickers, packers, receivers, putaway, recvPerCell;
  /** Batch picking: a cart holds cartUnits units (0 = single-order picking), at most maxOrders orders (0 = no limit). */
  public int cartUnits, maxOrders;
  /** Wave release: a cart leaves when the waiting units fill it or the oldest waiting order has waited maxWait s;
   *  the rule is re-checked every tick s. */
  public double maxWait, tick;
  public Dist pickPerLine, packPerOrder, packPerUnit, receivePerLine, putawayHandling;

  public static RunConfig load(String path) { return parse(Json.read(path)); }

  public static RunConfig parse(Object root) {
    Map<String, Object> m = Json.obj(root, "run config");
    String schema = Json.str(Json.get(m, "schema"), "schema");
    if (!schema.equals("whsim.run/1")) throw new IllegalArgumentException("run config: unsupported schema " + schema);
    RunConfig c = new RunConfig();
    c.horizon = Json.num(Json.get(m, "horizon_s"), "horizon_s");
    c.promiseLead = Json.num(Json.get(m, "promise_lead_s"), "promise_lead_s");
    List<Object> cl = Json.arr(Json.get(m, "cutoffs_s"), "cutoffs_s");
    c.cutoffs = new double[cl.size()];
    for (int i = 0; i < c.cutoffs.length; i++) c.cutoffs[i] = Json.num(cl.get(i), "cutoffs_s");
    Map<String, Object> r = Json.obj(Json.get(m, "resources"), "resources");
    c.pickers = Json.integer(Json.get(r, "pickers"), "resources.pickers");
    c.packers = Json.integer(Json.get(r, "packers"), "resources.packers");
    c.receivers = Json.integer(Json.get(r, "receivers"), "resources.receivers");
    c.putaway = Json.integer(Json.get(r, "putaway"), "resources.putaway");
    c.walkSpeed = Json.num(Json.get(m, "walk_speed_mps"), "walk_speed_mps");
    c.putawaySpeed = Json.num(Json.get(m, "putaway_speed_mps"), "putaway_speed_mps");
    c.recvPerCell = Json.integer(Json.get(m, "recv_buffer_per_cell"), "recv_buffer_per_cell");
    Map<String, Object> b = Json.obj(Json.get(m, "batching"), "batching");
    c.cartUnits = Json.integer(Json.get(b, "cart_units"), "batching.cart_units");
    c.maxOrders = Json.integer(Json.get(b, "max_orders"), "batching.max_orders");
    c.maxWait = Json.num(Json.get(b, "max_wait_s"), "batching.max_wait_s");
    c.tick = Json.num(Json.get(b, "tick_s"), "batching.tick_s");
    Map<String, Object> t = Json.obj(Json.get(m, "times"), "times");
    c.pickPerLine = Dist.of(Json.get(t, "pick_per_line_s"), "times.pick_per_line_s");
    c.packPerOrder = Dist.of(Json.get(t, "pack_per_order_s"), "times.pack_per_order_s");
    c.packPerUnit = Dist.of(Json.get(t, "pack_per_unit_s"), "times.pack_per_unit_s");
    c.receivePerLine = Dist.of(Json.get(t, "receive_per_line_s"), "times.receive_per_line_s");
    c.putawayHandling = Dist.of(Json.get(t, "putaway_handling_s"), "times.putaway_handling_s");
    c.check();
    return c;
  }

  public void check() {
    if (!(horizon > 0)) throw new IllegalArgumentException("horizon_s must be > 0");
    if (promiseLead < 0) throw new IllegalArgumentException("promise_lead_s must be >= 0");
    if (cutoffs.length == 0) throw new IllegalArgumentException("cutoffs_s must list at least one cut-off");
    for (int i = 0; i < cutoffs.length; i++) {
      if (!(cutoffs[i] > 0 && cutoffs[i] < horizon))
        throw new IllegalArgumentException("cut-off " + cutoffs[i] + " must be inside (0, horizon_s)");
      if (i > 0 && cutoffs[i] <= cutoffs[i - 1]) throw new IllegalArgumentException("cutoffs_s must be increasing");
    }
    if (pickers < 1 || packers < 1 || receivers < 1 || putaway < 1)
      throw new IllegalArgumentException("every resource count must be >= 1");
    if (!(walkSpeed > 0 && putawaySpeed > 0)) throw new IllegalArgumentException("speeds must be > 0");
    if (recvPerCell < 1) throw new IllegalArgumentException("recv_buffer_per_cell must be >= 1");
    if (cartUnits < 0 || maxOrders < 0) throw new IllegalArgumentException("batching.cart_units and max_orders must be >= 0");
    if (maxWait < 0 || !(tick > 0)) throw new IllegalArgumentException("batching.max_wait_s must be >= 0 and tick_s > 0");
  }

  /** First cut-off at or after t, or +infinity if none is left today. */
  public double nextCutoff(double t) {
    for (double c : cutoffs) if (c >= t) return c;
    return Double.POSITIVE_INFINITY;
  }

  /** The cut-off an order arriving at t is due for (+infinity: arrives too late for today). */
  public double dueCutoff(double tArrive) { return nextCutoff(tArrive + promiseLead); }
}

// ===== LayoutData (from java/src/wh/LayoutData.java) =====
/** A compiled layout (schema whsim.layout/1) as written by python/whsim/layout.py. */
public static final class LayoutData {
  public static final class Facility {
    public String id, type;
    public int r, c, node;
    public double x, y;
  }

  public String id, slotting;
  public double cellW, cellH, originX, originY;   // metres; cell (r, c) centre = origin + ((c + .5) cellW, (r + .5) cellH)
  public int rows, cols;
  public String[][] grid;
  // aisle graph
  public int n;
  public double[] nx, ny;
  public int[][] adj;
  public double[][] adjLen;
  // facilities
  public List<Facility> facilities = new ArrayList<Facility>();
  public int home;                 // picker depot node
  public int[] stations;           // packing station nodes, in id order PK1, PK2, ...
  public int[] inDocks;            // inbound dock nodes DI1, DI2, ...
  public int recvCells, stagingCells;
  // slots
  public String[] slotId, slotSku;
  public int[] slotNode, slotR, slotC;
  public Map<String, Integer> slotOfSku = new HashMap<String, Integer>();

  public static LayoutData load(String path) { return parse(Json.read(path)); }

  public static LayoutData parse(Object root) {
    Map<String, Object> m = Json.obj(root, "layout");
    String schema = Json.str(Json.get(m, "schema"), "schema");
    if (!schema.equals("whsim.layout/1")) throw new IllegalArgumentException("layout: unsupported schema " + schema);
    LayoutData L = new LayoutData();
    L.id = Json.str(Json.get(m, "id"), "id");
    L.slotting = Json.str(Json.get(m, "slotting"), "slotting");
    L.cellW = Json.num(Json.get(m, "cell_w"), "cell_w");
    L.cellH = Json.num(Json.get(m, "cell_h"), "cell_h");
    List<Object> org = Json.arr(Json.get(m, "origin"), "origin");
    L.originX = Json.num(org.get(0), "origin x");
    L.originY = Json.num(org.get(1), "origin y");
    L.rows = Json.integer(Json.get(m, "rows"), "rows");
    L.cols = Json.integer(Json.get(m, "cols"), "cols");
    List<Object> g = Json.arr(Json.get(m, "grid"), "grid");
    if (g.size() != L.rows) throw new IllegalArgumentException("layout: grid has " + g.size() + " rows, rows = " + L.rows);
    L.grid = new String[L.rows][];
    for (int r = 0; r < L.rows; r++) {
      L.grid[r] = Json.str(g.get(r), "grid row").trim().split("\\s+");
      if (L.grid[r].length != L.cols) throw new IllegalArgumentException("layout: grid row " + r + " has " + L.grid[r].length + " cells, cols = " + L.cols);
    }
    List<Object> nodes = Json.arr(Json.get(m, "nodes"), "nodes");
    L.n = nodes.size();
    L.nx = new double[L.n];
    L.ny = new double[L.n];
    for (int i = 0; i < L.n; i++) {
      List<Object> nd = Json.arr(nodes.get(i), "node");
      L.nx[i] = Json.num(nd.get(2), "node x");
      L.ny[i] = Json.num(nd.get(3), "node y");
    }
    List<Object> edges = Json.arr(Json.get(m, "edges"), "edges");
    int[] deg = new int[L.n];
    int[][] e = new int[edges.size()][2];
    double[] w = new double[edges.size()];
    for (int k = 0; k < e.length; k++) {
      List<Object> ed = Json.arr(edges.get(k), "edge");
      e[k][0] = L.node(Json.integer(ed.get(0), "edge"));
      e[k][1] = L.node(Json.integer(ed.get(1), "edge"));
      w[k] = Json.num(ed.get(2), "edge length");
      if (!(w[k] > 0)) throw new IllegalArgumentException("layout: edge " + k + " has length " + w[k]);
      deg[e[k][0]]++;
      deg[e[k][1]]++;
    }
    L.adj = new int[L.n][];
    L.adjLen = new double[L.n][];
    for (int i = 0; i < L.n; i++) { L.adj[i] = new int[deg[i]]; L.adjLen[i] = new double[deg[i]]; deg[i] = 0; }
    for (int k = 0; k < e.length; k++) {
      int a = e[k][0], b = e[k][1];
      L.adj[a][deg[a]] = b; L.adjLen[a][deg[a]++] = w[k];
      L.adj[b][deg[b]] = a; L.adjLen[b][deg[b]++] = w[k];
    }
    List<Integer> pk = new ArrayList<Integer>(), di = new ArrayList<Integer>();
    int homes = 0;
    for (Object fo : Json.arr(Json.get(m, "facilities"), "facilities")) {
      Map<String, Object> fm = Json.obj(fo, "facility");
      Facility f = new Facility();
      f.id = Json.str(Json.get(fm, "id"), "facility id");
      f.type = Json.str(Json.get(fm, "type"), "facility type");
      f.r = Json.integer(Json.get(fm, "r"), "facility r");
      f.c = Json.integer(Json.get(fm, "c"), "facility c");
      f.x = Json.num(Json.get(fm, "x"), "facility x");
      f.y = Json.num(Json.get(fm, "y"), "facility y");
      f.node = L.node(Json.integer(Json.get(fm, "node"), "facility node"));
      L.facilities.add(f);
      if (f.type.equals("H")) { L.home = f.node; homes++; }
      else if (f.type.equals("PK")) pk.add(f.node);
      else if (f.type.equals("DI")) di.add(f.node);
      else if (f.type.equals("R")) L.recvCells++;
      else if (f.type.equals("G")) L.stagingCells++;
    }
    if (homes != 1) throw new IllegalArgumentException("layout: needs exactly one depot H, found " + homes);
    if (pk.isEmpty() || di.isEmpty() || L.recvCells == 0)
      throw new IllegalArgumentException("layout: needs at least one PK, one DI and one R");
    L.stations = toArray(pk);
    L.inDocks = toArray(di);
    List<Object> slots = Json.arr(Json.get(m, "slots"), "slots");
    int ns = slots.size();
    L.slotId = new String[ns]; L.slotSku = new String[ns];
    L.slotNode = new int[ns]; L.slotR = new int[ns]; L.slotC = new int[ns];
    for (int i = 0; i < ns; i++) {
      Map<String, Object> sm = Json.obj(slots.get(i), "slot");
      L.slotId[i] = Json.str(Json.get(sm, "id"), "slot id");
      Object sku = Json.get(sm, "sku");
      L.slotSku[i] = sku == null ? null : Json.str(sku, "slot sku");
      L.slotNode[i] = L.node(Json.integer(Json.get(sm, "node"), "slot node"));
      L.slotR[i] = Json.integer(Json.get(sm, "r"), "slot r");
      L.slotC[i] = Json.integer(Json.get(sm, "c"), "slot c");
      if (L.slotSku[i] != null && !L.slotOfSku.containsKey(L.slotSku[i])) L.slotOfSku.put(L.slotSku[i], i);
    }
    return L;
  }

  private int node(int k) {
    if (k < 0 || k >= n) throw new IllegalArgumentException("layout: node index " + k + " out of range 0.." + (n - 1));
    return k;
  }

  private static int[] toArray(List<Integer> l) {
    int[] a = new int[l.size()];
    for (int i = 0; i < a.length; i++) a[i] = l.get(i);
    return a;
  }

  /** Access node of the slot holding sku (-1 if the layout does not stock it). */
  public int nodeOfSku(String sku) {
    Integer s = slotOfSku.get(sku);
    return s == null ? -1 : slotNode[s];
  }

  public double widthM() { return cols * cellW; }
  public double heightM() { return rows * cellH; }
}

// ===== PathGraph (from java/src/wh/PathGraph.java) =====
/** Shortest paths on the layout's aisle graph (Dijkstra per source, cached). */
public static final class PathGraph {
  private final LayoutData L;
  private final Map<Integer, double[]> dist = new HashMap<Integer, double[]>();
  private final Map<Integer, int[]> pred = new HashMap<Integer, int[]>();

  public PathGraph(LayoutData L) { this.L = L; }

  public double[] distFrom(int s) {
    double[] d = dist.get(s);
    if (d == null) { run(s); d = dist.get(s); }
    return d;
  }

  public double dist(int a, int b) { return distFrom(a)[b]; }

  /** Node sequence a .. b (inclusive) along a shortest path. */
  public int[] path(int a, int b) {
    distFrom(a);
    int[] p = pred.get(a);
    if (a != b && p[b] < 0) throw new IllegalStateException("node " + b + " is not reachable from " + a);
    List<Integer> rev = new ArrayList<Integer>();
    for (int v = b; v != a; v = p[v]) rev.add(v);
    rev.add(a);
    int[] out = new int[rev.size()];
    for (int i = 0; i < out.length; i++) out[i] = rev.get(out.length - 1 - i);
    return out;
  }

  private void run(int s) {
    double[] d = new double[L.n];
    int[] p = new int[L.n];
    Arrays.fill(d, Double.POSITIVE_INFINITY);
    Arrays.fill(p, -1);
    d[s] = 0;
    PriorityQueue<double[]> pq = new PriorityQueue<double[]>((x, y) -> x[0] != y[0] ? Double.compare(x[0], y[0]) : Double.compare(x[1], y[1]));
    pq.add(new double[]{0, s});
    while (!pq.isEmpty()) {
      double[] top = pq.poll();
      int u = (int) top[1];
      if (top[0] > d[u]) continue;
      for (int k = 0; k < L.adj[u].length; k++) {
        int v = L.adj[u][k];
        double nd = d[u] + L.adjLen[u][k];
        if (nd < d[v]) { d[v] = nd; p[v] = u; pq.add(new double[]{nd, v}); }
      }
    }
    dist.put(s, d);
    pred.put(s, p);
  }
}

// ===== Router (from java/src/wh/Router.java) =====
/** Picking tours and timed walking schedules on the aisle graph. */
public static final class Router {
  private Router() {}

  public static final class Tour {
    public int[] stops;       // distinct access nodes in visiting order
    public int station;       // index into LayoutData.stations
    public double length;     // metres: depot -> stops -> station -> depot
  }

  /**
   * Nearest-neighbour tour: from home visit every distinct stop, always going to the closest one next
   * (ties: smaller node id), then to the closest packing station (ties: lower index), then back home.
   * Same rule as python whsim.layout.pick_tour, so both give identical lengths.
   */
  public static Tour pickTour(PathGraph g, int home, int[] stops, int[] stations) {
    TreeSet<Integer> rest = new TreeSet<Integer>();
    for (int s : stops) rest.add(s);
    int[] order = new int[rest.size()];
    int cur = home, k = 0;
    double len = 0;
    while (!rest.isEmpty()) {
      double[] d = g.distFrom(cur);
      int best = -1;
      for (int v : rest) if (best < 0 || d[v] < d[best]) best = v;   // ascending ids: first minimum wins ties
      len += d[best];
      order[k++] = best;
      rest.remove(best);
      cur = best;
    }
    double[] d = g.distFrom(cur);
    int st = 0;
    for (int i = 1; i < stations.length; i++) if (d[stations[i]] < d[stations[st]]) st = i;
    Tour t = new Tour();
    t.stops = order;
    t.station = st;
    len += d[stations[st]];                         // two separate additions, as in python pick_tour
    len += g.dist(stations[st], home);
    t.length = len;
    return t;
  }

  /** Piecewise-linear position over time (for animation and for the walk time itself). */
  public static final class Motion {
    public final double[] x, y, t;
    Motion(double[] x, double[] y, double[] t) { this.x = x; this.y = y; this.t = t; }
    public double start() { return t[0]; }
    public double end() { return t[t.length - 1]; }

    /** Position at time q: clamps to the first / last point outside the schedule. */
    public double[] at(double q) {
      if (q <= t[0]) return new double[]{x[0], y[0]};
      int n = t.length;
      if (q >= t[n - 1]) return new double[]{x[n - 1], y[n - 1]};
      int lo = 0, hi = n - 1;                      // t[lo] <= q < t[hi]
      while (hi - lo > 1) { int mid = (lo + hi) >>> 1; if (t[mid] <= q) lo = mid; else hi = mid; }
      double f = t[hi] > t[lo] ? (q - t[lo]) / (t[hi] - t[lo]) : 0;
      return new double[]{x[lo] + f * (x[hi] - x[lo]), y[lo] + f * (y[hi] - y[lo])};
    }
  }

  /**
   * Walk from `from` through `targets` in order at `speed`, dwelling dwell[i] seconds on arriving at
   * targets[i]. Starts at time t0. Duration = path length / speed + sum(dwell).
   */
  public static Motion walk(PathGraph g, LayoutData L, int from, int[] targets, double[] dwell, double speed, double t0) {
    List<double[]> pts = new ArrayList<double[]>();
    pts.add(new double[]{L.nx[from], L.ny[from], t0});
    double t = t0;
    int cur = from;
    for (int i = 0; i < targets.length; i++) {
      int[] p = g.path(cur, targets[i]);
      double[] d = g.distFrom(cur);                 // edge lengths along the path, as in the graph
      double t1 = t;
      for (int k = 1; k < p.length; k++) {
        t = t1 + d[p[k]] / speed;
        pts.add(new double[]{L.nx[p[k]], L.ny[p[k]], t});
      }
      if (dwell[i] > 0) {
        t += dwell[i];
        pts.add(new double[]{L.nx[targets[i]], L.ny[targets[i]], t});
      }
      cur = targets[i];
    }
    double[] x = new double[pts.size()], y = new double[pts.size()], tt = new double[pts.size()];
    for (int i = 0; i < x.length; i++) { x[i] = pts.get(i)[0]; y[i] = pts.get(i)[1]; tt[i] = pts.get(i)[2]; }
    return new Motion(x, y, tt);
  }
}

// ===== ScenarioData (from java/src/wh/ScenarioData.java) =====
/** One day of workload (data/scenarios/day_<seed>.csv) and the SKU master (data/skus.csv). */
public static final class ScenarioData {
  public static final class OrderSpec {
    public int index;          // 0, 1, 2, ... in arrival order
    public String id;
    public double t;
    public String[] skus;
    public int[] qty;
    public int units() { int u = 0; for (int q : qty) u += q; return u; }
  }

  public static final class ReceiptSpec {
    public int index, truckNo;  // truckNo: 0, 1, 2, ... in order of first appearance
    public String truck, sku;
    public double t;
    public int qty;
  }

  public final List<OrderSpec> orders = new ArrayList<OrderSpec>();
  public final List<ReceiptSpec> receipts = new ArrayList<ReceiptSpec>();

  public static ScenarioData load(String path) { return parse(readLines(path), path); }

  public static ScenarioData parse(List<String> lines, String what) {
    if (lines.isEmpty() || !lines.get(0).trim().equals("t_s,type,id,sku,qty"))
      throw new IllegalArgumentException(what + ": header must be t_s,type,id,sku,qty");
    ScenarioData s = new ScenarioData();
    Map<String, List<String[]>> orderLines = new LinkedHashMap<String, List<String[]>>();
    Map<String, Integer> trucks = new LinkedHashMap<String, Integer>();
    double lastT = Double.NEGATIVE_INFINITY;
    for (int ln = 1; ln < lines.size(); ln++) {
      String row = lines.get(ln).trim();
      if (row.isEmpty()) continue;
      String[] f = row.split(",", -1);
      if (f.length != 5) throw new IllegalArgumentException(what + " line " + (ln + 1) + ": expected 5 fields");
      double t = parseNum(f[0], what, ln);
      int q = (int) parseNum(f[4], what, ln);
      if (t < 0 || q < 1 || q != parseNum(f[4], what, ln))
        throw new IllegalArgumentException(what + " line " + (ln + 1) + ": need t_s >= 0 and integer qty >= 1");
      if (t < lastT) throw new IllegalArgumentException(what + " line " + (ln + 1) + ": rows must be sorted by t_s");
      lastT = t;
      if (f[1].equals("ORDER")) {
        f[0] = Double.toString(t);          // store the validated values (e.g. qty "2.0" -> "2")
        f[4] = Integer.toString(q);
        orderLines.computeIfAbsent(f[2], k -> new ArrayList<String[]>()).add(f);
      } else if (f[1].equals("RECEIPT")) {
        ReceiptSpec r = new ReceiptSpec();
        r.index = s.receipts.size();
        r.truck = f[2];
        r.sku = f[3];
        r.t = t;
        r.qty = q;
        Integer no = trucks.get(f[2]);
        if (no == null) { no = trucks.size(); trucks.put(f[2], no); }
        r.truckNo = no;
        s.receipts.add(r);
      } else {
        throw new IllegalArgumentException(what + " line " + (ln + 1) + ": type must be ORDER or RECEIPT");
      }
    }
    for (Map.Entry<String, List<String[]>> e : orderLines.entrySet()) {
      List<String[]> ls = e.getValue();
      OrderSpec o = new OrderSpec();
      o.index = s.orders.size();
      o.id = e.getKey();
      o.t = Double.parseDouble(ls.get(0)[0]);
      o.skus = new String[ls.size()];
      o.qty = new int[ls.size()];
      for (int i = 0; i < ls.size(); i++) {
        if (Double.parseDouble(ls.get(i)[0]) != o.t)
          throw new IllegalArgumentException(what + ": all lines of order " + o.id + " must have the same t_s");
        o.skus[i] = ls.get(i)[3];
        o.qty[i] = Integer.parseInt(ls.get(i)[4]);
        for (int j = 0; j < i; j++)
          if (o.skus[j].equals(o.skus[i])) throw new IllegalArgumentException(what + ": order " + o.id + " lists SKU " + o.skus[i] + " twice");
      }
      s.orders.add(o);
    }
    return s;
  }

  /** sku -> opening stock, in file order. */
  public static Map<String, Integer> loadSkus(String path) {
    List<String> lines = readLines(path);
    if (lines.isEmpty() || !lines.get(0).trim().equals("sku,weight,init_qty"))
      throw new IllegalArgumentException(path + ": header must be sku,weight,init_qty");
    Map<String, Integer> m = new LinkedHashMap<String, Integer>();
    for (int ln = 1; ln < lines.size(); ln++) {
      String row = lines.get(ln).trim();
      if (row.isEmpty()) continue;
      String[] f = row.split(",", -1);
      if (f.length != 3) throw new IllegalArgumentException(path + " line " + (ln + 1) + ": expected 3 fields");
      double v = parseNum(f[2], path, ln);
      if (v < 0 || v != Math.rint(v)) throw new IllegalArgumentException(path + " line " + (ln + 1) + ": init_qty must be an integer >= 0");
      int q = (int) v;
      if (m.put(f[0], q) != null) throw new IllegalArgumentException(path + ": SKU " + f[0] + " listed twice");
    }
    return m;
  }

  private static double parseNum(String v, String what, int ln) {
    try {
      return Double.parseDouble(v.trim());
    } catch (NumberFormatException e) {
      throw new IllegalArgumentException(what + " line " + (ln + 1) + ": not a number: " + v);
    }
  }

  static List<String> readLines(String path) {
    try {
      return java.nio.file.Files.readAllLines(java.nio.file.Paths.get(path), java.nio.charset.StandardCharsets.UTF_8);
    } catch (java.io.IOException e) {
      throw new IllegalArgumentException("cannot read " + path + ": " + e.getMessage());
    }
  }
}

// ===== Inventory (from java/src/wh/Inventory.java) =====
/**
 * SKU stock: OnHand(t) = opening + put away - picked. Reserved = stock promised to released orders
 * that are not picked yet. An order is released only if every line fits in OnHand - Reserved.
 */
public static final class Inventory {
  private final Map<String, int[]> s = new HashMap<String, int[]>();   // sku -> {onHand, reserved}
  private long received, picked;

  public Inventory(Map<String, Integer> opening) {
    for (Map.Entry<String, Integer> e : opening.entrySet()) s.put(e.getKey(), new int[]{e.getValue(), 0});
  }

  public boolean knows(String sku) { return s.containsKey(sku); }

  private int[] rec(String sku) {
    int[] r = s.get(sku);
    if (r == null) throw new IllegalArgumentException("unknown SKU " + sku);
    return r;
  }

  public int onHand(String sku) { return rec(sku)[0]; }
  public int reserved(String sku) { return rec(sku)[1]; }
  public int available(String sku) { int[] r = rec(sku); return r[0] - r[1]; }

  /** Reserves every line of the order, or nothing if any line is short. */
  public boolean tryReserve(ScenarioData.OrderSpec o) {
    for (int i = 0; i < o.skus.length; i++) if (available(o.skus[i]) < o.qty[i]) return false;
    for (int i = 0; i < o.skus.length; i++) rec(o.skus[i])[1] += o.qty[i];
    return true;
  }

  /** The reserved units leave the shelf (end of the pick). */
  public void consume(ScenarioData.OrderSpec o) {
    for (int i = 0; i < o.skus.length; i++) {
      int[] r = rec(o.skus[i]);
      if (r[1] < o.qty[i] || r[0] < o.qty[i])
        throw new IllegalStateException("consume without reservation: order " + o.id + " SKU " + o.skus[i]);
      r[0] -= o.qty[i];
      r[1] -= o.qty[i];
      picked += o.qty[i];
    }
  }

  public void receive(String sku, int qty) {
    if (qty < 1) throw new IllegalArgumentException("receive qty must be >= 1");
    rec(sku)[0] += qty;
    received += qty;
  }

  public long unitsReceived() { return received; }
  public long unitsPicked() { return picked; }

  public long totalOnHand() { long t = 0; for (int[] r : s.values()) t += r[0]; return t; }
  public long totalReserved() { long t = 0; for (int[] r : s.values()) t += r[1]; return t; }
}

// ===== Stats (from java/src/wh/Stats.java) =====
/** Small statistics helpers for the KPI output. */
public static final class Stats {
  private Stats() {}

  /** Time-weighted level (queue length, buffer occupancy): call set() whenever the level changes. */
  public static final class TimeLevel {
    private double value, area, last, max;

    public void set(double t, double v) {
      area += value * (t - last);
      last = t;
      value = v;
      if (v > max) max = v;
    }

    public void add(double t, double dv) { set(t, value + dv); }
    public double value() { return value; }
    public double max() { return max; }
    /** Time average over [0, t]. */
    public double mean(double t) { return t > 0 ? (area + value * (t - last)) / t : 0; }
  }

  public static double mean(List<Double> xs) {
    if (xs.isEmpty()) return Double.NaN;
    double s = 0;
    for (double x : xs) s += x;
    return s / xs.size();
  }

  /** Nearest-rank percentile, p in (0, 1]. */
  public static double percentile(List<Double> xs, double p) {
    if (xs.isEmpty()) return Double.NaN;
    List<Double> c = new ArrayList<Double>(xs);
    Collections.sort(c);
    int k = (int) Math.ceil(p * c.size()) - 1;
    return c.get(Math.max(0, Math.min(c.size() - 1, k)));
  }
}

// ===== Warehouse (from java/src/wh/Warehouse.java) =====
/**
 * Everything the process model needs from the data: layout + graph, run config, workload, inventory,
 * and the decisions (picking tour, packing station, putaway trip) with their times.
 *
 * Common random numbers: every random time is drawn from a stream seeded by (seed, stream, entity index),
 * so the same order gets the same pick / pack times in every layout and in every event order.
 */
public static final class Warehouse {
  public static final int S_PICK = 1, S_PACK = 2, S_RECEIVE = 3, S_PUTAWAY = 4;

  public final LayoutData layout;
  public final PathGraph graph;
  public final RunConfig cfg;
  public final ScenarioData scenario;
  public final Inventory inv;
  public final long seed;

  public Warehouse(LayoutData layout, RunConfig cfg, ScenarioData scenario, Map<String, Integer> opening, long seed) {
    this.layout = layout;
    this.cfg = cfg;
    this.scenario = scenario;
    this.seed = seed;
    this.graph = new PathGraph(layout);
    this.inv = new Inventory(opening);
    check(opening);
  }

  public static Warehouse load(String layoutFile, String configFile, String scenarioFile, String skuFile, long seed) {
    return new Warehouse(LayoutData.load(layoutFile), RunConfig.load(configFile), ScenarioData.load(scenarioFile),
        ScenarioData.loadSkus(skuFile), seed);
  }

  /** Cross-file consistency: every SKU used is in the SKU master and has a slot; every node is reachable. */
  private void check(Map<String, Integer> opening) {
    for (ScenarioData.OrderSpec o : scenario.orders)
      for (String s : o.skus) need(s, opening, "order " + o.id);
    for (ScenarioData.ReceiptSpec r : scenario.receipts) need(r.sku, opening, "receipt of truck " + r.truck);
    double[] d = graph.distFrom(layout.home);
    for (int v = 0; v < layout.n; v++)
      if (Double.isInfinite(d[v])) throw new IllegalArgumentException("layout " + layout.id + ": node " + v + " is not reachable from the depot");
  }

  private void need(String sku, Map<String, Integer> opening, String where) {
    if (!opening.containsKey(sku)) throw new IllegalArgumentException(where + ": SKU " + sku + " is not in the SKU master file");
    if (layout.nodeOfSku(sku) < 0) throw new IllegalArgumentException(where + ": SKU " + sku + " has no slot in layout " + layout.id);
  }

  /**
   * Stream for one (stream, entity) pair. The key is scrambled with the SplitMix64 finaliser: java.util.Random
   * barely mixes its seed, so neighbouring raw seeds would give almost the same first draws.
   */
  public Random rng(int stream, int index) {
    return new Random(mix(mix(mix(seed) ^ stream) ^ index));
  }

  static long mix(long z) {
    z += 0x9E3779B97F4A7C15L;
    z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
    z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
    return z ^ (z >>> 31);
  }

  // ------------------------------------------------------------------ picking
  public static final class PickPlan {
    public double duration, length;   // seconds; metres walked (all trips)
    public int station, stops, trips, orders, units;
    public Router.Motion motion;
  }

  /**
   * Batch (wave) formation, greedy first-fit in release order: the oldest waiting order always goes on the
   * cart; every later order that still fits (cart_units, max_orders) is added. With cart_units = 0 every
   * batch is one order (single-order picking). Returns positions in the waiting list, ascending.
   */
  public int[] formBatch(List<ScenarioData.OrderSpec> waiting) {
    if (waiting.isEmpty()) return new int[0];
    List<Integer> pos = new ArrayList<Integer>();
    pos.add(0);
    int units = waiting.get(0).units();
    for (int i = 1; i < waiting.size() && cfg.cartUnits > 0; i++) {
      if (cfg.maxOrders > 0 && pos.size() >= cfg.maxOrders) break;
      int u = waiting.get(i).units();
      if (units + u <= cfg.cartUnits) { pos.add(i); units += u; }
    }
    int[] out = new int[pos.size()];
    for (int i = 0; i < out.length; i++) out[i] = pos.get(i);
    return out;
  }

  /**
   * The picking tour(s) of a batch, starting at the depot at t0. A batch that fits the cart is ONE trip:
   * nearest-neighbour route over all its distinct slots, then the nearest packing station, then back to the
   * depot. A batch larger than the cart (only possible for a single order bigger than cart_units) is split
   * like the real WMS splits such orders over several waves: its lines are cut, in line order, into chunks of
   * at most cart_units units (one trip each), and a line bigger than the cart takes ceil(qty / cart_units)
   * trips to its slot. Pick time: one draw per order line from that ORDER's own stream, spent on the trip that
   * picks the line (so an order's pick times do not depend on its batch).
   */
  public PickPlan planBatch(List<ScenarioData.OrderSpec> batch, double t0) {
    List<List<int[]>> trips = new ArrayList<List<int[]>>();      // per trip: {node, line number}
    List<Double> lineDwell = new ArrayList<Double>();
    int units = 0;
    for (ScenarioData.OrderSpec o : batch) units += o.units();
    boolean split = cfg.cartUnits > 0 && units > cfg.cartUnits;
    List<int[]> cur = new ArrayList<int[]>();
    int curUnits = 0;
    for (ScenarioData.OrderSpec o : batch) {
      Random r = rng(S_PICK, o.index);
      for (int i = 0; i < o.skus.length; i++) {
        int v = layout.nodeOfSku(o.skus[i]);
        int line = lineDwell.size();
        lineDwell.add(cfg.pickPerLine.sample(r));
        int q = o.qty[i];
        if (!split) { cur.add(new int[]{v, line}); continue; }
        if (q > cfg.cartUnits) {                                 // its own trips: picks on the first one
          if (!cur.isEmpty()) { trips.add(cur); cur = new ArrayList<int[]>(); curUnits = 0; }
          int n = (q + cfg.cartUnits - 1) / cfg.cartUnits;
          for (int k = 0; k < n; k++) {
            List<int[]> t = new ArrayList<int[]>();
            t.add(new int[]{v, k == 0 ? line : -1});
            trips.add(t);
          }
          continue;
        }
        if (curUnits + q > cfg.cartUnits) { trips.add(cur); cur = new ArrayList<int[]>(); curUnits = 0; }
        cur.add(new int[]{v, line});
        curUnits += q;
      }
    }
    if (!cur.isEmpty()) trips.add(cur);
    List<Integer> targets = new ArrayList<Integer>();
    List<Double> dwells = new ArrayList<Double>();
    PickPlan p = new PickPlan();
    p.station = -1;
    for (List<int[]> trip : trips) {
      Map<Integer, Double> dwell = new LinkedHashMap<Integer, Double>();
      int[] nodes = new int[trip.size()];
      for (int i = 0; i < nodes.length; i++) {
        nodes[i] = trip.get(i)[0];
        dwell.merge(nodes[i], trip.get(i)[1] >= 0 ? lineDwell.get(trip.get(i)[1]) : 0.0, Double::sum);
      }
      Router.Tour tour = Router.pickTour(graph, layout.home, nodes, layout.stations);
      for (int v : tour.stops) { targets.add(v); dwells.add(dwell.get(v)); }
      targets.add(layout.stations[tour.station]);
      dwells.add(0.0);
      targets.add(layout.home);
      dwells.add(0.0);
      p.length += tour.length;
      p.stops += tour.stops.length;
      if (p.station < 0) p.station = tour.station;
    }
    int[] tg = new int[targets.size()];
    double[] dw = new double[targets.size()];
    for (int i = 0; i < tg.length; i++) { tg[i] = targets.get(i); dw[i] = dwells.get(i); }
    p.motion = Router.walk(graph, layout, layout.home, tg, dw, cfg.walkSpeed, t0);
    p.duration = p.motion.end() - t0;
    p.trips = trips.size();
    p.orders = batch.size();
    p.units = units;
    return p;
  }

  /**
   * Wave release rule: release a cart now if picking is single-order, or the waiting orders fill a cart,
   * or the oldest one was released at least max_wait_s ago. releasedAt = release time of waiting.get(0).
   */
  public boolean releaseNow(List<ScenarioData.OrderSpec> waiting, double oldestReleasedAt, double now) {
    if (waiting.isEmpty()) return false;
    if (cfg.cartUnits == 0 || now - oldestReleasedAt >= cfg.maxWait) return true;
    int units = 0;
    for (ScenarioData.OrderSpec o : waiting) units += o.units();
    return units >= cfg.cartUnits || (cfg.maxOrders > 0 && waiting.size() >= cfg.maxOrders);
  }

  /** Single-order tour (a batch of one). */
  public PickPlan planPick(ScenarioData.OrderSpec o, double t0) {
    List<ScenarioData.OrderSpec> one = new ArrayList<ScenarioData.OrderSpec>();
    one.add(o);
    return planBatch(one, t0);
  }

  public double packTime(ScenarioData.OrderSpec o) {
    Random r = rng(S_PACK, o.index);
    double t = cfg.packPerOrder.sample(r);
    for (int i = 0; i < o.units(); i++) t += cfg.packPerUnit.sample(r);
    return t;
  }

  // ------------------------------------------------------------------ inbound
  public int dockOf(ScenarioData.ReceiptSpec rc) { return layout.inDocks[rc.truckNo % layout.inDocks.length]; }

  public double receiveTime(ScenarioData.ReceiptSpec rc) { return cfg.receivePerLine.sample(rng(S_RECEIVE, rc.index)); }

  public static final class PutPlan {
    public double duration, length;
    public Router.Motion motion;
  }

  /** Putaway trip of one receipt line: inbound dock -> its slot (handling time there) -> back to the dock. */
  public PutPlan planPutaway(ScenarioData.ReceiptSpec rc, double t0) {
    int dock = dockOf(rc), slot = layout.nodeOfSku(rc.sku);
    double handle = cfg.putawayHandling.sample(rng(S_PUTAWAY, rc.index));
    PutPlan p = new PutPlan();
    p.motion = Router.walk(graph, layout, dock, new int[]{slot, dock}, new double[]{handle, 0}, cfg.putawaySpeed, t0);
    p.duration = p.motion.end() - t0;
    p.length = 2 * graph.dist(dock, slot);
    return p;
  }

  public int recvBufferCapacity() { return layout.recvCells * cfg.recvPerCell; }

  /** Initial picker positions etc. are all the depot. */
  public double[] depotXY() { return new double[]{layout.nx[layout.home], layout.ny[layout.home]}; }

  /** All facility ids of a type, in file order (for drawing labels). */
  public List<LayoutData.Facility> facilities(String type) {
    List<LayoutData.Facility> l = new ArrayList<LayoutData.Facility>();
    for (LayoutData.Facility f : layout.facilities) if (f.type.equals(type)) l.add(f);
    return l;
  }
}

// ===== Kpi (from java/src/wh/Kpi.java) =====
/**
 * Per-order and per-receipt timestamps plus time-weighted levels; turns them into one summary row per
 * run (results/runs.csv) and one row per order (results/orders_<layout>_s<seed>.csv).
 * NaN = event did not happen before the end of the run.
 */
public static final class Kpi {
  private final Warehouse w;
  // orders, by OrderSpec.index
  public final double[] oArr, oRel, oPickStart, oPickEnd, oPacked, oShip, oPickM, oDue;
  public final boolean[] oHeld;
  public final int[] oStation;
  // receipt lines, by ReceiptSpec.index
  public final double[] rArr, rRecv, rPut, rPutM;
  // levels over time
  public final Stats.TimeLevel held = new Stats.TimeLevel(), recvBuffer = new Stats.TimeLevel(), staging = new Stats.TimeLevel(),
      inSystem = new Stats.TimeLevel();
  public int recvOverflows;
  // picking tours (batches)
  public int tours, tourOrders, tourUnits, tourTrips;
  public double tourM, tourTime;

  public Kpi(Warehouse w) {
    this.w = w;
    int n = w.scenario.orders.size(), m = w.scenario.receipts.size();
    oArr = nan(n); oRel = nan(n); oPickStart = nan(n); oPickEnd = nan(n); oPacked = nan(n); oShip = nan(n);
    oPickM = nan(n); oDue = nan(n);
    oHeld = new boolean[n];
    oStation = new int[n];
    Arrays.fill(oStation, -1);
    rArr = nan(m); rRecv = nan(m); rPut = nan(m); rPutM = nan(m);
  }

  private static double[] nan(int n) { double[] a = new double[n]; Arrays.fill(a, Double.NaN); return a; }

  // ---- event hooks (t = current model time)
  public void orderArrived(ScenarioData.OrderSpec o, double t) {
    oArr[o.index] = t;
    oDue[o.index] = w.cfg.dueCutoff(t);
    inSystem.add(t, 1);
  }
  public void orderHeld(ScenarioData.OrderSpec o, double t) { oHeld[o.index] = true; held.add(t, 1); }
  public void orderReleased(ScenarioData.OrderSpec o, double t) {
    oRel[o.index] = t;
    if (oHeld[o.index]) held.add(t, -1);
  }
  public void pickStarted(ScenarioData.OrderSpec o, double t) { oPickStart[o.index] = t; }
  public void pickEnded(ScenarioData.OrderSpec o, double t, Warehouse.PickPlan p) {
    oPickEnd[o.index] = t;
    oPickM[o.index] = p.length / p.orders;      // the order's share of its tour
    oStation[o.index] = p.station;
  }
  /** Once per picking tour, when it ends. */
  public void tourEnded(Warehouse.PickPlan p) {
    tours++;
    tourOrders += p.orders;
    tourUnits += p.units;
    tourTrips += p.trips;
    tourM += p.length;
    tourTime += p.duration;
  }

  public void orderPacked(ScenarioData.OrderSpec o, double t) { oPacked[o.index] = t; staging.add(t, 1); }
  public void orderShipped(ScenarioData.OrderSpec o, double t) {
    oShip[o.index] = t;
    staging.add(t, -1);
    inSystem.add(t, -1);
  }
  public void receiptArrived(ScenarioData.ReceiptSpec r, double t) {
    rArr[r.index] = t;
    recvBuffer.add(t, 1);
    if (recvBuffer.value() > w.recvBufferCapacity()) recvOverflows++;
  }
  public void received(ScenarioData.ReceiptSpec r, double t) { rRecv[r.index] = t; }
  /** The putaway worker takes the line out of the receiving buffer. */
  public void putawayStarted(ScenarioData.ReceiptSpec r, double t) { recvBuffer.add(t, -1); }
  public void putawayEnded(ScenarioData.ReceiptSpec r, double t, Warehouse.PutPlan p) { rPut[r.index] = t; rPutM[r.index] = p.length; }

  // ---- summary
  /** util: utilisation of pickers, packers, receivers, putaway (from the resource pools). */
  public Map<String, Object> summary(double T, String scenarioName, int[] staff, double[] util) {
    List<Double> fulfil = new ArrayList<Double>(), cycle = new ArrayList<Double>(), hold = new ArrayList<Double>(),
        pickM = new ArrayList<Double>();
    int arrived = 0, released = 0, picked = 0, packed = 0, shipped = 0, dueToday = 0, onTime = 0, heldN = 0;
    for (int i = 0; i < oArr.length; i++) {
      if (Double.isNaN(oArr[i])) continue;
      arrived++;
      if (oHeld[i]) heldN++;
      if (!Double.isNaN(oRel[i])) { released++; if (oHeld[i]) hold.add(oRel[i] - oArr[i]); }
      if (!Double.isNaN(oPickEnd[i])) { picked++; pickM.add(oPickM[i]); }
      if (!Double.isNaN(oPacked[i])) { packed++; fulfil.add(oPacked[i] - oArr[i]); }
      if (!Double.isNaN(oShip[i])) { shipped++; cycle.add(oShip[i] - oArr[i]); }
      if (oDue[i] <= T) {                      // due at a cut-off inside the run
        dueToday++;
        if (!Double.isNaN(oPacked[i]) && oPacked[i] <= oDue[i]) onTime++;
      }
    }
    int lines = 0, put = 0;
    double putM = 0;
    for (int j = 0; j < rArr.length; j++) {
      if (Double.isNaN(rArr[j])) continue;
      lines++;
      if (!Double.isNaN(rPut[j])) { put++; putM += rPutM[j]; }
    }
    double pickTotal = 0;
    for (double x : pickM) pickTotal += x;
    Map<String, Object> s = new LinkedHashMap<String, Object>();
    s.put("layout", w.layout.id);
    s.put("scenario", scenarioName);
    s.put("seed", w.seed);
    s.put("pickers", staff[0]); s.put("packers", staff[1]); s.put("receivers", staff[2]); s.put("putaway", staff[3]);
    s.put("horizon_s", T);
    s.put("orders", oArr.length);
    s.put("orders_arrived", arrived); s.put("orders_released", released); s.put("orders_picked", picked);
    s.put("orders_packed", packed); s.put("orders_shipped", shipped); s.put("backlog_end", arrived - shipped);
    s.put("fulfil_mean_s", Stats.mean(fulfil)); s.put("fulfil_p95_s", Stats.percentile(fulfil, 0.95));
    s.put("cycle_mean_s", Stats.mean(cycle)); s.put("cycle_p95_s", Stats.percentile(cycle, 0.95));
    s.put("on_time_pct", dueToday > 0 ? 100.0 * onTime / dueToday : Double.NaN);
    s.put("held_orders", heldN); s.put("hold_mean_s", Stats.mean(hold));
    s.put("pick_m_per_order", Stats.mean(pickM)); s.put("pick_m_total", pickTotal);
    s.put("tours", tours);
    s.put("orders_per_tour", tours > 0 ? (double) tourOrders / tours : Double.NaN);
    s.put("units_per_tour", tours > 0 ? (double) tourUnits / tours : Double.NaN);
    s.put("tour_m_mean", tours > 0 ? tourM / tours : Double.NaN);
    s.put("tour_s_mean", tours > 0 ? tourTime / tours : Double.NaN);
    s.put("cart_units", w.cfg.cartUnits);
    s.put("receipt_lines", lines); s.put("receipt_lines_put", put); s.put("put_m_total", putM);
    s.put("recv_buffer_cap", w.recvBufferCapacity());
    s.put("recv_buffer_max", recvBuffer.max()); s.put("recv_buffer_mean", recvBuffer.mean(T));
    s.put("recv_overflow_events", recvOverflows);
    s.put("held_mean", held.mean(T)); s.put("staging_max", staging.max()); s.put("in_system_mean", inSystem.mean(T));
    s.put("util_pick", util[0]); s.put("util_pack", util[1]); s.put("util_recv", util[2]); s.put("util_put", util[3]);
    s.put("units_received", w.inv.unitsReceived()); s.put("units_picked", w.inv.unitsPicked());
    s.put("units_on_hand_end", w.inv.totalOnHand());
    return s;
  }

  public static String fmt(Object v) {
    if (v instanceof Double) {
      double d = (Double) v;
      if (Double.isNaN(d) || Double.isInfinite(d)) return "";
      return d == Math.rint(d) && Math.abs(d) < 1e15 ? String.valueOf((long) d) : String.format(java.util.Locale.ROOT, "%.4f", d);
    }
    return String.valueOf(v).replace(',', ';');
  }

  /** Appends the summary row to file (writes the header first if the file is new or empty). */
  public static void appendSummary(String file, Map<String, Object> s) {
    try {
      java.io.File f = new java.io.File(file);
      if (f.getParentFile() != null) f.getParentFile().mkdirs();
      boolean header = !f.exists() || f.length() == 0;
      try (java.io.PrintWriter out = new java.io.PrintWriter(new java.io.FileWriter(f, true))) {
        if (header) out.println(String.join(",", s.keySet()));
        StringBuilder b = new StringBuilder();
        for (Object v : s.values()) { if (b.length() > 0) b.append(','); b.append(fmt(v)); }
        out.println(b);
      }
    } catch (java.io.IOException e) {
      throw new IllegalStateException("cannot write " + file + ": " + e.getMessage());
    }
  }

  public void writeOrders(String file) {
    try {
      java.io.File f = new java.io.File(file);
      if (f.getParentFile() != null) f.getParentFile().mkdirs();
      try (java.io.PrintWriter out = new java.io.PrintWriter(new java.io.FileWriter(f, false))) {
        out.println("id,t_arrive,lines,units,held,t_release,t_pick_start,t_pick_end,t_packed,t_shipped,due,on_time,pick_m,station");
        for (ScenarioData.OrderSpec o : w.scenario.orders) {
          int i = o.index;
          if (Double.isNaN(oArr[i])) continue;
          boolean ok = oDue[i] < Double.POSITIVE_INFINITY && !Double.isNaN(oPacked[i]) && oPacked[i] <= oDue[i];
          out.println(String.join(",", o.id, fmt(oArr[i]), String.valueOf(o.skus.length), String.valueOf(o.units()),
              oHeld[i] ? "1" : "0", fmt(oRel[i]), fmt(oPickStart[i]), fmt(oPickEnd[i]), fmt(oPacked[i]), fmt(oShip[i]),
              fmt(oDue[i]), oDue[i] < Double.POSITIVE_INFINITY ? (ok ? "1" : "0") : "", fmt(oPickM[i]),
              oStation[i] < 0 ? "" : "PK" + (oStation[i] + 1)));
        }
      }
    } catch (java.io.IOException e) {
      throw new IllegalStateException("cannot write " + file + ": " + e.getMessage());
    }
  }
}
}
