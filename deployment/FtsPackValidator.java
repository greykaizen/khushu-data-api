import java.sql.*;
public class FtsVal {
  static int fails=0;
  static long one(String db,String sql){ try(Connection c=DriverManager.getConnection("jdbc:sqlite:"+db); Statement s=c.createStatement(); ResultSet r=s.executeQuery(sql)){return r.getLong(1);}catch(Exception e){System.out.println("  ERR "+sql+" -> "+e.getMessage());fails++;return -1;} }
  static void eq(String label,long got,long want){ boolean ok=got==want; if(!ok)fails++; System.out.printf("  %-46s got=%d want=%d %s%n",label,got,want,ok?"OK":"*** FAIL ***"); }
  public static void main(String[] a){ try{Class.forName("org.sqlite.JDBC");}catch(Exception e){System.out.println(e);return;}
    String P="/home/kaizen/AndroidStudioProjects/khushu-data-api/data/packs/";
    System.out.println("== external-content FTS5 ==");
    eq("quran-core arabic ar-Rahman", one(P+"quran-core.db","SELECT COUNT(*) FROM quran_arabic_fts WHERE quran_arabic_fts MATCH 'الرحمن'"),45);
    eq("quran-core surah_alias Yusuf", one(P+"quran-core.db","SELECT COUNT(*) FROM quran_surah_alias_fts WHERE quran_surah_alias_fts MATCH 'Yusuf'"),17);
    eq("hadith-bukhari prayer", one(P+"hadith-bukhari.db","SELECT COUNT(*) FROM bukhari_hadith_fts WHERE bukhari_hadith_fts MATCH 'prayer'"),1043);
    System.out.println("== contentless FTS5 + rowid-join ==");
    eq("sahih translation_fts merciful (pack-scoped)", one(P+"translation-en_saheeh-international.db","SELECT COUNT(*) FROM translation_fts WHERE translation_fts MATCH 'merciful'"),172);
    try(Connection c=DriverManager.getConnection("jdbc:sqlite:"+P+"translation-en_saheeh-international.db"); Statement s=c.createStatement();
        ResultSet r=s.executeQuery("SELECT ta.surah_no,ta.ayah_no,substr(ta.translation,1,48) FROM translation_fts JOIN translation_ayahs ta ON ta.rowid=translation_fts.rowid WHERE translation_fts MATCH 'merciful' LIMIT 1")){
      if(r.next()) System.out.println("  contentless rowid->base join: "+r.getInt(1)+":"+r.getInt(2)+" \""+r.getString(3)+"...\""); else {System.out.println("  *** join empty");fails++;}
    }catch(Exception e){System.out.println("  ERR join "+e.getMessage());fails++;}
    eq("content dua_fts pray", one(P+"content.db","SELECT COUNT(*) FROM dua_fts WHERE dua_fts MATCH 'pray'"),4);
    System.out.println("== base counts (xerial vs system sqlite3) ==");
    eq("core quran_ayah_words", one(P+"quran-core.db","SELECT COUNT(*) FROM quran_ayah_words"),334660);
    eq("wbw-en words", one(P+"wbw-en.db","SELECT COUNT(*) FROM wbw_words"),167330);
    eq("tafsir tabari entries", one(P+"tafsir-ar-tafsir-al-tabari.db","SELECT COUNT(*) FROM tafsir_entries"),6196);
    System.out.println(fails==0?"\nALL GREEN under xerial sqlite-jdbc 3.46 (external-content + contentless FTS5 + rowid-join)":("\n"+fails+" FAILURES"));
    System.exit(fails==0?0:1);
  }
}
