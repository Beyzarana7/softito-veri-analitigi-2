# Doğrudan fiyat tahminiyle MILP — dört haftalık pilot

Girdiler `kod.db` aracılığıyla PostgreSQL'den okunur. Mevcut CSV akışı ve doğrulanmış çözücü değiştirilmez. `solver.py`, mevcut MILP'nin kısıtlarını koruyan ayrı bir kopyadır; yeniden planlamada geçmiş saatleri sabitler. Kaynak izi `solver_origin.txt` içindedir.

`config.json` yalnız geliştirme haftalarındaki 0, 11, 22 ve 33. fold'ları seçer. Her hafta aynı ayarlarla 7 çözüm çalışır: gerçek fiyatlı oracle, HGB/ensemble ilk planları ve her yöntem için iki günlük yeniden çözüm. İlk planlar hem açık döngü hem rolling değerlendirmede kullanılır. Her çözüm 15 saniye sınırına sahiptir; yerel arama kapalıdır. Sonuçlar en iyi koşumu seçerek birleştirilmez.

Proje kökünde:

```powershell
.venv\Scripts\python.exe -B experiments\04_direct_milp\test_task4.py
.venv\Scripts\python.exe -B experiments\04_direct_milp\run.py --project . --output data/results/direct_milp_04_pilot
.venv\Scripts\python.exe -B experiments\04_direct_milp\review_pilot.py --project . --output data/results/direct_milp_04_pilot
```

Çıktı klasörü mevcutsa çalışma durur. Tahminler her karar anında yalnız açıklanmış geçmişten yeniden eğitilir. İkinci yeniden çözümde kalan son gün bütünüyle açıklanmıştır. Rolling uygulamada yalnız ilk gün yürütülür; uygulanmış plan, stok, hazırlık ve makine geçmişi korunur. Her ara planın tamamı ayrıca gerçek fiyatlarla maliyetlendirilir; rolling politika maliyeti yalnız uygulanan günlerin toplamıdır.

Süre sınırlı oracle, kesin optimum anlamına gelmez. Oracle uygun maliyeti ve alt sınırı birlikte kaydedilir; gerçek regret bu sınırlarla aralık olarak raporlanır. Bilgi yakalama, toplam kazancın toplam potansiyele oranıdır; haftalık oran ortalaması kullanılmaz. Sonuçlar `results.milp_runs_04` ve `results.milp_weekly_04` tablolarına deney kimliğiyle idempotent yazılır.

34 haftalık tam çalışma ve stokastik mod bu komutta yoktur. Pilot sonunda süre tahmini sunulur; tam çalışma kullanıcı onayı gerektirir. `.env` içeriği okunmaz/yazdırılmaz; bağlantıyı mevcut güvenli veri katmanı yönetir.

`review_pilot.py` MILP çalıştırmaz; diskteki 28 planı yeniden doğrular, gelecek fiyatları değiştirme testiyle iki gerçek model hattını sınar, grafik üretir ve `results.milp_summary_04` tablosuna altı politika özetini idempotent yükler. Pilot sonrası yalnız rapor biçimi ve tam sayı/ondalıklı ton gösteriminin plan imzasına etkisi düzeltildi. Özgün koşum kaynak hash'leri `manifest.json`, düzeltme izleri `postprocessing_manifest.json` içindedir; maliyetler ve planlar değiştirilmedi.
