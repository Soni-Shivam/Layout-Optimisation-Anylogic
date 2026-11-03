package wh;

import java.util.List;
import java.util.Map;

/** data/config/run_config.json (schema whsim.run/1): horizon, cut-offs, resources, speeds, batching, service times. */
public final class RunConfig {
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
