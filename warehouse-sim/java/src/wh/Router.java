package wh;

import java.util.ArrayList;
import java.util.List;
import java.util.TreeSet;

/** Picking tours and timed walking schedules on the aisle graph. */
public final class Router {
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
    len += d[stations[st]];                         // two separate additions, as in python pick_tour
    len += g.dist(stations[st], home);
    t.length = len;
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
