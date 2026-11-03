import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

import wh.*;

/** Plain-Java tests of the core (no JUnit needed). Run from the project root after the fixtures are built. */
public class CoreTest {
  static int passed, failed;
  static final String DATA = "model/WarehouseSim/data/";

  static void check(boolean ok, String what) {
    if (ok) passed++;
    else { failed++; System.out.println("FAIL: " + what); }
  }

  static void near(double a, double b, double tol, String what) {
    check(Math.abs(a - b) <= tol, what + " (got " + a + ", expected " + b + " +- " + tol + ")");
  }

  static void throwsIAE(Runnable r, String contains, String what) {
    try { r.run(); check(false, what + ": no exception"); }
    catch (IllegalArgumentException e) { check(e.getMessage().contains(contains), what + ": message was " + e.getMessage()); }
  }

  public static void main(String[] a) throws Exception {
    json();
    dists();
    tinyLayout();
    inventory();
    scenario();
    crossCheck();
    randomStreams();
    batching();
    endToEnd();
    System.out.println("CoreTest: " + passed + " passed, " + failed + " failed");
    if (failed > 0) System.exit(1);
  }

  static void json() {
    Object o = Json.parse("{\"a\": [1, 2.5, -3e2], \"b\": {\"c\": \"x\\\"y\\u0041\"}, \"d\": null, \"e\": true}");
    Map<String, Object> m = Json.obj(o, "root");
    check(Json.arr(m.get("a"), "a").equals(Arrays.asList(1.0, 2.5, -300.0)), "json numbers");
    check(Json.obj(m.get("b"), "b").get("c").equals("x\"yA"), "json string escapes");
    check(m.get("d") == null && m.containsKey("d") && m.get("e").equals(Boolean.TRUE), "json null / true");
    throwsIAE(() -> Json.parse("{\"a\": 1,}"), "expected a key", "json trailing comma");
    throwsIAE(() -> Json.parse("[1 2]"), "expected ','", "json missing comma");
    throwsIAE(() -> Json.integer(2.5, "x"), "expected an integer", "json integer check");
    throwsIAE(() -> Json.parse("\"\\u+041\""), "bad \\u escape", "json \\u with a sign");
    throwsIAE(() -> Json.parse("\"\\u12\""), "bad \\u escape", "json short \\u");
  }

  static void dists() {
    String[] specs = {
        "{\"dist\":\"const\",\"value\":3}", "{\"dist\":\"uniform\",\"min\":2,\"max\":6}",
        "{\"dist\":\"triangular\",\"min\":1,\"mode\":2,\"max\":6}", "{\"dist\":\"exponential\",\"mean\":5}",
        "{\"dist\":\"normal\",\"mean\":10,\"sd\":2}", "{\"dist\":\"lognormal\",\"mean\":12,\"sd\":5}",
        "{\"dist\":\"gamma\",\"shape\":4,\"scale\":12}", "{\"dist\":\"gamma\",\"shape\":0.5,\"scale\":2}",
        "{\"dist\":\"weibull\",\"shape\":2,\"scale\":10}", "{\"dist\":\"empirical\",\"values\":[1,2,3,10]}"};
    for (String s : specs) {
      Dist d = Dist.of(Json.parse(s), "test");
      Random r = new Random(42);
      int n = 200000;
      double sum = 0, min = Double.MAX_VALUE;
      for (int i = 0; i < n; i++) { double x = d.sample(r); sum += x; min = Math.min(min, x); }
      near(sum / n, d.mean(), 0.02 * d.mean() + 1e-9, "sample mean of " + s);
      check(min >= 0, "non-negative samples of " + s);
    }
    // truncated normal far in the tail: mean of N(0, 10) given x >= 30 is 32.833, and no mass sits at 30
    Dist tn = Dist.of(Json.parse("{\"dist\":\"normal\",\"mean\":0,\"sd\":10,\"min\":30}"), "tn");
    Random rt = new Random(3);
    double st = 0;
    int atMin = 0;
    for (int i = 0; i < 200000; i++) { double x = tn.sample(rt); st += x; if (x == 30) atMin++; }
    near(st / 200000, 32.833, 0.05, "truncated normal tail mean");
    check(atMin == 0, "truncated normal has no point mass at min");
    // the lognormal sd is of the variable itself
    Dist ln = Dist.of(Json.parse(specs[5]), "ln");
    Random r = new Random(7);
    double s1 = 0, s2 = 0;
    int n = 200000;
    for (int i = 0; i < n; i++) { double x = ln.sample(r); s1 += x; s2 += x * x; }
    near(Math.sqrt(s2 / n - (s1 / n) * (s1 / n)), 5.0, 0.15, "lognormal sd");
    throwsIAE(() -> Dist.of(Json.parse("{\"dist\":\"gamma\",\"shape\":-1,\"scale\":2}"), "times.x"), "shape > 0", "bad gamma");
    throwsIAE(() -> Dist.of(Json.parse("{\"dist\":\"beta\"}"), "times.x"), "unknown distribution", "unknown dist");
    throwsIAE(() -> Dist.of(Json.parse("{\"dist\":\"uniform\",\"min\":1}"), "times.x"), "missing key", "missing parameter");
  }

