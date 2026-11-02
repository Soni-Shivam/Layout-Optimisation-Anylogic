import java.util.Random;
public class R { public static void main(String[] a){ long seed=1; int stream=3;
 double s=0,s2=0; int n=362;
 for(int i=0;i<n;i++){ double u=new Random((seed*1_000_003L+stream)*2_147_483_647L+i).nextDouble(); if(i<8)System.out.printf("%.6f ",u); s+=u; s2+=u*u;}
 double m=s/n; System.out.printf("%nmean %.4f sd %.4f (uniform 0.5, 0.2887)%n", m, Math.sqrt(s2/n-m*m)); }}
