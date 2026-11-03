package wh;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Per-order and per-receipt timestamps plus time-weighted levels; turns them into one summary row per
 * run (results/runs.csv) and one row per order (results/orders_<layout>_s<seed>.csv).
 * NaN = event did not happen before the end of the run.
 */
public final class Kpi {
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
