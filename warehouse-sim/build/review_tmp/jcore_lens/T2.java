import wh.*;
import java.util.*;
public class T2 {
  public static void main(String[] a) throws Exception {
    // percentile: nearest rank should be index ceil(95 n / 100) - 1 (exact integer arithmetic)
    int bad=0; StringBuilder ex=new StringBuilder();
    for (int n=1;n<=5000;n++){
      List<Double> xs=new ArrayList<>(); for(int i=0;i<n;i++) xs.add((double)i);
      double got=Stats.percentile(xs,0.95); int exact=(95*n+99)/100-1;
      if (got!=exact){bad++; if(ex.length()<200) ex.append(n).append(":").append(got).append("vs").append(exact).append(" ");}
    }
    System.out.println("percentile mismatches n<=5000: "+bad+"  "+ex);
    // scenario qty 2.0
    try { ScenarioData s=ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,ORDER,O1,A,2.0"),"day.csv"); System.out.println("qty 2.0 ok: "+s.orders.get(0).qty[0]); }
    catch (Exception e){ System.out.println("qty 2.0 -> "+e); }
    try { ScenarioData s=ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,RECEIPT,T1,A,2.0"),"day.csv"); System.out.println("receipt qty 2.0 ok: "+s.receipts.get(0).qty); }
    catch (Exception e){ System.out.println("receipt qty 2.0 -> "+e); }
    try { ScenarioData s=ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty","1,ORDER,O1,A, 2"),"day.csv"); System.out.println("qty ' 2' ok"); }
    catch (Exception e){ System.out.println("qty ' 2' -> "+e); }
    // Json
    String[] js={"1e-5","-0.0","[1,2]x","\"\\u00e9\"","\"\\uD83D\\uDE00\"","01","1.","+1",".5","\"\\u+041\"","1e400","{\"a\":{\"b\":[[]]}}","\"a\tb\"","[1,]","{\"a\":1 \"b\":2}","2147483648", "[\"\\u12\"]"};
    for (String s: js){ try { Object o=Json.parse(s); System.out.println("parse "+s+" -> "+o+(o instanceof String? " len="+((String)o).length():"")); } catch(Exception e){System.out.println("parse "+s+" -> "+e);} }
    try { System.out.println("integer(1e10)="+Json.integer(Json.parse("1e10"),"x")); } catch(Exception e){System.out.println(e);}
    // lgamma accuracy via weibull mean
    for (double k: new double[]{0.5,1,1.5,2,3.4,0.2}) {
      Dist d=Dist.of(Json.parse("{\"dist\":\"weibull\",\"shape\":"+k+",\"scale\":1}"),"w");
      System.out.println("weibull k="+k+" mean="+d.mean());
    }
  }
}
