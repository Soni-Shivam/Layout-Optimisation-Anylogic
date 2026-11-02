import wh.*;
import java.util.*;
public class T3 {
  public static void main(String[] a) throws Exception {
    String D="model/WarehouseSim/data/";
    for (int seed=1; seed<=3; seed++){
      Warehouse w = Warehouse.load(D+"layouts/I_v_c0_central_abc.json", D+"config/run_config.json", D+"scenarios/day_"+seed+".csv", D+"skus.csv", seed);
      // first pick-line time of each order = first lognormal draw of rng(S_PICK, index)
      int n=w.scenario.orders.size(); double s=0,s2=0;
      for (int i=0;i<n;i++){ double x=w.cfg.pickPerLine.sample(w.rng(Warehouse.S_PICK,i)); s+=x;s2+=x*x; }
      double m=s/n; System.out.printf("seed %d: first pick-line time over %d orders mean %.2f sd %.2f (theory 12, 5)%n", seed, n, m, Math.sqrt(s2/n-m*m));
      int nr=w.scenario.receipts.size(); s=0;s2=0;
      for (ScenarioData.ReceiptSpec r: w.scenario.receipts){double x=w.receiveTime(r); s+=x;s2+=x*x;}
      m=s/nr; System.out.printf("        receive time over %d lines mean %.2f sd %.2f (theory 48, 24)%n", nr, m, Math.sqrt(s2/nr-m*m));
    }
    // fresh-generator comparison: same dist from one Random
    Random r=new Random(1); double s=0; for(int i=0;i<362;i++) s+=Dist.of(Json.parse("{\"dist\":\"gamma\",\"shape\":4,\"scale\":12}"),"g").sample(r);
    System.out.printf("single-stream gamma mean over 362: %.2f%n", s/362);
  }
}
