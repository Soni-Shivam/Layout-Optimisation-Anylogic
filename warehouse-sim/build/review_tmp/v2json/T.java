public class T { public static void main(String[] a){
 System.out.println(wh.Json.parse("\"\\u+041\""));
 try{ wh.Json.parse("[\"\\u12\"]"); }catch(Exception e){System.out.println(e);} } }
