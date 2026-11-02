package wh;

import java.util.HashMap;
import java.util.Map;

/**
 * SKU stock: OnHand(t) = opening + put away - picked. Reserved = stock promised to released orders
 * that are not picked yet. An order is released only if every line fits in OnHand - Reserved.
 */
public final class Inventory {
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
