import wh.*;
import java.util.*;
public class T1 {
  public static void main(String[] a) {
    String D="model/WarehouseSim/data/";
    Warehouse w = Warehouse.load(D+"layouts/I_v_c0_central_abc.json", D+"config/run_config.json", D+"scenarios/day_1.csv", D+"skus.csv", 1);
    System.out.println("orders "+w.scenario.orders.size()+" receipts "+w.scenario.receipts.size());
    // first uniform per order index for S_PACK
    double mn=1,mx=0; 
    for (int i=0;i<w.scenario.orders.size();i++){ double u=w.rng(Warehouse.S_PACK,i).nextDouble(); mn=Math.min(mn,u); mx=Math.max(mx,u);} 
    System.out.println("first U over orders, S_PACK: min "+mn+" max "+mx);
    for (int s=1;s<=4;s++){ for (int i=0;i<6;i++) System.out.printf("%.5f ", w.rng(s,i).nextDouble()); System.out.println(" stream "+s);}
    // receive times stats
    List<Double> rt=new ArrayList<>(), ph=new ArrayList<>(), pk=new ArrayList<>();
    for (ScenarioData.ReceiptSpec r: w.scenario.receipts) rt.add(w.receiveTime(r));
    for (ScenarioData.ReceiptSpec r: w.scenario.receipts) ph.add(w.cfg.putawayHandling.sample(w.rng(Warehouse.S_PUTAWAY,r.index)));
    for (ScenarioData.OrderSpec o: w.scenario.orders) pk.add(w.cfg.packPerOrder.sample(w.rng(Warehouse.S_PACK,o.index)));
    rep("receive gamma(4,12) mean 48 sd 24", rt); rep("putaway uniform(20,40) mean 30 sd 5.77", ph); rep("packPerOrder tri(40,60,120) mean 73.3 sd 17", pk);
    // pick per line first line
    List<Double> pl=new ArrayList<>();
    for (ScenarioData.OrderSpec o: w.scenario.orders) pl.add(w.cfg.pickPerLine.sample(w.rng(Warehouse.S_PICK,o.index)));
    rep("pick first line lognormal mean 12 sd 5", pl);
    for (int s2=1;s2<=5;s2++){ Warehouse w2 = Warehouse.load(D+"layouts/I_v_c0_central_abc.json", D+"config/run_config.json", D+"scenarios/day_"+s2+".csv", D+"skus.csv", s2);
      List<Double> x=new ArrayList<>(); for (ScenarioData.ReceiptSpec r: w2.scenario.receipts) x.add(w2.receiveTime(r)); rep("seed "+s2+" receive", x);}
  }
  static void rep(String n, List<Double> x){ double s=0,s2=0,mn=1e18,mx=-1e18; for(double v:x){s+=v;s2+=v*v;mn=Math.min(mn,v);mx=Math.max(mx,v);} int k=x.size(); double m=s/k; System.out.printf("%s: n=%d mean %.2f sd %.2f min %.2f max %.2f%n", n,k,m,Math.sqrt(s2/k-m*m),mn,mx);}
}
