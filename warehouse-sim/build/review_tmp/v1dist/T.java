import java.util.*;
public class T { public static void main(String[] a){ double c=30,m=0,s=10; Random r=new Random(1); int n=200000,eq=0; double sum=0;
for(int i=0;i<n;i++){ double x=c; for(int k=0;k<1000;k++){double y=m+s*r.nextGaussian(); if(y>=c){x=y;break;}} if(x==c)eq++; sum+=x;}
System.out.println(eq*1.0/n+" "+sum/n);}}
