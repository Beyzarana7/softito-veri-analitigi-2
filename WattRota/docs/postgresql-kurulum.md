# PostgreSQL veri katmanı

WattRota'nın yerel veritabanı `wattrota`, uygulama tablolarının şeması `wattrota` adını taşır. VS Code'daki PostgreSQL eklentisi sorgu yazmak ve tabloları incelemek için kullanılır.

## Kurulum

1. Yerel PostgreSQL sunucusunun `postgres` veritabanına bağlanın ve `sql/00_veritabani_olustur.sql` dosyasını bir kez çalıştırın.
2. Proje Python ortamında `python scripts/veritabani_sql_hazirla.py` komutunu çalıştırın. Bu komut mevcut firma CSV'lerini fiziksel kontrollerden geçirir ve `data/database_import/firma_01_yukle.sql` dosyasını üretir.
3. VS Code sorgu bağlantısını **wattrota** veritabanına değiştirin. Üretilen yükleme SQL'ini çalıştırın.
4. `sql/01_veritabani_kontrol.sql` ile ilişki kontrollerini ve toplamları doğrulayın.

Aktarım bir işlem içinde yapılır. Aynı şema zaten varsa yükleme durur; tablolar silinmez veya mevcut kayıtlar değiştirilmez. Yükleme sırasında hata olursa işlem geri alınmalıdır (`ROLLBACK;`). İlk kurulum dosyası günlük fiyat güncellemesi için kullanılmaz.

## Tablo düzeni

Firma CSV'lerindeki tabloların alan adları korunur. `rota_tanimlari`, rota adımlarından ayrıştırılan rota başlıklarını tutar; siparişin ürünü, teslim türü ve rotası aynı tanıma bağlıdır. `elektrik_fiyatlari`, EPİAŞ'tan alınan bütün saatlik geçmişi; `fiyatlar`, firmanın kayıtlı planlama döneminin fiyatlarını içerir. `referans_plan` ve `referans_yuklemeler`, doğrulanmış karşılaştırma planıdır.

Birincil anahtarlar tekrarlanan kimlikleri ve saatleri; yabancı anahtarlar olmayan ürün, makine, iş emri ve sipariş bağlantılarını reddeder. Sayısal ve zamansal kontroller negatif kapasite veya ters tarih aralığı gibi kayıtları engeller. Bu kontroller, çizelgeleme motorundaki stok, teslim ve kaynak uygunluğu denetimlerinin yerine geçmez.

Zamanlar Türkiye yerel saatini temsil eden `timestamp without time zone` alanlarında saklanır. Kapalı referans plan satırlarındaki boş ürün ve iş emri alanları SQL'de `NULL` olarak tutulur.

Üretilen aktarım dosyası CSV'lerden yeniden oluşturulabilir. Veritabanı parolası SQL dosyalarına, kaynak koda veya GitHub deposuna yazılmaz.
