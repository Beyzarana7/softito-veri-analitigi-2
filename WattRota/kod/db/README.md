# PostgreSQL veri katmanı

Mevcut `src/` CSV yükleyicileri değiştirilmez. `kod.db.read_firm(engine)` aynı 18 DataFrame sözlüğünü, `read_prices(engine)` aynı tarih-saat indeksli PTF serisini döndürür. SQL'de satır sırası varsayılmaz; açık sıralama ve tip dönüşümü uygulanır. Referans yüklemelerinde teslim penceresi/kaynak/ürün/saat sırası CSV sözleşmesiyle korunur.

## Kurulum ve kullanım

```text
python -m pip install -r kod/db/requirements.txt
python -B -m unittest kod.db.test_db -v
python -B -m kod.db.validate
```

Proje kökündeki `.env` dosyasında DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD alanları bulunmalıdır. Değerler yalnız yerelde girilir; `.env` Git'e alınmaz. DB_NAME wattrota olmalıdır. Bağlantı URL'si loglanmaz; SQL parametreleri gizlenir. Eski protokol kilitleri korunması için kök requirements dosyası değiştirilmemiştir.

```python
from pathlib import Path
from kod.db import create_db_engine, read_firm, read_prices

engine = create_db_engine(Path.cwd())
firma = read_firm(engine)
fiyatlar = read_prices(engine)
engine.dispose()
```

## Eşdeğerlik ve sonuçlar

Entegrasyon komutu 18 firma tablosunu ve 24.984 fiyat kaydını CSV ile birebir karşılaştırır. Referans maliyeti ve doğrulayıcı çıktıları kontrol edilir. Aynı seed, tek iş parçacığı ve bir düğümlük sabit arama bütçesiyle iki ayrı tam-firma MILP çözülür; üretim/yükleme planları, maliyet ve doğrulayıcı çıktıları tam eşitlik ile sınanır. Bu düğüm sınırı yalnız testte uygulanır; mevcut çözücü değiştirilmez. Süre sınırlı genel çözümde her çalıştırmada aynı plan veya kesin optimum garantisi verilmez.

`results.weekly_decision_metrics`, `method_summaries` ve `net_savings` yalnız geliştirme karar dosyalarından ve 2025 firma karşılaştırmasından yüklenir. Birincil anahtarlar ve koşullu UPSERT aynı kaydın tekrarını önler. İkinci yüklemede satır sayısı yanında içerik eşitliği de test edilir. JSONB payload kaynak satırın ek metriklerini korur; tanımsız bilgi oranları NULL olur. Net tasarruf, modelde tanımlı PTF ve ek giderler kapsamındadır; bütün elektrik faturası tasarrufu değildir.

`results.forecast_log` üretim zamanı, hedef saat, yöntem ve tahmin alanlarıyla oluşturulur. UPDATE, DELETE ve TRUNCATE tetikleyiciyle reddedilir. Canlı akış ve kalıcı test tahmini yazılmaz; geçici test işlemi geri alınır. Yönetici/süper kullanıcı tetikleyiciyi kaldırabileceğinden bu, veritabanı yöneticisine karşı kriptografik değişmezlik garantisi değildir.

20 temel tablonun gerçek sütun/tip/PK/FK bilgileri katalogdan `veri/veri_sozlugu_taslak.md` dosyasına çıkarılır. Entegrasyon raporu `data/results/postgresql_06` altındadır. Kilitli test haftaları puanlanmaz veya sonuç tablolarına taşınmaz; fiyat sayısı/toplamı kontrolü bütün mevcut tarihsel PTF serisini kapsar.

Entegrasyon komutu tekrar çalıştırıldığında önceki sonuç klasörü korunur ve zaman damgalı yeni bir klasör açılır. İstenirse `--output data/results/postgresql_06_yeni` ile yeni yol verilir; mevcut yol reddedilir. SQL sonuç tabloları her çalıştırmada aynı iş anahtarlarıyla idempotent yüklenir.

Önerilen commit: `feat: add PostgreSQL readers and verified idempotent result loading`. Kullanıcı onayı olmadan commit atılmaz. Sonraki çalışma Görev 4'tür.
