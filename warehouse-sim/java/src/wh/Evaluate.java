package wh;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Batch evaluator for the optimizer (one JVM for many layouts). Not part of the AnyLogic model.
 *
 *   static LAYOUTS WAVES OUT
 *       For every layout file listed in LAYOUTS (one path per line): the picking-tour length of every
 *       historical wave in WAVES (csv with a 'skus' column, space-separated SKU ids), using the same
 *       nearest-neighbour tour as the simulation. Writes layout, waves, mean_tour_m, p95_tour_m.
 *
 *   des LAYOUTS CONFIG SCENARIO_PATTERN SKUS SEED_FROM SEED_TO OUT
 *       Full reference-simulation days (RefSim) of every layout x seed; SCENARIO_PATTERN contains {seed}.
 *       Appends one KPI row per run to OUT (same columns as the AnyLogic runs.csv).
 */
public final class Evaluate {
  private Evaluate() {}

  public static void main(String[] a) throws Exception {
    if (a.length == 4 && a[0].equals("static")) staticTours(a[1], a[2], a[3]);
    else if (a.length == 8 && a[0].equals("des")) des(a[1], a[2], a[3], a[4], Integer.parseInt(a[5]), Integer.parseInt(a[6]), a[7]);
    else {
      System.err.println("usage: Evaluate static LAYOUTS WAVES OUT | des LAYOUTS CONFIG SCENARIO_PATTERN SKUS SEED_FROM SEED_TO OUT");
      System.exit(2);
    }
  }

  static List<String> lines(String path) {
    List<String> out = new ArrayList<String>();
    for (String s : ScenarioData.readLines(path)) if (!s.trim().isEmpty()) out.add(s.trim());
    return out;
  }

  /** SKU lists of the historical waves (column 'skus'). */
  static List<String[]> waves(String path) {
    List<String> ls = ScenarioData.readLines(path);
    String[] head = ls.get(0).split(",", -1);
    int col = -1;
    for (int i = 0; i < head.length; i++) if (head[i].trim().equals("skus")) col = i;
    if (col < 0) throw new IllegalArgumentException(path + ": no 'skus' column");
    List<String[]> out = new ArrayList<String[]>();
    for (int i = 1; i < ls.size(); i++) {
      if (ls.get(i).trim().isEmpty()) continue;
      String[] f = ls.get(i).split(",", -1);
      out.add(f[col].trim().split("\\s+"));
    }
    return out;
  }

  static void staticTours(String layoutList, String waveFile, String out) throws Exception {
    List<String[]> ws = waves(waveFile);
    try (java.io.PrintWriter w = new java.io.PrintWriter(new java.io.FileWriter(out))) {
      w.println("layout_file,layout,waves,mean_tour_m,p95_tour_m");
      for (String file : lines(layoutList)) {
        LayoutData L = LayoutData.load(file);
        PathGraph g = new PathGraph(L);
        List<Double> len = new ArrayList<Double>();
        for (String[] skus : ws) {
          int[] nodes = new int[skus.length];
          for (int i = 0; i < skus.length; i++) {
            nodes[i] = L.nodeOfSku(skus[i]);
            if (nodes[i] < 0) throw new IllegalArgumentException(file + ": SKU " + skus[i] + " has no slot");
          }
          len.add(Router.pickTour(g, L.home, nodes, L.stations).length);
        }
        w.printf(java.util.Locale.ROOT, "%s,%s,%d,%.4f,%.4f%n", file, L.id, len.size(), Stats.mean(len), Stats.percentile(len, 0.95));
      }
    }
  }

  static void des(String layoutList, String config, String pattern, String skus, int s0, int s1, String out) {
    for (String file : lines(layoutList)) {
      for (int seed = s0; seed <= s1; seed++) {
        String day = pattern.replace("{seed}", String.valueOf(seed));
        Warehouse w = Warehouse.load(file, config, day, skus, seed);
        RunConfig c = w.cfg;
        RefSim sim = new RefSim(w, new int[]{c.pickers, c.packers, c.receivers, c.putaway});
        Map<String, Object> s = sim.run(new java.io.File(day).getName());
        Kpi.appendSummary(out, s);
      }
    }
  }
}
