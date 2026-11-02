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
  public String layoutFile = "data/layouts/I_v_c0_central_abc.json";
  public int layoutIndex = -1;
  public String scenarioFile = "data/scenarios/day_{seed}.csv";
  public String skuFile = "data/skus.csv";
  public String configFile = "data/config/run_config.json";
  public int seed = 1;
  public int nPickers = -1;
  public int nPackers = -1;
  public int nReceivers = -1;
  public int nPutaway = -1;
  public boolean writeOrders = true;
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
  public double ox = 20;
  public double oy = 160;
  public int nArrived = 0;
  public int nPicked = 0;
  public int nPacked = 0;
  public int nShipped = 0;
  public boolean done = false;
  public ShapeTopLevelPresentationGroup presentation;
  public com.anylogic.libraries.processmodeling.Enter<Order> orderIn;
  public com.anylogic.libraries.processmodeling.Delay<Order> orderArrive;
  public com.anylogic.libraries.processmodeling.SelectOutput<Order> stockCheck;
  public com.anylogic.libraries.processmodeling.Wait<Order> holdWait;
  public com.anylogic.libraries.processmodeling.Seize<Order> pickSeize;
  public com.anylogic.libraries.processmodeling.Delay<Order> pickWalk;
  public com.anylogic.libraries.processmodeling.Release<Order> pickRelease;
  public com.anylogic.libraries.processmodeling.Service<Order> pack;
  public com.anylogic.libraries.processmodeling.Delay<Order> staging;
  public com.anylogic.libraries.processmodeling.Sink<Order> shipped;
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
// 4. build the warehouse picture from the layout
drawLayout();
// 5. the workload enters the flowchart; each order / receipt line waits in its arrival delay until its time
// (the spec goes in through the agent's parameter constructor, as in AnyLogic's own examples)
for (ScenarioData.OrderSpec s : wh.scenario.orders) orderIn.take(new Order(s));
for (ScenarioData.ReceiptSpec s : wh.scenario.receipts) receiptIn.take(new Receipt(s));
dayClockIn.take(new DayClock());
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
  double beginPick(Order a) {
if (a.pick == null) {       // plan once (the delay time may be evaluated more than once)
	kpi.pickStarted(a.spec, time());
	a.pick = wh.planPick(a.spec, time());
	if (a.picker != null) a.picker.motion = a.pick.motion;
}
return a.pick.duration;
  }
  void endPick(Order a) {
nPicked++;
wh.inv.consume(a.spec);
kpi.pickEnded(a.spec, time(), a.pick);
if (a.picker != null) a.picker.motion = null;
  }
  double stageTime(Order a) {
if (Double.isNaN(kpi.oPacked[a.spec.index])) {     // once per order
	nPacked++;
	kpi.orderPacked(a.spec, time());
}
double c = wh.cfg.nextCutoff(time());
return c < Double.POSITIVE_INFINITY ? c - time() : 10 * 400000;
  }
  void orderShipped(Order a) {
nShipped++;
kpi.orderShipped(a.spec, time());
  }
  double beginPutaway(Receipt a) {
if (a.put == null) {
	kpi.putawayStarted(a.spec, time());
	a.put = wh.planPutaway(a.spec, time());
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
traceln(String.format("WarehouseSim done: %s seed %d | shipped %s of %s | fulfil mean %.0f s, p95 %.0f s | on time %.1f%% | pick %.1f m/order | util pick %.2f pack %.2f recv %.2f put %.2f",
	wh.layout.id, seed, Kpi.fmt(s.get("orders_shipped")), Kpi.fmt(s.get("orders_arrived")), (Double) s.get("fulfil_mean_s"),
	(Double) s.get("fulfil_p95_s"), (Double) s.get("on_time_pct"), (Double) s.get("pick_m_per_order"), util[0], util[1], util[2], util[3]));
finishSimulation();
  }
  Color cellColor(String t) {
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
  }
  void drawLayout() {
if (presentation == null) return;          // no animation in this experiment
LayoutData L = wh.layout;
px = Math.min(900.0 / L.widthM(), 600.0 / L.heightM());
double c = L.cellM * px;
int k = 0;                                 // insert at the bottom so the worker dots stay on top
for (int r = 0; r < L.rows; r++) {
	for (int q = 0; q < L.cols; q++) {
		ShapeRectangle s = new ShapeRectangle();
		s.setPos(ox + q * c, oy + r * c);
		s.setSize(c, c);
		s.setFillColor(cellColor(L.grid[r][q]));
		s.setLineColor(new Color(255, 255, 255));
		s.setLineWidth(0.5);
		presentation.insert(k++, s);
	}
}
for (LayoutData.Facility f : L.facilities) {
	if (f.type.equals("R") || f.type.equals("G")) continue;
	ShapeText t = new ShapeText();
	t.setPos(ox + f.x * px, oy + f.y * px - 5);
	t.setText(f.id);
	t.setColor(Color.WHITE);
	t.setFont(new Font("SansSerif", Font.BOLD, 8));
	t.setAlignment(ALIGNMENT_CENTER);
	presentation.insert(k++, t);
}
ShapeText title = new ShapeText();
title.setPos(ox, oy + L.rows * c + 6);
title.setText("Layout " + L.id + "  (" + L.cols + " x " + L.rows + " cells of " + L.cellM + " m, " + L.slotId.length
	+ " slots, slotting " + L.slotting + ")   grey = aisle, brown = shelf, green DI = inbound dock, blue DO = outbound dock, "
	+ "yellow = receiving, orange PK = packing, purple = staging, teal H = picker depot");
title.setColor(new Color(69, 90, 100));
title.setFont(new Font("SansSerif", Font.PLAIN, 11));
presentation.insert(k++, title);
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
double off = ((u.k % 3) - 1) * 0.35 * wh.layout.cellM;     // spread workers that share a spot
return new double[]{ox + (p[0] + off) * px, oy + (p[1] + off) * px};
  }
  boolean workerVisible(int i) {
return wh != null && i < workers.size();
  }
  Color workerColor(int i) {
Worker u = workers.get(i);
Color[] busyC = {new Color(229, 57, 53), new Color(255, 111, 0), new Color(253, 216, 53), new Color(30, 136, 229)};
return u.busyNow ? busyC[u.role] : new Color(158, 158, 158);
  }
  String statusText() {
if (wh == null) return "loading ...";
long t = (long) time();
return String.format("%s   seed %d   day file %s%n"
	+ "clock %02d:%02d:%02d (day ends at %s s)%n"
	+ "orders: arrived %d   held now %d   picked %d   packed %d   shipped %d   in system %d%n"
	+ "busy: pickers %d/%d   packers %d/%d   receivers %d/%d   putaway %d/%d%n"
	+ "receiving buffer %d / %d lines   staging %d orders   stock on hand %d units",
	wh.layout.id, seed, scenarioPath, t / 3600, (t / 60) % 60, t % 60, Kpi.fmt(wh.cfg.horizon),
	nArrived, (int) kpi.held.value(), nPicked, nPacked, nShipped, (int) kpi.inSystem.value(),
	pickerPool.busy(), staff[0], packerPool.busy(), staff[1], receiverPool.busy(), staff[2], putawayPool.busy(), staff[3],
	(int) kpi.recvBuffer.value(), wh.recvBufferCapacity(), (int) kpi.staging.value(), wh.inv.totalOnHand());
  }
  // orderArrive.delayTime
  double _snippet1(Order agent) {
return max(0, agent.spec.t - time());
  }
  // stockCheck.condition
  boolean _snippet2(Order agent) {
return admit(agent);
  }
  // pickSeize.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet3(Order agent) {
return pickerPool;
  }
  // pickSeize.onSeizeUnit
  void _snippet4(Order agent, Agent unit) {
agent.picker = (Worker) unit;
  }
  // pickWalk.delayTime
  double _snippet5(Order agent) {
return beginPick(agent);
  }
  // pickWalk.onExit
  void _snippet6(Order agent) {
endPick(agent);
  }
  // pack.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet7(Order agent) {
