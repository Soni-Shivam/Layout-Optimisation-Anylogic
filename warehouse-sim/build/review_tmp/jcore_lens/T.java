import wh.*;
import java.util.*;
public class T {
  static final String DATA = "model/WarehouseSim/data/";
  public static void main(String[] a) throws Exception {
    Warehouse w = Warehouse.load(DATA+"layouts/I_v_c0_central_abc.json", DATA+"config/run_config.json", DATA+"scenarios/day_1.csv", DATA+"skus.csv", 1);
    System.out.println("receive times (gamma shape4 scale12, mean 48, sd 24) receipts 0..14:");
    for (int i=0;i<15;i++) System.out.printf("%.3f ", w.receiveTime(w.scenario.receipts.get(i)));
    System.out.println();
    double s=0,s2=0; int n=w.scenario.receipts.size();
    for (ScenarioData.ReceiptSpec r: w.scenario.receipts){double x=w.receiveTime(r); s+=x; s2+=x*x;}
    System.out.printf("n=%d mean=%.3f sd=%.3f%n", n, s/n, Math.sqrt(s2/n-(s/n)*(s/n)));
    System.out.println("putaway durations receipts 0..14 (uniform 20..40 handling):");
    for (int i=0;i<15;i++){ ScenarioData.ReceiptSpec r=w.scenario.receipts.get(i); Warehouse.PutPlan p=w.planPutaway(r,0); System.out.printf("%.3f ", p.duration - p.length/w.cfg.putawaySpeed);}
    System.out.println();
    s=0;s2=0;
    for (ScenarioData.ReceiptSpec r: w.scenario.receipts){Warehouse.PutPlan p=w.planPutaway(r,0); double x=p.duration - p.length/w.cfg.putawaySpeed; s+=x;s2+=x*x;}
    System.out.printf("handling mean=%.3f sd=%.3f (theory 30, 5.77)%n", s/n, Math.sqrt(s2/n-(s/n)*(s/n)));
    // pack per order (triangular) is the first draw of the S_PACK stream
    int no=w.scenario.orders.size(); s=0;s2=0;
    System.out.println("pack time - 4*units for orders 0..14 (triangular 40,60,120):");
    for (int i=0;i<no;i++){ ScenarioData.OrderSpec o=w.scenario.orders.get(i); double x=w.packTime(o)-4*o.units(); if(i<15)System.out.printf("%.3f ",x); s+=x;s2+=x*x;}
    System.out.printf("%nn=%d mean=%.3f sd=%.3f (theory 73.33, 17.0)%n", no, s/no, Math.sqrt(s2/no-(s/no)*(s/no)));
    // first uniform of consecutive streams
    System.out.println("first nextDouble of rng(S_PUTAWAY, i), i=0..9:");
    for (int i=0;i<10;i++) System.out.printf("%.6f ", w.rng(4,i).nextDouble());
    System.out.println();
  }
}
