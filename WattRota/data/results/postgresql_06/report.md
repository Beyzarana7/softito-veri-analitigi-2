# PostgreSQL okuma katmanı — görev 6

CSV akışı değişmedi. Yeni SQLAlchemy katmanı `kod/db/` altındadır. Bağlantı değerleri yalnız proje kökündeki Git dışı `.env` dosyasından okunur; URL ve değerler raporlanmaz.

18 firma tablosunun tip, satır sırası ve değerleri birebir eşleşti. Fiyat serisi 24984 satır; toplam 58113112.82; ilk 2024-01-01 00:00:00; son 2026-11-06 23:00:00.

Referans maliyeti: 652799.65895 TL. Testte bulunan öneri maliyeti: 644855.65185 TL. Her iki yoldan seçilen üretim/yükleme planı ve bağımsız doğrulayıcının bütün çıktıları birebir eşleşti.
Çözücü karşılaştırması sabit seed, tek iş parçacığı, bir arama düğümü ve aynı doğrulanmış başlangıçla iki kez bağımsız çalıştırıldı. Normal süre sınırlı çalışmalarda aynı plan garantisi verilmez. Test planı kesin optimum iddiası değildir; gap ve alt sınırlar validation.json içinde saklanır.

Sonuç tabloları: {"weekly_decision_metrics": 136, "method_summaries": 4, "net_savings": 137, "forecast_log": 0}. İki yüklemede kayıt sayıları ve içerikler değişmedi; SQL değerleri kaynak CSV kayıtlarıyla karşılaştırıldı.
`results.forecast_log` yalnız şema olarak oluşturuldu. UPDATE, DELETE ve TRUNCATE engelleri geri alınan test işlemiyle doğrulandı; test kaydı kalıcılaştırılmadı. Canlı akış bağlanmadı. Bu engelleri veritabanı sahibi/süper kullanıcı kaldırabilir; yöneticiye karşı değişmez kayıt garantisi değildir.

Yalnız 34 geliştirme haftası ve 2025 firma karşılaştırması sonuç tablolarına yüklendi. Kilitli 10 hafta açılmadı. 20 temel tablonun sözlüğü `veri/veri_sozlugu_taslak.md` dosyasına katalogdan çıkarıldı.
