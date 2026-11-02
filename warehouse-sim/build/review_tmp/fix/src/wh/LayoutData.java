package wh;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** A compiled layout (schema whsim.layout/1) as written by python/whsim/layout.py. */
public final class LayoutData {
  public static final class Facility {
    public String id, type;
    public int r, c, node;
    public double x, y;
  }

  public String id, slotting;
  public double cellM;
  public int rows, cols;
  public String[][] grid;
  // aisle graph
  public int n;
  public double[] nx, ny;
  public int[][] adj;
  public double[][] adjLen;
  // facilities
  public List<Facility> facilities = new ArrayList<Facility>();
  public int home;                 // picker depot node
  public int[] stations;           // packing station nodes, in id order PK1, PK2, ...
  public int[] inDocks;            // inbound dock nodes DI1, DI2, ...
  public int recvCells, stagingCells;
  // slots
  public String[] slotId, slotSku;
  public int[] slotNode, slotR, slotC;
  public Map<String, Integer> slotOfSku = new HashMap<String, Integer>();

  public static LayoutData load(String path) { return parse(Json.read(path)); }

  public static LayoutData parse(Object root) {
    Map<String, Object> m = Json.obj(root, "layout");
    String schema = Json.str(Json.get(m, "schema"), "schema");
    if (!schema.equals("whsim.layout/1")) throw new IllegalArgumentException("layout: unsupported schema " + schema);
    LayoutData L = new LayoutData();
    L.id = Json.str(Json.get(m, "id"), "id");
    L.slotting = Json.str(Json.get(m, "slotting"), "slotting");
    L.cellM = Json.num(Json.get(m, "cell_m"), "cell_m");
    L.rows = Json.integer(Json.get(m, "rows"), "rows");
    L.cols = Json.integer(Json.get(m, "cols"), "cols");
    List<Object> g = Json.arr(Json.get(m, "grid"), "grid");
    if (g.size() != L.rows) throw new IllegalArgumentException("layout: grid has " + g.size() + " rows, rows = " + L.rows);
    L.grid = new String[L.rows][];
    for (int r = 0; r < L.rows; r++) {
      L.grid[r] = Json.str(g.get(r), "grid row").trim().split("\\s+");
      if (L.grid[r].length != L.cols) throw new IllegalArgumentException("layout: grid row " + r + " has " + L.grid[r].length + " cells, cols = " + L.cols);
    }
    List<Object> nodes = Json.arr(Json.get(m, "nodes"), "nodes");
    L.n = nodes.size();
    L.nx = new double[L.n];
    L.ny = new double[L.n];
    for (int i = 0; i < L.n; i++) {
      List<Object> nd = Json.arr(nodes.get(i), "node");
      L.nx[i] = Json.num(nd.get(2), "node x");
      L.ny[i] = Json.num(nd.get(3), "node y");
    }
    List<Object> edges = Json.arr(Json.get(m, "edges"), "edges");
    int[] deg = new int[L.n];
    int[][] e = new int[edges.size()][2];
    double[] w = new double[edges.size()];
    for (int k = 0; k < e.length; k++) {
      List<Object> ed = Json.arr(edges.get(k), "edge");
      e[k][0] = L.node(Json.integer(ed.get(0), "edge"));
      e[k][1] = L.node(Json.integer(ed.get(1), "edge"));
      w[k] = Json.num(ed.get(2), "edge length");
      if (!(w[k] > 0)) throw new IllegalArgumentException("layout: edge " + k + " has length " + w[k]);
      deg[e[k][0]]++;
      deg[e[k][1]]++;
    }
    L.adj = new int[L.n][];
    L.adjLen = new double[L.n][];
    for (int i = 0; i < L.n; i++) { L.adj[i] = new int[deg[i]]; L.adjLen[i] = new double[deg[i]]; deg[i] = 0; }
    for (int k = 0; k < e.length; k++) {
      int a = e[k][0], b = e[k][1];
      L.adj[a][deg[a]] = b; L.adjLen[a][deg[a]++] = w[k];
      L.adj[b][deg[b]] = a; L.adjLen[b][deg[b]++] = w[k];
    }
    List<Integer> pk = new ArrayList<Integer>(), di = new ArrayList<Integer>();
    int homes = 0;
    for (Object fo : Json.arr(Json.get(m, "facilities"), "facilities")) {
      Map<String, Object> fm = Json.obj(fo, "facility");
      Facility f = new Facility();
      f.id = Json.str(Json.get(fm, "id"), "facility id");
      f.type = Json.str(Json.get(fm, "type"), "facility type");
      f.r = Json.integer(Json.get(fm, "r"), "facility r");
      f.c = Json.integer(Json.get(fm, "c"), "facility c");
      f.x = Json.num(Json.get(fm, "x"), "facility x");
      f.y = Json.num(Json.get(fm, "y"), "facility y");
      f.node = L.node(Json.integer(Json.get(fm, "node"), "facility node"));
      L.facilities.add(f);
      if (f.type.equals("H")) { L.home = f.node; homes++; }
      else if (f.type.equals("PK")) pk.add(f.node);
      else if (f.type.equals("DI")) di.add(f.node);
      else if (f.type.equals("R")) L.recvCells++;
      else if (f.type.equals("G")) L.stagingCells++;
    }
    if (homes != 1) throw new IllegalArgumentException("layout: needs exactly one depot H, found " + homes);
    if (pk.isEmpty() || di.isEmpty() || L.recvCells == 0)
      throw new IllegalArgumentException("layout: needs at least one PK, one DI and one R");
    L.stations = toArray(pk);
    L.inDocks = toArray(di);
    List<Object> slots = Json.arr(Json.get(m, "slots"), "slots");
    int ns = slots.size();
    L.slotId = new String[ns]; L.slotSku = new String[ns];
    L.slotNode = new int[ns]; L.slotR = new int[ns]; L.slotC = new int[ns];
    for (int i = 0; i < ns; i++) {
      Map<String, Object> sm = Json.obj(slots.get(i), "slot");
      L.slotId[i] = Json.str(Json.get(sm, "id"), "slot id");
      Object sku = Json.get(sm, "sku");
      L.slotSku[i] = sku == null ? null : Json.str(sku, "slot sku");
      L.slotNode[i] = L.node(Json.integer(Json.get(sm, "node"), "slot node"));
      L.slotR[i] = Json.integer(Json.get(sm, "r"), "slot r");
      L.slotC[i] = Json.integer(Json.get(sm, "c"), "slot c");
      if (L.slotSku[i] != null && !L.slotOfSku.containsKey(L.slotSku[i])) L.slotOfSku.put(L.slotSku[i], i);
    }
    return L;
  }

  private int node(int k) {
    if (k < 0 || k >= n) throw new IllegalArgumentException("layout: node index " + k + " out of range 0.." + (n - 1));
    return k;
  }

  private static int[] toArray(List<Integer> l) {
    int[] a = new int[l.size()];
    for (int i = 0; i < a.length; i++) a[i] = l.get(i);
    return a;
  }

  /** Access node of the slot holding sku (-1 if the layout does not stock it). */
  public int nodeOfSku(String sku) {
    Integer s = slotOfSku.get(sku);
    return s == null ? -1 : slotNode[s];
  }

  public double widthM() { return cols * cellM; }
  public double heightM() { return rows * cellM; }
}