  static void tinyLayout() {
    LayoutData L = LayoutData.load("build/fixtures/tiny_layout.json");
    PathGraph g = new PathGraph(L);
    int home = L.home, pk = L.stations[0];
    // same hand calculation as python tests/test_layout.py::test_tour_length_by_hand
    int s22 = -1, s34 = -1;
    for (int i = 0; i < L.slotId.length; i++) {
      if (L.slotR[i] == 2 && L.slotC[i] == 2) s22 = L.slotNode[i];
      if (L.slotR[i] == 3 && L.slotC[i] == 4) s34 = L.slotNode[i];
    }
    Router.Tour t = Router.pickTour(g, home, new int[]{s22, s34}, L.stations);
    near(t.length, 28.0, 1e-12, "tiny tour length");
    check(t.stops.length == 2 && t.stops[0] == s34 && t.stops[1] == s22, "tiny tour order");
    // duplicate stops are visited once
    Router.Tour t2 = Router.pickTour(g, home, new int[]{s22, s22}, L.stations);
    check(t2.stops.length == 1, "duplicate stop visited once");
    // walk time = length / speed + dwell, and the motion passes through the nodes
    Router.Motion mo = Router.walk(g, L, home, new int[]{s34, s22, pk, home}, new double[]{5, 7, 0, 0}, 2.0, 100);
    near(mo.end() - mo.start(), 28.0 / 2.0 + 12, 1e-9, "walk duration");
    double[] p0 = mo.at(0), pEnd = mo.at(1e9);
    check(p0[0] == L.nx[home] && p0[1] == L.ny[home] && pEnd[0] == L.nx[home], "motion clamps at ends");
    double[] pd = mo.at(100 + 4.0 / 2.0 + 2.5);       // dwelling at the first stop
    check(pd[0] == L.nx[s34] && pd[1] == L.ny[s34], "motion waits at a stop while picking");
    // path endpoints and reachability
    int[] p = g.path(home, s22);
    check(p[0] == home && p[p.length - 1] == s22 && p.length == 1 + (int) Math.round(g.dist(home, s22) / L.cellW), "path nodes");
  }

  static void inventory() {
    Map<String, Integer> open = new LinkedHashMap<String, Integer>();
    open.put("A", 2); open.put("B", 0);
    Inventory inv = new Inventory(open);
    ScenarioData.OrderSpec o = new ScenarioData.OrderSpec();
    o.id = "o"; o.skus = new String[]{"A", "B"}; o.qty = new int[]{1, 1};
    check(!inv.tryReserve(o) && inv.reserved("A") == 0, "all-or-nothing reservation");
    inv.receive("B", 1);
    check(inv.tryReserve(o) && inv.available("A") == 1 && inv.available("B") == 0, "reservation after receipt");
    ScenarioData.OrderSpec o2 = new ScenarioData.OrderSpec();
    o2.id = "o2"; o2.skus = new String[]{"B"}; o2.qty = new int[]{1};
    check(!inv.tryReserve(o2), "reserved stock is not available to the next order");
    inv.consume(o);
    check(inv.onHand("A") == 1 && inv.onHand("B") == 0 && inv.unitsPicked() == 2, "consume");
    try { inv.consume(o); check(false, "double consume must fail"); } catch (IllegalStateException e) { check(true, ""); }
  }

