# 34 geliştirme haftası — sabit 60 saniye / seed 42

Üç tahmin yöntemi (HGB, ensemble, son yayımlanan gün profili), açık döngü ve günlük rolling değerlendirme. Her hafta 1 oracle + üç yöntem için d0/d1/d2 = 10 MILP, toplam 340. Pilotlar okunarak başlangıç planı alınmaz. İlk karar PostgreSQL referansından, devam kararları yalnız kendi yönteminin önceki gün planından başlar.

```powershell
.venv\Scripts\python.exe -B experiments\04_full_development\test_full.py
.venv\Scripts\python.exe -B experiments\04_full_development\full_run.py --project . --output data/results/direct_milp_04_development_60s
```

Kaynaklar ve ayarlar manifest hash'leriyle sabitlenir. Mevcut çıktı klasörü normal komutta reddedilir. Çalışan süreç varsa ikinci süreç başlatılmaz. Açık `--resume-pending` seçeneği yalnız aynı kaynak/girdilerle kullanılabilir: tamamlanmış haftalar checkpoint'ten, tamamlanmış koşumlar doğrulanmış dosyalarından alınır. Başarısız veya yarıda kesilmiş solve otomatik tekrarlanmaz; bu durum raporda kalır. Başarılı önceki sonuçlar hafta sonu hatası nedeniyle atılmaz. Dosya silinmez.

Her koşumda `solver_trace.txt`, `solver_events.jsonl`, `solver_diagnostics.json` saklanır. Warm-start API dönüşü ve model aktarımı/solve öncesi-sonrası etkin seed/thread/limit/gap seçenekleri kaydedilir. Callback sayıları benzersiz bütün uygun çözümlerin sayısı değildir. Callback/log hatası gizlenmez. Solver ayarlarına müdahale eden bir callback kullanılmaz.

Planlar bağımsız fiziksel/maliyet doğrulamasından geçer. Rolling planı d0/d1/d2'den gerçekten uygulanmış parçalarla birleştirilir; özgün, geçmişi sabitlenmemiş tam modelin bütün satırlarında ve amaç fonksiyonunda denetlenir. Özgün oracle ile politika adaylarını da kullanan deney sonrası uygun üst sınır ayrı kalır. Regret aralıkları ve sıfır paydalı tanımsız bilgi yakalama korunur.

PostgreSQL solver/haftalık metrik tabloları yeni deney kimliğiyle yazılır. Başarısızlıklar, tam-model denetimleri ve yardımcı sonuçlar ayrı `results.milp_full_aux_04` tablosundadır. Yüklemeler idempotenttir. Her hafta CSV checkpoint ve `progress.json` güncellenir. SQL bağlantısı geçici kesilirse solver tekrarı yapılmaz; depolama hatası kaydedilir, sonunda yalnız SQL yüklemesi tekrar denenir.

34 hafta geliştirme dönemidir; kilitli test, seed deneyi, Görev 5 ve stokastik mod yürütülmez. Pilot dosyaları korunur. Çalışma süresince Windows sistem uyku isteği geçici olarak engellenir; güç planı değiştirilmez ve istek işlem sonunda kaldırılır. Yeni çalışma commit'i sonuçlar incelendikten sonra ayrıca onaylanır.