return packerPool;
  }
  // pack.delayTime
  double _snippet8(Order agent) {
return wh.packTime(agent.spec);
  }
  // staging.delayTime
  double _snippet9(Order agent) {
return stageTime(agent);
  }
  // staging.onExit
  void _snippet10(Order agent) {
orderShipped(agent);
  }
  // receiptArrive.delayTime
  double _snippet11(Receipt agent) {
return max(0, agent.spec.t - time());
  }
  // receiptArrive.onExit
  void _snippet12(Receipt agent) {
kpi.receiptArrived(agent.spec, time());
  }
  // receive.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet13(Receipt agent) {
return receiverPool;
  }
  // receive.delayTime
  double _snippet14(Receipt agent) {
return wh.receiveTime(agent.spec);
  }
  // receive.onExit
  void _snippet15(Receipt agent) {
kpi.received(agent.spec, time());
  }
  // putSeize.resourcePool
  com.anylogic.libraries.processmodeling.ResourcePool _snippet16(Receipt agent) {
return putawayPool;
  }
  // putSeize.onSeizeUnit
  void _snippet17(Receipt agent, Agent unit) {
agent.worker = (Worker) unit;
  }
  // putWalk.delayTime
  double _snippet18(Receipt agent) {
return beginPutaway(agent);
  }
  // putWalk.onExit
  void _snippet19(Receipt agent) {
endPutaway(agent);
  }
  // endOfDay.delayTime
  double _snippet20(DayClock agent) {
return max(0, wh.cfg.horizon - time());
  }
  // endOfDay.onExit
  void _snippet21(DayClock agent) {
finishRun();
  }
  // pickerPool.onNewUnit
  void _snippet22(Worker unit) {
registerWorker(unit, 0);
  }
  // pickerPool.onSeize
  void _snippet23(Worker unit, Agent agent) {
busy[0].add(time(), 1);
unit.busyNow = true;
  }
  // pickerPool.onRelease
  void _snippet24(Worker unit, Agent agent) {
busy[0].add(time(), -1);
unit.busyNow = false;
  }
  // packerPool.onNewUnit
  void _snippet25(Worker unit) {
registerWorker(unit, 1);
  }
  // packerPool.onSeize
  void _snippet26(Worker unit, Agent agent) {
busy[1].add(time(), 1);
unit.busyNow = true;
  }
  // packerPool.onRelease
  void _snippet27(Worker unit, Agent agent) {
busy[1].add(time(), -1);
unit.busyNow = false;
  }
  // receiverPool.onNewUnit
  void _snippet28(Worker unit) {
registerWorker(unit, 2);
  }
  // receiverPool.onSeize
  void _snippet29(Worker unit, Agent agent) {
busy[2].add(time(), 1);
unit.busyNow = true;
  }
  // receiverPool.onRelease
  void _snippet30(Worker unit, Agent agent) {
busy[2].add(time(), -1);
unit.busyNow = false;
  }
  // putawayPool.onNewUnit
  void _snippet31(Worker unit) {
registerWorker(unit, 3);
  }
  // putawayPool.onSeize
  void _snippet32(Worker unit, Agent agent) {
busy[3].add(time(), 1);
unit.busyNow = true;
  }
  // putawayPool.onRelease
  void _snippet33(Worker unit, Agent agent) {
busy[3].add(time(), -1);
unit.busyNow = false;
  }
  void _startup() {
setup();
  }
  // status.TextCode
  Object _snippet34() {
return statusText();
  }
  // workerDot.XCode
  double _snippet35(int index) {
return workerXY(index)[0];
  }
  // workerDot.YCode
  double _snippet36(int index) {
return workerXY(index)[1];
  }
  // workerDot.VisibleCode
  boolean _snippet37(int index) {
return workerVisible(index);
  }
  // workerDot.replication
  int _snippet38() {
return 80;
  }
  // workerDot.FillColorCode
  Color _snippet39(int index) {
return workerColor(index);
  }
  // levels.orders in system
  double _snippet40() {
return kpi == null ? 0 : kpi.inSystem.value();
  }
  // levels.held (no stock)
  double _snippet41() {
return kpi == null ? 0 : kpi.held.value();
  }
  // levels.in staging
  double _snippet42() {
return kpi == null ? 0 : kpi.staging.value();
  }
  // levels.receiving buffer
  double _snippet43() {
return kpi == null ? 0 : kpi.recvBuffer.value();
  }
  void _pvCompareLayouts(Main root) { int runs = 0;
runs++;
traceln("run " + runs + " of 30 done");
 Object t = "runs done: " + runs; }
  void _pvStaffPackers(Main root) { int runs = 0;
runs++;
traceln("run " + runs + " of 20 done");
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
/** data/config/run_config.json (schema whsim.run/1): horizon, cut-offs, resources, speeds, service times. */
public static final class RunConfig {
  public double horizon, promiseLead, walkSpeed, putawaySpeed;
  public double[] cutoffs;
  public int pickers, packers, receivers, putaway, recvPerCell;
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
  public double cellM;
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
    L.cellM = Json.num(Json.get(m, "cell_m"), "cell_m");
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

  public double widthM() { return cols * cellM; }
  public double heightM() { return rows * cellM; }
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
    t.length = len + d[stations[st]] + g.dist(stations[st], home);
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
    public double duration, length;
    public int station, stops;
    public Router.Motion motion;
  }

  /** Single-order picking tour starting at the depot at time t0: walk + one pick time per order line. */
  public PickPlan planPick(ScenarioData.OrderSpec o, double t0) {
    Random r = rng(S_PICK, o.index);
    Map<Integer, Double> dwell = new LinkedHashMap<Integer, Double>();
    int[] nodes = new int[o.skus.length];
    for (int i = 0; i < o.skus.length; i++) {
      nodes[i] = layout.nodeOfSku(o.skus[i]);
      dwell.merge(nodes[i], cfg.pickPerLine.sample(r), Double::sum);   // lines sampled in order-line order
    }
    Router.Tour tour = Router.pickTour(graph, layout.home, nodes, layout.stations);
    int k = tour.stops.length;
    int[] targets = new int[k + 2];
    double[] dw = new double[k + 2];
    for (int i = 0; i < k; i++) { targets[i] = tour.stops[i]; dw[i] = dwell.get(tour.stops[i]); }
    targets[k] = layout.stations[tour.station];
    targets[k + 1] = layout.home;
    PickPlan p = new PickPlan();
    p.motion = Router.walk(graph, layout, layout.home, targets, dw, cfg.walkSpeed, t0);
    p.duration = p.motion.end() - t0;
    p.length = tour.length;
    p.station = tour.station;
    p.stops = k;
    return p;
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
    oPickM[o.index] = p.length;
    oStation[o.index] = p.station;
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