  static void scenario() {
    ScenarioData s = ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty", "1.5,ORDER,O1,A,2", "1.5,ORDER,O1,B,1",
        "2,RECEIPT,T1,A,5", "3,ORDER,O2,A,1", "4,RECEIPT,T2,B,1", "4,RECEIPT,T1,B,2"), "test");
    check(s.orders.size() == 2 && s.orders.get(0).skus.length == 2 && s.orders.get(0).units() == 3, "orders grouped");
    check(s.receipts.size() == 3 && s.receipts.get(1).truckNo == 1 && s.receipts.get(2).truckNo == 0, "truck numbers");
    throwsIAE(() -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty", "2,ORDER,O1,A,1", "1,ORDER,O2,A,1"), "x"), "sorted", "unsorted rows");
    throwsIAE(() -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty", "1,ORDER,O1,A,1", "1,ORDER,O1,A,1"), "x"), "twice", "duplicate sku");
    throwsIAE(() -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty", "1,ORDER,O1,A,0"), "x"), "qty >= 1", "zero qty");
    ScenarioData f = ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty", "1.0,ORDER,O1,A,2.0", "1,ORDER,O1,B, 3"), "float");
    check(f.orders.size() == 1 && f.orders.get(0).qty[0] == 2 && f.orders.get(0).qty[1] == 3, "float-written qty accepted");
    throwsIAE(() -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty", "1,ORDER,O1,A,2.5"), "x"), "integer qty", "fractional qty");
  }

  /** Per-entity streams must be independent: one draw per entity behaves like an i.i.d. sample. */
  static void randomStreams() {
    Map<String, Integer> open = new LinkedHashMap<String, Integer>();
    for (String s : new String[]{"X", "Y", "Z"}) open.put(s, 0);
    Warehouse w = new Warehouse(LayoutData.load("build/fixtures/tiny_layout.json"),
        RunConfig.load(DATA + "config/run_config.json"), new ScenarioData(), open, 1);
    int n = 20000;
    for (int stream = 1; stream <= 4; stream++) {
      double[] u = new double[n];
      double sum = 0, sq = 0;
      for (int i = 0; i < n; i++) { u[i] = w.rng(stream, i).nextDouble(); sum += u[i]; sq += u[i] * u[i]; }
      double m = sum / n, v = sq / n - m * m, ac = 0;
      for (int i = 1; i < n; i++) ac += (u[i] - m) * (u[i - 1] - m);
      ac /= (n - 1) * v;
      near(m, 0.5, 0.01, "stream " + stream + ": mean of first draws");
      near(v, 1.0 / 12, 0.003, "stream " + stream + ": variance of first draws");
      near(ac, 0, 0.03, "stream " + stream + ": lag-1 autocorrelation across entities");
    }
    double c = 0;
    for (int i = 0; i < n; i++) c += (w.rng(1, i).nextDouble() - 0.5) * (w.rng(2, i).nextDouble() - 0.5);
    near(12 * c / n, 0, 0.03, "pick and pack streams of the same entity are uncorrelated");
  }

  static ScenarioData.OrderSpec order(int index, String[] skus, int[] qty) {
    ScenarioData.OrderSpec o = new ScenarioData.OrderSpec();
    o.index = index; o.id = "o" + index; o.skus = skus; o.qty = qty;
    return o;
  }

  /** Cart formation, multi-trip tours and the wave release rule. */
  static void batching() {
    Map<String, Integer> open = new LinkedHashMap<String, Integer>();
    for (String s : new String[]{"X", "Y", "Z"}) open.put(s, 100);
    RunConfig c = RunConfig.load(DATA + "config/run_config.json");
    c.cartUnits = 10; c.maxOrders = 0; c.maxWait = 600;
    Warehouse w = new Warehouse(LayoutData.load("build/fixtures/tiny_layout.json"), c, new ScenarioData(), open, 1);
    List<ScenarioData.OrderSpec> wait = Arrays.asList(order(0, new String[]{"X"}, new int[]{6}),
        order(1, new String[]{"Y"}, new int[]{5}), order(2, new String[]{"Z"}, new int[]{4}), order(3, new String[]{"Y"}, new int[]{1}));
    check(Arrays.equals(w.formBatch(wait), new int[]{0, 2}), "first fit: 6 + 4 = 10 units, the 5-unit order waits");
    c.maxOrders = 1;
    check(Arrays.equals(w.formBatch(wait), new int[]{0}), "max_orders = 1");
    c.maxOrders = 0; c.cartUnits = 0;
    check(Arrays.equals(w.formBatch(wait), new int[]{0}), "cart_units = 0 is single-order picking");
    c.cartUnits = 10;
    // one tour for two orders: the union of their slots, picks timed per order (CRN)
    Warehouse.PickPlan both = w.planBatch(Arrays.asList(wait.get(0), wait.get(2)), 0);
    Warehouse.PickPlan a = w.planPick(wait.get(0), 0), b = w.planPick(wait.get(2), 0);
    check(both.orders == 2 && both.units == 10 && both.trips == 1, "batch counts");
    check(both.length <= a.length + b.length, "one shared tour is not longer than two separate tours");
    double dwellBoth = both.duration - both.length / c.walkSpeed, dwellA = a.duration - a.length / c.walkSpeed,
        dwellB = b.duration - b.length / c.walkSpeed;
    near(dwellBoth, dwellA + dwellB, 1e-6, "pick times of an order do not depend on its batch");
    // an order bigger than the cart needs several trips over the same route
    Warehouse.PickPlan big = w.planPick(order(4, new String[]{"X"}, new int[]{25}), 0);
    Warehouse.PickPlan small = w.planPick(order(4, new String[]{"X"}, new int[]{5}), 0);
    check(big.trips == 3, "25 units on a 10-unit cart = 3 trips");
    near(big.length, 3 * small.length, 1e-9, "trip distance");
    near(big.duration - small.duration, 2 * small.length / c.walkSpeed, 1e-6, "extra trips add walking only");
    // an oversize order with several SKUs is split into cart-sized chunks: each trip visits only its own slots
    ScenarioData.OrderSpec multi = order(5, new String[]{"X", "Y", "Z"}, new int[]{6, 6, 6});
    Warehouse.PickPlan mp = w.planPick(multi, 0);
    double sum = w.planPick(order(5, new String[]{"X"}, new int[]{6}), 0).length
        + w.planPick(order(5, new String[]{"Y"}, new int[]{6}), 0).length + w.planPick(order(5, new String[]{"Z"}, new int[]{6}), 0).length;
    check(mp.trips == 3, "18 units in lines of 6 on a 10-unit cart = 3 one-line trips");
    near(mp.length, sum, 1e-9, "split trips: sum of the chunk tours, not trips x the whole tour");
    double dwellM = mp.duration - mp.length / c.walkSpeed;
    Warehouse.PickPlan whole = w.planPick(order(5, new String[]{"X", "Y", "Z"}, new int[]{3, 3, 3}), 0);
    near(dwellM, whole.duration - whole.length / c.walkSpeed, 1e-6, "each line is picked once, whatever the split");
    // wave release: wait for a full cart or max_wait_s
    List<ScenarioData.OrderSpec> two = Arrays.asList(wait.get(1), wait.get(3));
    check(!w.releaseNow(two, 0, 100), "6 of 10 units after 100 s: keep waiting");
    check(w.releaseNow(two, 0, 600), "oldest waited max_wait_s: release");
    check(w.releaseNow(wait, 0, 1), "a full cart is waiting: release");
    c.cartUnits = 0;
    check(w.releaseNow(two, 0, 0), "single-order picking releases at once");
  }

  /** Java Router == Python pick_tour on every order of day_1, on every candidate layout. */
  static void crossCheck() throws Exception {
    ScenarioData day = ScenarioData.load(DATA + "scenarios/day_1.csv");
    Map<String, ScenarioData.OrderSpec> byId = new LinkedHashMap<String, ScenarioData.OrderSpec>();
    for (ScenarioData.OrderSpec o : day.orders) byId.put(o.id, o);
    int layouts = 0, rows = 0, bad = 0;
    for (String name : Files.readAllLines(Paths.get(DATA + "layouts/index.txt"))) {
      if (name.trim().isEmpty()) continue;
      LayoutData L = LayoutData.load(DATA + "layouts/" + name.trim());
      PathGraph g = new PathGraph(L);
      List<String> ref = Files.readAllLines(Paths.get("build/fixtures/crosscheck_" + L.id + ".csv"));
      for (String r : ref.subList(1, ref.size())) {
        String[] f = r.split(",");
        ScenarioData.OrderSpec o = byId.get(f[0]);
        int[] nodes = new int[o.skus.length];
        for (int i = 0; i < nodes.length; i++) nodes[i] = L.nodeOfSku(o.skus[i]);
        Router.Tour t = Router.pickTour(g, L.home, nodes, L.stations);
        StringBuilder stops = new StringBuilder();
        for (int v : t.stops) { if (stops.length() > 0) stops.append(' '); stops.append(v); }
        if (t.length != Double.parseDouble(f[1]) || t.station != Integer.parseInt(f[2]) || !stops.toString().equals(f[3])) bad++;
        rows++;
      }
      layouts++;
    }
    check(layouts >= 1 && rows > 0 && bad == 0, "Java vs Python tours: " + bad + " of " + rows + " differ on " + layouts + " layouts");
  }

  /** Full day on the reference simulator: flow conservation and sane KPIs on every candidate layout. */
  static void endToEnd() throws Exception {
    for (String name : Files.readAllLines(Paths.get(DATA + "layouts/index.txt"))) {
      if (name.trim().isEmpty()) continue;
      Warehouse w = Warehouse.load(DATA + "layouts/" + name.trim(), DATA + "config/run_config.json",
          DATA + "scenarios/day_1.csv", DATA + "skus.csv", 1);
      Map<String, Integer> open = ScenarioData.loadSkus(DATA + "skus.csv");
      long opening = 0;
      for (int q : open.values()) opening += q;
      RunConfig c = w.cfg;
      RefSim sim = new RefSim(w, new int[]{c.pickers, c.packers, c.receivers, c.putaway});
      Map<String, Object> s = sim.run("day_1");
      String id = w.layout.id;
      long onHand = (Long) s.get("units_on_hand_end"), rec = (Long) s.get("units_received"), pick = (Long) s.get("units_picked");
      check(onHand == opening + rec - pick, id + ": stock balance");
      Kpi k = sim.kpi();
      long pickedUnits = 0;
      for (ScenarioData.OrderSpec o : w.scenario.orders) if (!Double.isNaN(k.oPickEnd[o.index])) pickedUnits += o.units();
      check(pickedUnits == pick, id + ": units picked = units of picked orders");
      check(k.tourOrders == (Integer) s.get("orders_picked") && k.tours > 0, id + ": every picked order was on exactly one cart");
      int arrived = (Integer) s.get("orders_arrived"), shipped = (Integer) s.get("orders_shipped");
      check(arrived == w.scenario.orders.size(), id + ": every order arrives");
      check(shipped + (Integer) s.get("backlog_end") == arrived && shipped > 0.9 * arrived, id + ": most orders ship (" + shipped + "/" + arrived + ")");
      for (ScenarioData.OrderSpec o : w.scenario.orders) {
        int i = o.index;
        if (!Double.isNaN(k.oShip[i])) {
          check(k.oArr[i] <= k.oRel[i] && k.oRel[i] <= k.oPickStart[i] && k.oPickStart[i] < k.oPickEnd[i]
              && k.oPickEnd[i] < k.oPacked[i] && k.oPacked[i] <= k.oShip[i], id + ": timestamps in order for " + o.id);
          boolean atCutoff = false;
          for (double cut : c.cutoffs) atCutoff |= k.oShip[i] == cut;
          check(atCutoff && k.oShip[i] == c.nextCutoff(k.oPacked[i]), id + ": " + o.id + " ships at the first cut-off after packing");
        }
      }
      double util = (Double) s.get("util_pick");
      check(util > 0 && util < 1, id + ": picker utilisation in (0, 1): " + util);
      check((Integer) s.get("receipt_lines_put") == w.scenario.receipts.size(), id + ": all receipts put away");
      System.out.printf("  %-26s shipped %d/%d  held %s  pick m/order %.1f  fulfil mean %.0f s  on-time %.1f%%  util pick %.2f pack %.2f%n",
          id, shipped, arrived, s.get("held_orders"), (Double) s.get("pick_m_per_order"), (Double) s.get("fulfil_mean_s"),
          (Double) s.get("on_time_pct"), util, (Double) s.get("util_pack"));
    }
  }
}
