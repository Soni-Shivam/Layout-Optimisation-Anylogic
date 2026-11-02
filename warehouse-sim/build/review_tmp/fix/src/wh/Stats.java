package wh;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Small statistics helpers for the KPI output. */
public final class Stats {
  private Stats() {}

  /** Time-weighted level (queue length, buffer occupancy): call set() whenever the level changes. */
  public static final class TimeLevel {
    private double value, area, last, max;

    public void set(double t, double v) {
      area += value * (t - last);
      last = t;
      value = v;
      if (v > max) max = v;
    }

    public void add(double t, double dv) { set(t, value + dv); }
    public double value() { return value; }
    public double max() { return max; }
    /** Time average over [0, t]. */
    public double mean(double t) { return t > 0 ? (area + value * (t - last)) / t : 0; }
  }

  public static double mean(List<Double> xs) {
    if (xs.isEmpty()) return Double.NaN;
    double s = 0;
    for (double x : xs) s += x;
    return s / xs.size();
  }

  /** Nearest-rank percentile, p in (0, 1]. */
  public static double percentile(List<Double> xs, double p) {
    if (xs.isEmpty()) return Double.NaN;
    List<Double> c = new ArrayList<Double>(xs);
    Collections.sort(c);
    int k = (int) Math.ceil(p * c.size()) - 1;
    return c.get(Math.max(0, Math.min(c.size() - 1, k)));
  }
}
