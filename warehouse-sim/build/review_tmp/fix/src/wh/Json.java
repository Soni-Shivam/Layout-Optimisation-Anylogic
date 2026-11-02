package wh;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Minimal JSON reader: objects -> LinkedHashMap, arrays -> ArrayList, numbers -> Double. */
public final class Json {
  private final String s;
  private int i;

  private Json(String s) { this.s = s; }

  public static Object parse(String text) {
    Json p = new Json(text);
    p.ws();
    Object v = p.value();
    p.ws();
    if (p.i != p.s.length()) throw p.err("unexpected trailing text");
    return v;
  }

  public static Object read(String path) {
    try {
      return parse(new String(java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(path)), java.nio.charset.StandardCharsets.UTF_8));
    } catch (java.io.IOException e) {
      throw new IllegalArgumentException("cannot read " + path + ": " + e.getMessage());
    }
  }

  // ---- typed access helpers
  @SuppressWarnings("unchecked")
  public static Map<String, Object> obj(Object o, String what) {
    if (!(o instanceof Map)) throw new IllegalArgumentException(what + ": expected a JSON object");
    return (Map<String, Object>) o;
  }

  @SuppressWarnings("unchecked")
  public static List<Object> arr(Object o, String what) {
    if (!(o instanceof List)) throw new IllegalArgumentException(what + ": expected a JSON array");
    return (List<Object>) o;
  }

  public static Object get(Map<String, Object> m, String key) {
    if (!m.containsKey(key)) throw new IllegalArgumentException("missing key \"" + key + "\"");
    return m.get(key);
  }

  public static double num(Object o, String what) {
    if (!(o instanceof Double)) throw new IllegalArgumentException(what + ": expected a number");
    return (Double) o;
  }

  public static int integer(Object o, String what) {
    double d = num(o, what);
    if (d != Math.rint(d)) throw new IllegalArgumentException(what + ": expected an integer, got " + d);
    return (int) d;
  }

  public static String str(Object o, String what) {
    if (!(o instanceof String)) throw new IllegalArgumentException(what + ": expected a string");
    return (String) o;
  }

  // ---- parser
  private Object value() {
    if (i >= s.length()) throw err("unexpected end");
    char c = s.charAt(i);
    if (c == '{') return object();
    if (c == '[') return array();
    if (c == '"') return string();
    if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
    if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
    if (s.startsWith("null", i)) { i += 4; return null; }
    return number();
  }

  private Map<String, Object> object() {
    Map<String, Object> m = new LinkedHashMap<String, Object>();
    i++;
    ws();
    if (peek() == '}') { i++; return m; }
    while (true) {
      ws();
      if (peek() != '"') throw err("expected a key");
      String k = string();
      ws();
      expect(':');
      ws();
      m.put(k, value());
      ws();
      char c = next();
      if (c == '}') return m;
      if (c != ',') throw err("expected ',' or '}'");
    }
  }

  private List<Object> array() {
    List<Object> a = new ArrayList<Object>();
    i++;
    ws();
    if (peek() == ']') { i++; return a; }
    while (true) {
      ws();
      a.add(value());
      ws();
      char c = next();
      if (c == ']') return a;
      if (c != ',') throw err("expected ',' or ']'");
    }
  }

  private String string() {
    expect('"');
    StringBuilder b = new StringBuilder();
    while (true) {
      char c = next();
      if (c == '"') return b.toString();
      if (c == '\\') {
        char e = next();
        switch (e) {
          case '"': b.append('"'); break;
          case '\\': b.append('\\'); break;
          case '/': b.append('/'); break;
          case 'b': b.append('\b'); break;
          case 'f': b.append('\f'); break;
          case 'n': b.append('\n'); break;
          case 'r': b.append('\r'); break;
          case 't': b.append('\t'); break;
          case 'u':
            if (i + 4 > s.length()) throw err("bad \\u escape");
            b.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
            i += 4;
            break;
          default: throw err("bad escape \\" + e);
        }
      } else {
        b.append(c);
      }
    }
  }

  private Double number() {
    int st = i;
    while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
    if (st == i) throw err("unexpected character '" + s.charAt(i) + "'");
    try {
      return Double.valueOf(s.substring(st, i));
    } catch (NumberFormatException e) {
      throw err("bad number " + s.substring(st, i));
    }
  }

  private void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }
  private char peek() { if (i >= s.length()) throw err("unexpected end"); return s.charAt(i); }
  private char next() { char c = peek(); i++; return c; }
  private void expect(char c) { if (next() != c) throw err("expected '" + c + "'"); }
  private IllegalArgumentException err(String m) { return new IllegalArgumentException("JSON: " + m + " at position " + i); }
}
