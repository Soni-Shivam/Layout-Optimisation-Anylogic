import java.util.*;
public class T { public static void main(String[] a){
 Map<String,Object> m=new HashMap<>(); m.put("dist","normal"); m.put("mean",0.0); m.put("sd",10.0); m.put("min",30.0);
 wh.Dist d=wh.Dist.of(m,"t"); Random r=new Random(1); int n=200000, eq=0; double s=0;
 for(int i=0;i<n;i++){double x=d.sample(r); if(x==30.0)eq++; s+=x;}
 System.out.println(eq*1.0/n+" "+s/n);}}
