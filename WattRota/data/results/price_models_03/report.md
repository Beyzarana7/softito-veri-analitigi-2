# Fiyat tahmini geliştirme — görev 3

Yalnız 34 geliştirme haftası kullanıldı. Kilitli son 10 hafta açılmadı. 2026 daha önce görülmüştür; sonuçlar yeni kör test değildir. Model/alpha seçimiyle aynı geliştirme dönemindeki skor ve p-değerleri keşifseldir.

## Yöntemler ve sınırlar

- LEAR tarzı yöntem: her saat ve gün ufku için ayrı standartlaştırılmış Lasso-AR. Bu, literatürdeki LEAR yaklaşımından esinlenen bağımsız uyarlamadır; orijinal AIC/asinh/dış değişkenli modelin birebir yeniden üretimi değildir.
- Seviye ve profil hedefleri ayrı denendi. Tarihsel profil gerçek günlük ortalamaya bölünür; ileri günde gerçek ortalama kullanılmaz. Ayrı bir model günlük ortalamayı tahmin eder; profil yeniden normalize edilip bu tahminle ölçeklenir. Sıfıra yakın tarihsel ortalamalar için epsilon=1 TL/MWh kullanılır.
- Dünkü aynı saat kıyası ikinci bilinmeyen gün için özyinelemelidir; henüz açıklanmamış dünkü gerçek fiyat kullanılmaz. Geçen hafta aynı saat ve 28 günlük hafta içi/sonu ortalamaları ayrıca raporlanır.
- Karar örnekleri pazartesi başladığı için tahmin hedefleri salı/çarşambadır. Hafta içi/sonu yönteminin hafta sonu dalı birim testinde sınanır; bu 34 haftalık deney hafta sonu tahmin başarısını ölçmez.
- Tatiller Diyanet ve 2429 sayılı kanun kaynaklarına dayalıdır. Yarım günler saat 13.00 sonrası işaretlenir. İdari izinler ve tesise özgü tatil/çalışma takvimi fiyat tahminine otomatik eklenmez.
- LightGBM sıfır sınıflandırması + pozitif fiyat modeli ile iki aşamalı tahmin üretir. Sabit eşik 0,5. Ensemble ağırlıkları eşittir ve config içinde önceden sabittir.
- EPİAŞ yük tahmini API denemesi kimliksiz HTTP 401 döndürdü. Yetkili TGT bulunmadığından yük/rüzgâr/güneş tahminleri ve yayımlanma anına ait tarihsel sürümleri edinilmedi. Gerçekleşmiş değerler yerine kullanılmadı. Dış değişken katkısı sınanmış sayılmaz.

## Geliştirme skorları

| Model | MAE | RMSE | Yakınsama uyarısı |
|---|---:|---:|---:|
| ensemble_level_fixed | 480.13 | 682.81 | 0 |
| lear_level_1 | 491.62 | 685.30 | 0 |
| hgb_expanding_cached | 492.64 | 715.24 | 0 |
| lear_level_10 | 495.03 | 688.22 | 0 |
| lightgbm_level | 519.24 | 739.34 | 0 |
| lightgbm_two_stage | 524.96 | 749.20 | 0 |
| naive_weektype_28d | 565.52 | 788.12 | 0 |
| ensemble_profile_fixed | 573.74 | 797.39 | 0 |
| naive_yesterday_recursive | 582.62 | 849.50 | 0 |
| lightgbm_profile | 586.85 | 826.02 | 0 |
| lear_profile_0.01 | 589.25 | 808.34 | 0 |
| lear_profile_0.001 | 606.59 | 833.25 | 0 |
| naive_previous_week | 645.21 | 957.92 | 0 |

Geliştirme seçimi: **ensemble_level_fixed**. Üretim maliyeti üstünlüğü ölçülmedi.

## DM değerlendirmesi

Her karar haftasının 48 saatlik mutlak hataları ortalanır. DM, bu 34 eşleştirilmiş haftalık kayıp farkı üzerinde asimptotik normal dağılım ve Newey–West/Bartlett HAC (0 ve 3 hafta) ile hesaplanır. Saatler arası veya haftalar arasındaki boşluklar yapay biçimde kesintisiz 1.632 saat gibi ele alınmaz. Her HAC ayarı için bütün ikililere Holm düzeltmesi uygulanır. Küçük örneklem, model/alpha seçimi ve önceden görülmüş dönem nedeniyle sonuçlar keşifseldir; nihai test anlamlılığı değildir. Sıfır uzun dönem varyansında tanımsız durum gizlenmez.
Bütün karşılaştırmalar `dm_tests.csv` dosyasındadır; negatif fark A tahmininin daha düşük kayıp verdiğini gösterir.

## Olasılıksal tahmin

Sabit LightGBM-seviye modeli için 2025 son çeyreğinin 12 haftasında gerçek zamanlı bilgi kesimli OOS tahminler üretildi. Her geliştirme haftasında yalnız daha önce gerçekleşmiş 48 saatlik artık yolları eklenir. 30 tam yol örneklenir; böylece yol içi saat ilişkisi korunur. İlk 24 saat her senaryoda açıklanmış fiyatla aynıdır. Negatif senaryo fiyatları sıfırda kırpılır. Bu ampirik artık bootstrap yaklaşımı rejim değişimlerini veya kuyruk risklerini garanti etmez.
%10–%90 aralığı kapsaması: 0.619; ortalama genişlik: 991.94 TL/MWh. Nominal hedef %80; ölçülen kapsama bunun yerine kullanılır.
Sıfır tahmini F1: 0.512; Brier: 0.0237; gerçek sıfır saat: 77; tahmin edilen sıfır saat: 52.

Kaynak bağlantıları deney klasöründeki `sources.json` dosyasındadır. Eski config, kaynak ve sonuçlar değiştirilmedi.

## Sonuçların yorumu

Sabit ağırlıklı ensemble geliştirmede en düşük MAE'yi verdi (480.13 TL/MWh). Önceki HGB: 492.64; dünkü gün kıyası: 582.62.
Ensemble–HGB için 3 hafta HAC DM p=0.0405, Holm p=1.0000. Çoklu karşılaştırma sonrasında HGB'ye üstünlük gösterilmedi. Ensemble–dünkü gün için Holm p=0.0034; bu yalnız keşifsel geliştirme dönemi karşılaştırmasıdır.
Normalize profil ve iki aşamalı sıfır modeli seviye modellerini iyileştirmedi. Bu olumsuz sonuçlar korunmuştur.
Senaryo nominal %80 aralığının kapsaması %61.89; kapsama yetersizdir. Bu senaryolar güvenilir biçimde kalibre edilmiş bir risk dağılımı olarak sunulmamalıdır. Fiyat üst limitlerinin tarihsel sürümleri uygulanmamıştır.
training_audit içindeki training_rows/training_last_label ortak uygun eğitim havuzunu tanımlar; naive veya cached model için yeni fit yapıldığı anlamına gelmez.
Tam ayarlı gelecek-bozma tekrarında 13 yöntemin kayıtlı tahminleri eşleşti. Senaryoların ilk günü, olasılık toplamları, geçmiş artık zamanları ve son haftanın 30 yolu yeniden doğrulandı.
