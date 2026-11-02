import java.util.*;
public class T { public static void main(String[] a){
 for(String r: new String[]{"1,RECEIPT,T1,A,2.0","1,ORDER,O1,A,2.0","1,ORDER,O1,A, 2"}){
  try{ wh.ScenarioData s=wh.ScenarioData.parse(Arrays.asList("t_s,type,id,sku,qty",r),"x"); System.out.println(r+" OK");}catch(Exception e){System.out.println(r+" -> "+e);} }}}
