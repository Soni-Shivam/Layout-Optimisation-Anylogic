import java.util.Random;
public class C { public static void main(String[] a){
 for (long seed=1; seed<=3; seed++){ double s=0,s2=0; double[] u=new double[500];
  for(int i=0;i<500;i++){ long k=(seed*1_000_003L+4)*2_147_483_647L+i; u[i]=new Random(k).nextDouble(); s+=u[i]; s2+=u[i]*u[i];}
  double m=s/500, v=s2/500-m*m; double c=0; for(int i=1;i<500;i++) c+=(u[i]-m)*(u[i-1]-m); c/=499*v;
  System.out.printf("seed %d first5 %.5f %.5f %.5f %.5f %.5f mean %.4f sd %.4f lag1 %.4f%n",seed,u[0],u[1],u[2],u[3],u[4],m,Math.sqrt(v),c);
 }}}
