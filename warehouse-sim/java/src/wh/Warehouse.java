package wh;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * Everything the process model needs from the data: layout + graph, run config, workload, inventory,
 * and the decisions (picking tour, packing station, putaway trip) with their times.
 *
 * Common random numbers: every random time is drawn from a stream seeded by (seed, stream, entity index),
 * so the same order gets the same pick / pack times in every layout and in every event order.
 */
public final class Warehouse {
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
