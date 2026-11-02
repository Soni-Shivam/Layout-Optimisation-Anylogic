public class T { public static void main(String[] a){
 System.out.println((int)((String)wh.Json.parse("\"\\u+041\"")).charAt(0));
 System.out.println((int)((String)wh.Json.parse("\"\\u-041\"")).charAt(0));
 try { wh.Json.parse("[\"\\u12\"]"); } catch(Exception e){ System.out.println(e); }
}}
