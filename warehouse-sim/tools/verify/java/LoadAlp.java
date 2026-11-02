import java.io.*;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import com.anylogic.serialization.*;
import com.anylogic.objectmodel.elements.*;

/** Loads an .alp with AnyLogic's own serializer (headless) and optionally writes it back. */
public class LoadAlp {
  static Object proxyFor(Class<?> itf) {
    return Proxy.newProxyInstance(itf.getClassLoader(), new Class<?>[]{itf}, (p, m, args) -> {
      Class<?> rt = m.getReturnType();
      if (m.getName().equals("toString")) return "Stub(" + itf.getSimpleName() + ")";
      if (m.getName().equals("hashCode")) return System.identityHashCode(p);
      if (m.getName().equals("equals")) return p == args[0];
      if (args != null && args.length > 0 && args[0] != null && rt.isInstance(args[0])) return args[0];
      if (rt == boolean.class) return false;
      if (rt == int.class) return 0; if (rt == long.class) return 0L; if (rt == double.class) return 0.0;
      if (rt == float.class) return 0f; if (rt == short.class) return (short)0; if (rt == byte.class) return (byte)0; if (rt == char.class) return (char)0;
      if (rt == Optional.class) return Optional.empty();
      if (rt == List.class || rt == Collection.class) return new ArrayList<>();
      if (rt == Set.class) return new HashSet<>();
      if (rt == Map.class) return new HashMap<>();
      if (rt == String.class) return "";
      return null;
    });
  }

  @SuppressWarnings("unchecked")
  public static void main(String[] a) throws Exception {
    Path stubs = Paths.get("stubs.txt");
    if (Files.exists(stubs)) for (String c : Files.readAllLines(stubs)) if (!c.isBlank()) {
      Class<Object> itf = (Class<Object>) Class.forName(c.trim());
      Object impl = proxyFor(itf);
      com.anylogic.DependencyInjector.bind(itf, () -> impl);
    }
    ObjectModelSerializerImpl ser = new ObjectModelSerializerImpl();
    if (System.getProperty("convert") != null) {
      ser.setOldALPConverterRegistry(new com.anylogic.serialization.converter.OldALPConverterRegistry());
      System.out.println("converter registry set");
    }
    String modelName = System.getProperty("name", new File(a[0]).getName().replace(".alp", ""));
    try (InputStream in = new FileInputStream(a[0])) {
      LoadedModel lm = ser.read(in, modelName, new File(a[0]).getAbsoluteFile().getParent());
      System.out.println("LOADED OK: " + lm);
      for (Method m : lm.getClass().getMethods()) if (m.getParameterCount() == 0 && m.getDeclaringClass() == lm.getClass()) {
        try { System.out.println("  " + m.getName() + " -> " + m.invoke(lm)); } catch (Exception e) { System.out.println("  " + m.getName() + " !! " + e.getCause()); }
      }
      if (a.length > 1) {
        OMModel model = lm.getRAWUnconvertedModel();
        if (System.getProperty("convert") != null) {
          Object ctx = proxyFor(com.anylogic.objectmodel.elements.IWorkspaceContext.class);
          model = lm.convertToCurrentVersion((com.anylogic.objectmodel.elements.IWorkspaceContext) ctx);
          System.out.println("converted; log entries: " + lm.getConversionLog().size());
          for (Object e : lm.getConversionLog()) System.out.println("   LOG " + e);
        }
        try (OutputStream out = new FileOutputStream(a[1])) { ser.write(model, out); }
        System.out.println("Re-serialized to " + a[1]);
      }
    }
  }
}
