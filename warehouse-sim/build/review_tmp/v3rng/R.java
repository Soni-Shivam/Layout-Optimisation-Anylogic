import java.util.Random;
public class R { public static void main(String[] a){ long seed=1; int stream=2;
 for(int i=0;i<10;i++){ Random r=new Random((seed*1_000_003L+stream)*2_147_483_647L+i); System.out.printf("%d %.5f %.5f%n",i,r.nextDouble(),r.nextDouble()); } } }
