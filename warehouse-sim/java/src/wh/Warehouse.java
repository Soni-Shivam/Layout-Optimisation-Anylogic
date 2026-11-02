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
