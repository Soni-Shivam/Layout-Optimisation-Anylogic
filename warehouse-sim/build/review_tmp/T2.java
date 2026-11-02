import wh.*;
import java.util.*;
public class T2 {
  static void tryit(String n, Runnable r){ try { r.run(); System.out.println(n+": OK"); } catch (Throwable e) { System.out.println(n+": "+e.getClass().getSimpleName()+": "+e.getMessage()); } }
  public static void main(String[] a) {
    // percentile float issues
    int bad=0; for (int n=1;n<=100000;n++){ int k=(int)Math.ceil(0.95*n)-1; int exact=(19*n+19)/20-1; if(k!=exact){bad++; if(bad<5) System.out.println("p95 n="+n+" k="+k+" exact="+exact);} } System.out.println("p95 mismatches "+bad);
    tryit("order qty 2.0", () -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,ORDER,O1,A,2.0"),"x"));
    tryit("order qty ' 2'", () -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,ORDER,O1,A, 2"),"x"));
    tryit("receipt qty 2.0", () -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,RECEIPT,T1,A,2.0"),"x"));
    tryit("order qty 1e0", () -> ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,ORDER,O1,A,1e0"),"x"));
    tryit("order qty 3e9", () -> System.out.println(ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,RECEIPT,T1,A,3e9"),"x").receipts.get(0).qty));
    tryit("order t NaN", () -> System.out.println(ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","NaN,ORDER,O1,A,1","1,ORDER,O2,A,1"),"x").orders.get(0).t));
    tryit("json \\u bad hex", () -> Json.parse("\"\\uZZZZ\""));
    tryit("json 1e-5", () -> System.out.println(Json.parse("[1e-5, 1E+3, -0.5]")));
    tryit("json nested/ws", () -> System.out.println(Json.parse(" \n\t{ \"a\" : [ [ ] , { } , \"\\ud83d\\ude00\" ] } \r\n")));
    tryit("json 1e999", () -> System.out.println(Json.parse("1e999")));
    tryit("json BOM", () -> Json.parse("\uFEFF{}"));
    tryit("json empty", () -> Json.parse(""));
    tryit("json [", () -> Json.parse("["));
    tryit("json {\"a\"", () -> Json.parse("{\"a\""));
    tryit("integer 3e9", () -> System.out.println(Json.integer(3e9,"x")));
    // lgamma check
    tryit("weibull mean shape 1 scale 10", () -> System.out.println(Dist.of(Json.parse("{\"dist\":\"weibull\",\"shape\":1,\"scale\":10}"),"w").mean()));
    tryit("weibull mean shape 0.5 scale 1 (Gamma(3)=2)", () -> System.out.println(Dist.of(Json.parse("{\"dist\":\"weibull\",\"shape\":0.5,\"scale\":1}"),"w").mean()));
    tryit("weibull mean shape 3 scale 1", () -> System.out.println(Dist.of(Json.parse("{\"dist\":\"weibull\",\"shape\":3,\"scale\":1}"),"w").mean()+" expect 0.8929795"));
    // gamma shape small
    for (double sh : new double[]{0.1,0.3,0.9,1,1.5}) { Dist d=Dist.of(Json.parse("{\"dist\":\"gamma\",\"shape\":"+sh+",\"scale\":3}"),"g"); Random r=new Random(1); double s=0,s2=0; int n=400000; for(int i=0;i<n;i++){double x=d.sample(r);s+=x;s2+=x*x;} double m=s/n; System.out.printf("gamma %.2f: mean %.4f exp %.4f var %.4f exp %.4f%n",sh,m,sh*3,s2/n-m*m,sh*9); }
    for (String sp : new String[]{"{\"dist\":\"triangular\",\"min\":0,\"mode\":0,\"max\":6}","{\"dist\":\"triangular\",\"min\":0,\"mode\":6,\"max\":6}"}) { Dist d=Dist.of(Json.parse(sp),"t"); Random r=new Random(1); double s=0; for(int i=0;i<200000;i++) s+=d.sample(r); System.out.println(sp+" mean "+s/200000+" exp "+d.mean()); }
    // dwell at start: from == targets[0]
    Stats.TimeLevel tl=new Stats.TimeLevel(); tl.set(10,-1); System.out.println("TimeLevel max after only negative: "+tl.max());
  }
}
