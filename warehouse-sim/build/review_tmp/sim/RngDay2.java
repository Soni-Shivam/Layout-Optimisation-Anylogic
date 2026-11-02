import wh.*;
import java.util.*;
public class RngDay2 {
  public static void main(String[] x){
    String R="/home/shivam/.config/Claude/scratch-workspaces/36c5efff-0222-43b1-90d2-418b1ee76a96/42350534-e721-415f-8a30-0e4e30d3854e/scratch-2026-11-02-a846c7/warehouse-sim/model/WarehouseSim/";
    for (int seed=1; seed<=5; seed++){
    Warehouse w = Warehouse.load(R+"data/layouts/I_v_c0_central_abc.json", R+"data/config/run_config.json", R+"data/scenarios/day_"+seed+".csv", R+"data/skus.csv", seed);
    int k=w.scenario.receipts.size(); double s=0,ss=0; for(int j=0;j<k;j++){double v=w.cfg.putawayHandling.sample(w.rng(Warehouse.S_PUTAWAY,j)); s+=v; ss+=v*v;}
    double m=s/k; 
    int n=w.scenario.orders.size(); double ps=0; int pc=0; for(int i=0;i<n;i++){ Random r=w.rng(Warehouse.S_PICK,i); ScenarioData.OrderSpec o=w.scenario.orders.get(i); for(int l=0;l<o.skus.length;l++){ps+=w.cfg.pickPerLine.sample(r);pc++;}}
    System.out.printf("seed %d: putaway handling mean %.2f sd %.2f (theory 30, 5.77) | pick per line mean %.2f (theory 12)%n", seed, m, Math.sqrt(ss/k-m*m), ps/pc);
    }
  }
}
