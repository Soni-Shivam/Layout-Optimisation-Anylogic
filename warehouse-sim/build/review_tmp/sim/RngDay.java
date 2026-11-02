import wh.*;
import java.util.*;
public class RngDay {
  public static void main(String[] x){
    String R="/home/shivam/.config/Claude/scratch-workspaces/36c5efff-0222-43b1-90d2-418b1ee76a96/42350534-e721-415f-8a30-0e4e30d3854e/scratch-2026-11-02-a846c7/warehouse-sim/model/WarehouseSim/";
    for (int seed=1; seed<=5; seed++){
    Warehouse w = Warehouse.load(R+"data/layouts/I_v_c0_central_abc.json", R+"data/config/run_config.json", R+"data/scenarios/day_"+seed+".csv", R+"data/skus.csv", seed);
    int n=w.scenario.orders.size(); double s=0,ss=0; double[] q=new double[n];
    for(int i=0;i<n;i++){ double v=w.cfg.packPerOrder.sample(w.rng(Warehouse.S_PACK,i)); q[i]=v; s+=v; ss+=v*v;}
    double m=s/n, sd=Math.sqrt(ss/n-m*m);
    // fresh random reference
    Random r=new Random(seed); double s2=0,ss2=0; for(int i=0;i<n;i++){double v=w.cfg.packPerOrder.sample(r); s2+=v; ss2+=v*v;}
    double m2=s2/n, sd2=Math.sqrt(ss2/n-m2*m2);
    // receive
    int k=w.scenario.receipts.size(); double rs=0; for(int j=0;j<k;j++) rs+=w.receiveTime(w.scenario.receipts.get(j));
    System.out.printf("seed %d: %d orders, packPerOrder CRN mean %.2f sd %.2f  | independent stream mean %.2f sd %.2f | theory mean 73.33 sd 17.0 | %d receipts mean recv %.1f (theory 48)%n", seed,n,m,sd,m2,sd2,k,rs/k);
    }
  }
}
