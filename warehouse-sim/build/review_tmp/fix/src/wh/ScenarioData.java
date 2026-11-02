package wh;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** One day of workload (data/scenarios/day_<seed>.csv) and the SKU master (data/skus.csv). */
public final class ScenarioData {
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
      int q = (int) parseNum(f[2], path, ln);
      if (q < 0) throw new IllegalArgumentException(path + " line " + (ln + 1) + ": init_qty must be >= 0");
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
