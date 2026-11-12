# Görev 4 — 60 saniye / üç tahmin yöntemi pilotu

Önceki 15 saniyelik deney değiştirilmez. Aynı PostgreSQL girdi hash'leri, dört geliştirme haftası, gap hedefi, tek iş parçacığı ve seed 42 korunur. Ek politika `naive`, Görev 2'deki `son_yayinlanan_gun` yöntemidir: açıklanmış 24 saatlik fiyat profilini sonraki iki gün için tekrarlar. Fiyattan bağımsız referans ayrı politikadır.

Her haftada 10 MILP: oracle, ardından her gün HGB/ensemble/naive. İlk karar hem açık döngü hem rolling başlangıcıdır. Dört hafta toplam 40 MILP'dir. Önceki deneye ait plan hiçbir çözümün başlangıcına aktarılmaz. İlk kararlar PostgreSQL referansıyla; rolling devamı yalnız aynı deney/yöntemin önceki gün planıyla başlar. Geçmiş saatler aynı 72 saatlik modelde sabitlenir.

`solver.py` önceki ayrı MILP kopyasının aynısıdır; yalnız seed parametresi ve seçeneğin kabul/geri okuma denetimi ile ek günlük alanları vardır. Pilot seed 42'dir. HiGHS'in `random_seed` seçeneği gerçekten atanır ve geri okunur; farklı seed'lerin etkisi bu pilotta sınanmaz. Duyarlılık önerisi config içinde sonuçlara göre seçilmeyen fold 5, 16, 28 ve beş seed ile önceden belirtilmiştir; uygulanmaz.

```powershell
.venv\Scripts\python.exe -B -W ignore::FutureWarning experiments\04_direct_milp_60s\test_task4.py
.venv\Scripts\python.exe -B -W ignore::FutureWarning experiments\04_direct_milp_60s\run.py --project . --output data/results/direct_milp_04_pilot_60s
.venv\Scripts\python.exe -B -W ignore::FutureWarning experiments\04_direct_milp_60s\test_analysis.py
.venv\Scripts\python.exe -B -W ignore::FutureWarning experiments\04_direct_milp_60s\analyze.py --project . --output data/results/direct_milp_04_pilot_60s
```

Her çözüm gerçek fiyatlarla bağımsız doğrulanır. Elektrik; normal işletim, başlatma elektriği ve ürün geçiş elektriği olarak ayrılır. Başlatma/geçiş elektrik dışı giderleri ile plan değişikliği ayrı gösterilir; bu kalemlerin toplamı bağımsız doğrulayıcının toplamıyla saat saat eşleşmelidir. Mevcut plan değişikliği birim gideri sıfırdır; yeni bir gider uydurulmaz.

Oracle maliyeti kesin optimum değildir. Oracle alt sınırı ve bulunan plan maliyeti arasında optimum belirsizliği korunur. Gerçek regret aralıkla, bulunan oracle plana göre maliyet farkı ayrı sütunda verilir. Bilgi yakalama toplam kazanç / toplam potansiyeldir; sıfır payda tanımsızdır. Farklı süre bütçelerinin en iyi sonuçları seçilip birleştirilmez. Rolling avantajı güncellenen bilgi ve ek çözüm bütçesini içerir; tek başına ML katkısı sayılmaz.

Sonuçlar mevcut `results.milp_runs_04` ve `results.milp_weekly_04` tablolarına farklı deney kimliğiyle idempotent yazılır. 34 hafta, seed duyarlılığı, Görev 5 ve stokastik mod çalıştırılmaz. Commit kullanıcı onayına bağlıdır.

`analyze.py` MILP çözmez. Kaydedilmiş 40 planı yeniden doğrular; ilk karar ve rolling warm-start imzalarını kontrol eder; eski deneyle aynı tahmin fiyatlarını kullandığını sınar. HGB/ensemble maliyet ve çizelge eşitliği ayrı incelenir. 15/60 saniye ile ML/naive farkları ayrı CSV'lerdir. Yöntem özetleri `results.milp_summary_04`, karşılaştırmalar `results.milp_analysis_04` altında ayrı deney kimliğiyle iki kez yüklenip idempotans kontrol edilir. Eski deney dosyalarının hash'leri değişmemelidir. `manifest.json` çözüm kaynaklarını, `analysis_manifest.json` sonradan eklenen raporlama kodunu izler.
