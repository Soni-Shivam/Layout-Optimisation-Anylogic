import wh.*;
import java.util.*;
public class RngCheck {
  static double corr(double[] a, double[] b){int n=a.length;double ma=0,mb=0;for(int i=0;i<n;i++){ma+=a[i];mb+=b[i];}ma/=n;mb/=n;double sab=0,saa=0,sbb=0;for(int i=0;i<n;i++){sab+=(a[i]-ma)*(b[i]-mb);saa+=(a[i]-ma)*(a[i]-ma);sbb+=(b[i]-mb)*(b[i]-mb);}return sab/Math.sqrt(saa*sbb);}
  public static void main(String[] x){
    String R="/home/shivam/.config/Claude/scratch-workspaces/36c5efff-0222-43b1-90d2-418b1ee76a96/42350534-e721-415f-8a30-0e4e30d3854e/scratch-2026-11-02-a846c7/warehouse-sim/model/WarehouseSim/";
    Warehouse w = Warehouse.load(R+"data/layouts/I_v_c0_central_abc.json", R+"data/config/run_config.json", R+"data/scenarios/day_1.csv", R+"data/skus.csv", 1);
    int n=2000;
    double[] u1=new double[n], u2=new double[n], pk=new double[n], pi=new double[n], rc=new double[n];
    for(int i=0;i<n;i++){ u1[i]=w.rng(Warehouse.S_PICK,i).nextDouble(); u2[i]=w.rng(Warehouse.S_PACK,i).nextDouble();
      pk[i]=w.cfg.packPerOrder.sample(w.rng(Warehouse.S_PACK,i)); pi[i]=w.cfg.pickPerLine.sample(w.rng(Warehouse.S_PICK,i)); rc[i]=w.cfg.receivePerLine.sample(w.rng(Warehouse.S_RECEIVE,i));}
    for(int i=0;i<12;i++) System.out.printf("i=%d u_pick=%.5f u_pack=%.5f packPerOrder=%.3f pickLine=%.3f recv=%.3f%n",i,u1[i],u2[i],pk[i],pi[i],rc[i]);
    System.out.printf("lag1 corr u_pick %.4f pack %.4f pick %.4f recv %.4f%n", corr(Arrays.copyOf(u1,n-1),Arrays.copyOfRange(u1,1,n)), corr(Arrays.copyOf(pk,n-1),Arrays.copyOfRange(pk,1,n)), corr(Arrays.copyOf(pi,n-1),Arrays.copyOfRange(pi,1,n)), corr(Arrays.copyOf(rc,n-1),Arrays.copyOfRange(rc,1,n)));
    System.out.printf("cross corr u_pick vs u_pack same index %.4f%n", corr(u1,u2));
    // seed comparison
    Warehouse w2 = Warehouse.load(R+"data/layouts/I_v_c0_central_abc.json", R+"data/config/run_config.json", R+"data/scenarios/day_2.csv", R+"data/skus.csv", 2);
    double[] v=new double[n]; for(int i=0;i<n;i++) v[i]=w2.rng(Warehouse.S_PICK,i).nextDouble();
    System.out.printf("seed1 vs seed2 u_pick corr %.4f%n", corr(u1,v));
    for(int i=0;i<5;i++) System.out.printf("  seed2 i=%d u=%.5f%n",i,v[i]);
    // pack time per order (full)
    double[] pt=new double[n]; int m=Math.min(n,w.scenario.orders.size()); 
    for(int i=0;i<m;i++){ ScenarioData.OrderSpec o=w.scenario.orders.get(i); pt[i]=w.cfg.packPerOrder.sample(w.rng(Warehouse.S_PACK,o.index)); }
    double mn=1e9,mx=-1e9; for(int i=0;i<200;i++){mn=Math.min(mn,pt[i]);mx=Math.max(mx,pt[i]);} System.out.printf("packPerOrder range over first 200 orders: %.2f..%.2f (dist support 40..120)%n",mn,mx);
  }
}
