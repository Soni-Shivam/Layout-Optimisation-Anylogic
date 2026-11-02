package wh;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

/** Shortest paths on the layout's aisle graph (Dijkstra per source, cached). */
public final class PathGraph {
  private final LayoutData L;
  private final Map<Integer, double[]> dist = new HashMap<Integer, double[]>();
  private final Map<Integer, int[]> pred = new HashMap<Integer, int[]>();

  public PathGraph(LayoutData L) { this.L = L; }

  public double[] distFrom(int s) {
    double[] d = dist.get(s);
    if (d == null) { run(s); d = dist.get(s); }
    return d;
  }

  public double dist(int a, int b) { return distFrom(a)[b]; }

  /** Node sequence a .. b (inclusive) along a shortest path. */
  public int[] path(int a, int b) {
    distFrom(a);
    int[] p = pred.get(a);
    if (a != b && p[b] < 0) throw new IllegalStateException("node " + b + " is not reachable from " + a);
    List<Integer> rev = new ArrayList<Integer>();
    for (int v = b; v != a; v = p[v]) rev.add(v);
    rev.add(a);
    int[] out = new int[rev.size()];
    for (int i = 0; i < out.length; i++) out[i] = rev.get(out.length - 1 - i);
    return out;
  }

  private void run(int s) {
    double[] d = new double[L.n];
    int[] p = new int[L.n];
    Arrays.fill(d, Double.POSITIVE_INFINITY);
    Arrays.fill(p, -1);
    d[s] = 0;
    PriorityQueue<double[]> pq = new PriorityQueue<double[]>((x, y) -> x[0] != y[0] ? Double.compare(x[0], y[0]) : Double.compare(x[1], y[1]));
    pq.add(new double[]{0, s});
    while (!pq.isEmpty()) {
      double[] top = pq.poll();
      int u = (int) top[1];
      if (top[0] > d[u]) continue;
      for (int k = 0; k < L.adj[u].length; k++) {
        int v = L.adj[u][k];
        double nd = d[u] + L.adjLen[u][k];
        if (nd < d[v]) { d[v] = nd; p[v] = u; pq.add(new double[]{nd, v}); }
      }
    }
    dist.put(s, d);
    pred.put(s, p);
  }
}
