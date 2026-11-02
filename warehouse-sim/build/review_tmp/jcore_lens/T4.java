import wh.*;
import java.util.*;
public class T4 {
  public static void main(String[] a) throws Exception {
    Dist d=Dist.of(Json.parse("{\"dist\":\"normal\",\"mean\":0,\"sd\":10,\"min\":30}"),"n");
    Random r=new Random(5); int n=20000, atMin=0; double s=0;
    for(int i=0;i<n;i++){double x=d.sample(r); if(x==30) atMin++; s+=x;}
    System.out.printf("normal(0,10) truncated at 30: %.1f%% of samples exactly 30, mean %.3f (true truncated mean ~33.04)%n", 100.0*atMin/n, s/n);
    try { Map<String,Integer> m=ScenarioData.loadSkus("build/review_tmp/jcore_lens/skus_frac.csv"); System.out.println("loadSkus: "+m); } catch(Exception e){System.out.println(e);}
  }
}
