import wh.*;
import java.util.*;
public class WalkCheck {
  public static void main(String[] x){
    String R="/home/shivam/.config/Claude/scratch-workspaces/36c5efff-0222-43b1-90d2-418b1ee76a96/42350534-e721-415f-8a30-0e4e30d3854e/scratch-2026-11-02-a846c7/warehouse-sim/model/WarehouseSim/";
    for (String lay : new String[]{"I_v_c0_central_abc","I_h_c0_central_abc","U_v_c1_near_out_abc","L_v_c1_central_abc"}) {
    Warehouse w = Warehouse.load(R+"data/layouts/"+lay+".json", R+"data/config/run_config.json", R+"data/scenarios/day_1.csv", R+"data/skus.csv", 1);
    double maxErr=0; int shared=0;
    for (ScenarioData.OrderSpec o : w.scenario.orders){
      Warehouse.PickPlan p=w.planPick(o, 100);
      Random r=w.rng(Warehouse.S_PICK,o.index); double dw=0; for(int i=0;i<o.skus.length;i++) dw+=w.cfg.pickPerLine.sample(r);
      maxErr=Math.max(maxErr, Math.abs(p.duration-(p.length/w.cfg.walkSpeed+dw)));
      if (p.stops<o.skus.length) shared++;
    }
    double maxE2=0;
    for (ScenarioData.ReceiptSpec rc: w.scenario.receipts){ Warehouse.PutPlan p=w.planPutaway(rc,0); double h=w.cfg.putawayHandling.sample(w.rng(Warehouse.S_PUTAWAY,rc.index)); maxE2=Math.max(maxE2,Math.abs(p.duration-(p.length/w.cfg.putawaySpeed+h)));}
    System.out.printf("%s pick dur err %.2e, orders with shared access node %d, put err %.2e, docks %d%n",lay,maxErr,shared,maxE2,w.layout.inDocks.length);
    }
  }
}
