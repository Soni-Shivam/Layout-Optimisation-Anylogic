package wh;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

/**
 * Reference simulator: the AnyLogic flowchart re-implemented as a plain event loop on the same core
 * classes (FIFO queues, first free resource). Used to test the whole pipeline without AnyLogic and to
 * give expected KPIs to compare an AnyLogic run against. Not part of the AnyLogic model.
 *
 *   order:   arrive -> reserve stock (else hold) -> picker queue -> pick tour -> packer queue -> pack
 *            -> staging until the next cut-off -> shipped
 *   receipt: arrive -> receiver queue -> receive -> putaway queue -> putaway trip -> stock + retry held
 *
 * Usage: java wh.RefSim LAYOUT.json RUN_CONFIG.json DAY.csv SKUS.csv SEED [RESULTS_DIR]
 */
public final class RefSim {
  private final Warehouse w;
  private final Kpi kpi;
  private final PriorityQueue<double[]> events = new PriorityQueue<double[]>(
      (a, b) -> a[0] != b[0] ? Double.compare(a[0], b[0]) : Double.compare(a[1], b[1]));
  private final List<Runnable> actions = new ArrayList<Runnable>();
  private double now;
  // resources: free units and FIFO queues
  private final int[] free = new int[4], busy = new int[4];
  private final double[] busyArea = new double[4], busyLast = new double[4];
  private final ArrayDeque<Integer> pickQ = new ArrayDeque<Integer>(), packQ = new ArrayDeque<Integer>(),
      recvQ = new ArrayDeque<Integer>(), putQ = new ArrayDeque<Integer>();
  private final List<Integer> held = new ArrayList<Integer>();
  public final int[] staff;

  public RefSim(Warehouse w, int[] staff) {
    this.w = w;
    this.kpi = new Kpi(w);
    this.staff = staff.clone();
    for (int k = 0; k < 4; k++) free[k] = staff[k];
  }

  private void at(double t, Runnable a) {
    events.add(new double[]{t, actions.size()});
    actions.add(a);
  }

  private void seize(int k) { account(k); free[k]--; busy[k]++; }
  private void release(int k) { account(k); free[k]++; busy[k]--; }
  private void account(int k) { busyArea[k] += busy[k] * (now - busyLast[k]); busyLast[k] = now; }

  public Map<String, Object> run(String scenarioName) {
    for (ScenarioData.OrderSpec o : w.scenario.orders) at(o.t, () -> arrive(o));
    for (ScenarioData.ReceiptSpec r : w.scenario.receipts) at(r.t, () -> receiptArrives(r));
    double T = w.cfg.horizon;
    while (!events.isEmpty() && events.peek()[0] <= T) {
      double[] e = events.poll();
      now = e[0];
      actions.get((int) e[1]).run();
    }
    now = T;
    double[] util = new double[4];
    for (int k = 0; k < 4; k++) { account(k); util[k] = busyArea[k] / (staff[k] * T); }
    return kpi.summary(T, scenarioName, staff, util);
  }

  public Kpi kpi() { return kpi; }

  // ---- outbound
  private void arrive(ScenarioData.OrderSpec o) {
    kpi.orderArrived(o, now);
    if (w.inv.tryReserve(o)) { kpi.orderReleased(o, now); pickQ.add(o.index); tryPick(); }
    else { kpi.orderHeld(o, now); held.add(o.index); }
  }

  private void tryPick() {
    while (free[0] > 0 && !pickQ.isEmpty()) {
      ScenarioData.OrderSpec o = w.scenario.orders.get(pickQ.poll());
      seize(0);
      kpi.pickStarted(o, now);
      Warehouse.PickPlan p = w.planPick(o, now);
      at(now + p.duration, () -> {
        w.inv.consume(o);
        kpi.pickEnded(o, now, p);
        release(0);
        packQ.add(o.index);
        tryPack();
        tryPick();
      });
    }
  }

  private void tryPack() {
    while (free[1] > 0 && !packQ.isEmpty()) {
      ScenarioData.OrderSpec o = w.scenario.orders.get(packQ.poll());
      seize(1);
      at(now + w.packTime(o), () -> {
        release(1);
        kpi.orderPacked(o, now);
        double c = w.cfg.nextCutoff(now);
        if (c < Double.POSITIVE_INFINITY) at(c, () -> kpi.orderShipped(o, now));
        tryPack();
      });
    }
  }

  // ---- inbound
  private void receiptArrives(ScenarioData.ReceiptSpec r) {
    kpi.receiptArrived(r, now);
    recvQ.add(r.index);
    tryReceive();
  }

  private void tryReceive() {
    while (free[2] > 0 && !recvQ.isEmpty()) {
      ScenarioData.ReceiptSpec r = w.scenario.receipts.get(recvQ.poll());
      seize(2);
      at(now + w.receiveTime(r), () -> {
        release(2);
        kpi.received(r, now);
        putQ.add(r.index);
        tryPutaway();
        tryReceive();
      });
    }
  }

  private void tryPutaway() {
    while (free[3] > 0 && !putQ.isEmpty()) {
      ScenarioData.ReceiptSpec r = w.scenario.receipts.get(putQ.poll());
      seize(3);
      kpi.putawayStarted(r, now);
      Warehouse.PutPlan p = w.planPutaway(r, now);
      // stock counts when the worker is back at the dock (end of the round trip), as in the AnyLogic model
      at(now + p.duration, () -> {
        w.inv.receive(r.sku, r.qty);
        kpi.putawayEnded(r, now, p);
        release(3);
        retryHeld();
        tryPutaway();
      });
    }
  }

  /** Release every held order (oldest first) whose lines are now all in stock. */
  private void retryHeld() {
    boolean any = false;
    for (Iterator<Integer> it = held.iterator(); it.hasNext(); ) {
      ScenarioData.OrderSpec o = w.scenario.orders.get(it.next());
      if (w.inv.tryReserve(o)) { it.remove(); kpi.orderReleased(o, now); pickQ.add(o.index); any = true; }
    }
    if (any) tryPick();
  }

  public static void main(String[] a) {
    if (a.length < 5) { System.err.println("usage: RefSim LAYOUT RUN_CONFIG DAY SKUS SEED [RESULTS_DIR]"); System.exit(2); }
    Warehouse w = Warehouse.load(a[0], a[1], a[2], a[3], Long.parseLong(a[4]));
    RunConfig c = w.cfg;
    RefSim sim = new RefSim(w, new int[]{c.pickers, c.packers, c.receivers, c.putaway});
    String scen = new java.io.File(a[2]).getName();
    Map<String, Object> s = sim.run(scen);
    for (Map.Entry<String, Object> e : s.entrySet()) System.out.printf("%-22s %s%n", e.getKey(), Kpi.fmt(e.getValue()));
    if (a.length > 5) {
      Kpi.appendSummary(a[5] + "/refsim_runs.csv", s);
      sim.kpi().writeOrders(a[5] + "/refsim_orders_" + w.layout.id + "_s" + w.seed + ".csv");
    }
  }
}
