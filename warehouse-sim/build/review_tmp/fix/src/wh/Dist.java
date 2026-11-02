package wh;

import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * A service-time distribution read from the run config, e.g. {"dist": "gamma", "shape": 4, "scale": 12}.
 *
 *   const(value)  uniform(min, max)  triangular(min, mode, max)  exponential(mean)
 *   normal(mean, sd, min = 0; truncated)  lognormal(mean, sd; of the variable itself)
 *   gamma(shape, scale)  weibull(shape, scale)  empirical(values: resampled uniformly)
 *
 * Samples are never negative. The random stream is passed in, so the caller controls common random numbers.
 */
public final class Dist {
  public final String kind;
  private final double a, b, c;
  private final double[] values;

  private Dist(String kind, double a, double b, double c, double[] values) {
    this.kind = kind; this.a = a; this.b = b; this.c = c; this.values = values;
  }

  public static Dist constant(double v) { return new Dist("const", v, 0, 0, null); }

  public static Dist of(Object o, String what) {
    Map<String, Object> m = Json.obj(o, what);
    String k = Json.str(Json.get(m, "dist"), what + ".dist");
    try {
      switch (k) {
        case "const": return check(new Dist(k, p(m, "value"), 0, 0, null), p(m, "value") >= 0, what, "value >= 0");
        case "uniform": return check(new Dist(k, p(m, "min"), p(m, "max"), 0, null), 0 <= p(m, "min") && p(m, "min") <= p(m, "max"), what, "0 <= min <= max");
        case "triangular": {
          double lo = p(m, "min"), mo = p(m, "mode"), hi = p(m, "max");
          return check(new Dist(k, lo, mo, hi, null), 0 <= lo && lo <= mo && mo <= hi && lo < hi, what, "0 <= min <= mode <= max, min < max");
        }
        case "exponential": return check(new Dist(k, p(m, "mean"), 0, 0, null), p(m, "mean") > 0, what, "mean > 0");
        case "normal": {
          double lo = m.containsKey("min") ? p(m, "min") : 0.0;
          return check(new Dist(k, p(m, "mean"), p(m, "sd"), lo, null), p(m, "sd") >= 0 && lo >= 0, what, "sd >= 0, min >= 0");
        }
        case "lognormal": return check(new Dist(k, p(m, "mean"), p(m, "sd"), 0, null), p(m, "mean") > 0 && p(m, "sd") >= 0, what, "mean > 0, sd >= 0");
        case "gamma": return check(new Dist(k, p(m, "shape"), p(m, "scale"), 0, null), p(m, "shape") > 0 && p(m, "scale") > 0, what, "shape > 0, scale > 0");
        case "weibull": return check(new Dist(k, p(m, "shape"), p(m, "scale"), 0, null), p(m, "shape") > 0 && p(m, "scale") > 0, what, "shape > 0, scale > 0");
        case "empirical": {
          List<Object> l = Json.arr(Json.get(m, "values"), what + ".values");
          if (l.isEmpty()) throw new IllegalArgumentException(what + ": empirical needs at least one value");
          double[] v = new double[l.size()];
          for (int i = 0; i < v.length; i++) {
            v[i] = Json.num(l.get(i), what + ".values");
            if (v[i] < 0) throw new IllegalArgumentException(what + ": empirical values must be >= 0");
          }
          return new Dist(k, 0, 0, 0, v);
        }
        default: throw new IllegalArgumentException(what + ": unknown distribution \"" + k + "\"");
      }
    } catch (IllegalArgumentException e) {
      if (e.getMessage().startsWith(what)) throw e;
      throw new IllegalArgumentException(what + ": " + e.getMessage());
    }
  }

  private static double p(Map<String, Object> m, String key) { return Json.num(Json.get(m, key), key); }

  private static Dist check(Dist d, boolean ok, String what, String rule) {
    if (!ok) throw new IllegalArgumentException(what + ": " + d.kind + " needs " + rule);
    return d;
  }

  public double sample(Random r) {
    double x;
    switch (kind) {
      case "const": x = a; break;
      case "uniform": x = a + (b - a) * r.nextDouble(); break;
      case "triangular": {
        double u = r.nextDouble(), f = (b - a) / (c - a);
        x = u < f ? a + Math.sqrt(u * (c - a) * (b - a)) : c - Math.sqrt((1 - u) * (c - a) * (c - b));
        break;
      }
      case "exponential": x = -a * Math.log(1 - r.nextDouble()); break;
      case "normal": {
        x = c;
        for (int k = 0; k < 1000; k++) {
          double y = a + b * r.nextGaussian();
          if (y >= c) { x = y; break; }
        }
        break;
      }
      case "lognormal": {
        double s2 = Math.log(1 + (b * b) / (a * a));
        x = Math.exp(Math.log(a) - s2 / 2 + Math.sqrt(s2) * r.nextGaussian());
        break;
      }
      case "gamma": x = b * gamma(a, r); break;
      case "weibull": x = b * Math.pow(-Math.log(1 - r.nextDouble()), 1 / a); break;
      case "empirical": x = values[r.nextInt(values.length)]; break;
      default: throw new IllegalStateException(kind);
    }
    return Math.max(0, x);
  }

  /** Theoretical mean (empirical: sample mean; normal: of the untruncated distribution). */
  public double mean() {
    switch (kind) {
      case "const": return a;
      case "uniform": return (a + b) / 2;
      case "triangular": return (a + b + c) / 3;
      case "exponential": case "lognormal": case "normal": return a;
      case "gamma": return a * b;
      case "weibull": return b * Math.exp(lgamma(1 + 1 / a));
      default: { double s = 0; for (double v : values) s += v; return s / values.length; }
    }
  }

  /** Marsaglia-Tsang (2000); shape < 1 via the Gamma(shape + 1) * U^(1/shape) boost. */
  private static double gamma(double k, Random r) {
    if (k < 1) return gamma(k + 1, r) * Math.pow(r.nextDouble(), 1 / k);
    double d = k - 1.0 / 3, cc = 1 / Math.sqrt(9 * d);
    while (true) {
      double z = r.nextGaussian(), v = 1 + cc * z;
      if (v <= 0) continue;
      v = v * v * v;
      double u = r.nextDouble();
      if (Math.log(u) < 0.5 * z * z + d - d * v + d * Math.log(v)) return d * v;
    }
  }

  /** Lanczos log-gamma (for the Weibull mean only). */
  private static double lgamma(double x) {
    double[] g = {676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
        12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7};
    if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x);
    x -= 1;
    double s = 0.99999999999980993;
    for (int i = 0; i < g.length; i++) s += g[i] / (x + i + 1);
    double t = x + g.length - 0.5;
    return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(s);
  }

  @Override public String toString() { return kind + "(mean " + String.format("%.2f", mean()) + ")"; }
}
