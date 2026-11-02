import java.util.Random;
public class V { public static void main(String[] a){
 for (long seed: new long[]{1,2,3,12345}) { int stream=4; double s=0,s2=0; int n=360;
  for(int i=0;i<n;i++){ double u=new Random((seed*1_000_003L+stream)*2_147_483_647L+i).nextDouble(); s+=u; s2+=u*u;}
  double m=s/n; System.out.printf("seed %d mean %.4f sd %.4f (iid: 0.5, 0.2887)%n",seed,m,Math.sqrt(s2/n-m*m)); } } }
