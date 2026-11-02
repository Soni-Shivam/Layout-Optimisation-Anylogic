import java.util.*;
public class CrnTest {
  static Random rng(long seed, int stream, int index) { return new Random((seed * 1_000_003L + stream) * 2_147_483_647L + index); }
  static double corr(double[] a, double[] b){ int n=a.length; double ma=0,mb=0; for(int i=0;i<n;i++){ma+=a[i];mb+=b[i];} ma/=n; mb/=n; double sab=0,saa=0,sbb=0; for(int i=0;i<n;i++){sab+=(a[i]-ma)*(b[i]-mb);saa+=(a[i]-ma)*(a[i]-ma);sbb+=(b[i]-mb)*(b[i]-mb);} return sab/Math.sqrt(saa*sbb);}
  public static void main(String[] x){
    int n=1200;
    double[] u=new double[n], idx=new double[n], u2=new double[n], lag=new double[n-1], lag1=new double[n-1];
    for(int i=0;i<n;i++){ u[i]=rng(1,2,i).nextDouble(); idx[i]=i; u2[i]=rng(2,2,i).nextDouble(); }
    for(int i=0;i<n-1;i++){ lag[i]=u[i]; lag1[i]=u[i+1]; }
    System.out.println("first 12 pack-stream uniforms, seed 1, orders 0..11:");
    for(int i=0;i<12;i++) System.out.printf("%.5f ", u[i]); System.out.println();
    System.out.printf("corr(u_i, i) seed1 stream PACK n=%d: %.4f%n", n, corr(u, idx));
    System.out.printf("lag-1 autocorr: %.4f%n", corr(lag, lag1));
    System.out.printf("corr(day1 u_i, day2 u_i): %.4f%n", corr(u, u2));
    double[] p=new double[n]; for(int i=0;i<n;i++) p[i]=rng(1,1,i).nextDouble();
    System.out.printf("corr(pick stream u_i, pack stream u_i): %.4f%n", corr(u,p));
    // mean of first 200 vs last 200
    double a=0,b=0; for(int i=0;i<200;i++){a+=u[i];b+=u[n-1-i];} System.out.printf("mean u orders 0-199: %.3f, orders %d-%d: %.3f%n", a/200, n-200, n-1, b/200);
    // contrast: well-mixed seeds
    double[] v=new double[n]; for(int i=0;i<n;i++) v[i]=new Random(new SplittableRandom(i*31L+7).nextLong()).nextDouble();
    System.out.printf("control corr(v_i,i): %.4f%n", corr(v, idx));
  }
}
