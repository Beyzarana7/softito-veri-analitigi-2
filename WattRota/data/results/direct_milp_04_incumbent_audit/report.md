# WattRota — rolling planlarının özgün tam MILP denetimi

Ana deney: pilot04_60s_b8c91cd50d2b09b2. Ayrı denetim: posthoc04_7dbb0fb5d251c8f4. Yeni optimizasyon çağrısı: 0. Ham deney dosyaları korunmuştur.

## Özgün modelde aday uygunluğu

Rolling planlar d0 çözümünün ilk 24, d1 çözümünün ikinci 24 ve d2 çözümünün son 24 saatinin birleştirilmesiyle yeniden kuruldu; yalnız d2 dosyasının doğrulanmasına dayanılmadı. Başlangıçtaki PostgreSQL firma verisi, gerçek 72 saatlik PTF ve özgün src/firma_cizelgeleme.py formülasyonu kullanıldı. Geçmiş sabitlemesi olmayan tam 72 saatlik model kuruldu. Her adayın matrisi, sınırları ve amaç katsayıları referans modelle birebir karşılaştırıldı.

Model kaynağına dokunulmadı. AST üzerinden yalnız aday vektörü ve model matrisi alınacak kesim uygulandı; modeldeki fiziksel kısıtlar değiştirilmedi. Pahalı adayları erken reddeden başlangıç maliyeti kontrolü fizibilite kısıtı olmadığı için denetim kopyasında atlandı. Aday vektörü, bütün A·x satırları, değişken alt/üst sınırları ve tamsayılılıkla sayısal olarak sınandı; c·x + sabit bedel bağımsız maliyetle karşılaştırıldı. HiGHS kurucusu testte engellendi: solver başlatılamaz.

Denetlenen politika: 32; rolling: 12; uygun aday: 32; ihlal: 0. Detaylar candidate_audit.csv, yeniden birleştirilmiş planlar tarih klasörleri, hata listesi violations.json içindedir. Satır/değişken toleransı 10⁻⁵; amaç eşleşmesi 0,02 TL.

Her adayda 8637 kısıt satırı ve 5278 değişken denetlendi. En büyük satır ihlali artık değeri 3.208e-09; en büyük amaç farkı 1.164e-10 TL.

| week | policy | full_model_feasible | matrix_objective_tl | objective_difference_tl |
|---|---|---|---|---|
| 2026-01-05 | reference | True | 652231.62 | 0.00 |
| 2026-01-05 | oracle_incumbent | True | 652231.62 | 0.00 |
| 2026-01-05 | hgb_open | True | 652231.62 | 0.00 |
| 2026-01-05 | hgb_rolling | True | 651066.87 | -0.00 |
| 2026-01-05 | ensemble_open | True | 652231.62 | 0.00 |
| 2026-01-05 | ensemble_rolling | True | 651066.87 | -0.00 |
| 2026-01-05 | naive_open | True | 652231.62 | 0.00 |
| 2026-01-05 | naive_rolling | True | 645072.43 | 0.00 |
| 2026-03-23 | reference | True | 327087.60 | 0.00 |
| 2026-03-23 | oracle_incumbent | True | 327087.60 | 0.00 |
| 2026-03-23 | hgb_open | True | 327087.60 | 0.00 |
| 2026-03-23 | hgb_rolling | True | 319998.98 | 0.00 |
| 2026-03-23 | ensemble_open | True | 327087.60 | 0.00 |
| 2026-03-23 | ensemble_rolling | True | 326961.87 | 0.00 |
| 2026-03-23 | naive_open | True | 327087.60 | 0.00 |
| 2026-03-23 | naive_rolling | True | 318065.50 | 0.00 |
| 2026-06-08 | reference | True | 214852.00 | 0.00 |
| 2026-06-08 | oracle_incumbent | True | 214852.00 | 0.00 |
| 2026-06-08 | hgb_open | True | 214852.00 | 0.00 |
| 2026-06-08 | hgb_rolling | True | 211999.94 | -0.00 |
| 2026-06-08 | ensemble_open | True | 214852.00 | 0.00 |
| 2026-06-08 | ensemble_rolling | True | 212057.07 | 0.00 |
| 2026-06-08 | naive_open | True | 214852.00 | 0.00 |
| 2026-06-08 | naive_rolling | True | 214741.76 | 0.00 |
| 2026-08-24 | reference | True | 693898.32 | 0.00 |
| 2026-08-24 | oracle_incumbent | True | 693898.32 | 0.00 |
| 2026-08-24 | hgb_open | True | 693898.32 | 0.00 |
| 2026-08-24 | hgb_rolling | True | 693824.40 | 0.00 |
| 2026-08-24 | ensemble_open | True | 693898.32 | 0.00 |
| 2026-08-24 | ensemble_rolling | True | 693382.09 | 0.00 |
| 2026-08-24 | naive_open | True | 693898.32 | 0.00 |
| 2026-08-24 | naive_rolling | True | 693824.40 | 0.00 |

## Doğrulanmış en iyi bilinen gerçek-fiyatlı uygun maliyet

Her hafta yalnız aynı 60 saniyelik deneyin uygunluğu tam modelde doğrulanmış referans, özgün oracle sonucu ve altı politika planı arasındaki en düşük maliyet alındı. Başka süre bütçelerinden plan seçilmedi. Bu değer özgün oracle koşumunun sonucu olarak yeniden adlandırılmadı; oracle maliyeti ve alt sınırı değişmedi.

| week | original_oracle_upper_tl | verified_best_known_feasible_cost_tl | improvement_over_oracle_incumbent_tl | winning_policies | oracle_lower_bound_tl |
|---|---|---|---|---|---|
| 2026-01-05 | 652231.62 | 645072.43 | 7159.19 | naive_rolling | 628538.00 |
| 2026-03-23 | 327087.60 | 318065.50 | 9022.10 | naive_rolling | 303321.16 |
| 2026-06-08 | 214852.00 | 211999.94 | 2852.06 | hgb_rolling | 164093.83 |
| 2026-08-24 | 693898.32 | 693382.09 | 516.23 | ensemble_rolling | 663788.14 |

## Sıkılaştırılmış regret aralıkları

L özgün oracle alt sınırı, U doğrulanmış en iyi bilinen uygun maliyet, C politika maliyeti olsun. C* ∈ [L,U] ve regret ∈ [max(0,C−U), max(0,C−L)]. Daha iyi uygun üst sınır regret aralığının alt ucunu yükseltebilir; optimumun alt sınırı L değişmediğinden üst uç değişmez. En iyi bilinen plana fark kesin gerçek regret değildir.

| policy | old_regret_lower_tl | old_regret_upper_tl | tightened_regret_lower_tl | tightened_regret_upper_tl |
|---|---|---|---|---|
| ensemble_open | 0.00 | 32082.10 | 4887.40 | 32082.10 |
| ensemble_rolling | 0.00 | 30931.69 | 3736.99 | 30931.69 |
| hgb_open | 0.00 | 32082.10 | 4887.40 | 32082.10 |
| hgb_rolling | 0.00 | 29287.26 | 2092.56 | 29287.26 |
| naive_open | 0.00 | 32082.10 | 4887.40 | 32082.10 |
| naive_rolling | 0.00 | 27990.74 | 796.03 | 27990.74 |
| oracle_incumbent | 0.00 | 32082.10 | 4887.40 | 32082.10 |
| reference | 0.00 | 32082.10 | 4887.40 | 32082.10 |

Hafta bazındaki sıkılaştırılmış aralıklar:

| week | policy | actual_cost_tl | tightened_regret_lower_tl | tightened_regret_upper_tl |
|---|---|---|---|---|
| 2026-01-05 | reference | 652231.62 | 7159.19 | 23693.62 |
| 2026-01-05 | oracle_incumbent | 652231.62 | 7159.19 | 23693.62 |
| 2026-01-05 | hgb_open | 652231.62 | 7159.19 | 23693.62 |
| 2026-01-05 | hgb_rolling | 651066.87 | 5994.45 | 22528.88 |
| 2026-01-05 | ensemble_open | 652231.62 | 7159.19 | 23693.62 |
| 2026-01-05 | ensemble_rolling | 651066.87 | 5994.45 | 22528.88 |
| 2026-01-05 | naive_open | 652231.62 | 7159.19 | 23693.62 |
| 2026-01-05 | naive_rolling | 645072.43 | 0.00 | 16534.43 |
| 2026-03-23 | reference | 327087.60 | 9022.10 | 23766.44 |
| 2026-03-23 | oracle_incumbent | 327087.60 | 9022.10 | 23766.44 |
| 2026-03-23 | hgb_open | 327087.60 | 9022.10 | 23766.44 |
| 2026-03-23 | hgb_rolling | 319998.98 | 1933.48 | 16677.82 |
| 2026-03-23 | ensemble_open | 327087.60 | 9022.10 | 23766.44 |
| 2026-03-23 | ensemble_rolling | 326961.87 | 8896.37 | 23640.71 |
| 2026-03-23 | naive_open | 327087.60 | 9022.10 | 23766.44 |
| 2026-03-23 | naive_rolling | 318065.50 | 0.00 | 14744.34 |
| 2026-06-08 | reference | 214852.00 | 2852.06 | 50758.17 |
| 2026-06-08 | oracle_incumbent | 214852.00 | 2852.06 | 50758.17 |
| 2026-06-08 | hgb_open | 214852.00 | 2852.06 | 50758.17 |
| 2026-06-08 | hgb_rolling | 211999.94 | 0.00 | 47906.11 |
| 2026-06-08 | ensemble_open | 214852.00 | 2852.06 | 50758.17 |
| 2026-06-08 | ensemble_rolling | 212057.07 | 57.13 | 47963.24 |
| 2026-06-08 | naive_open | 214852.00 | 2852.06 | 50758.17 |
| 2026-06-08 | naive_rolling | 214741.76 | 2741.82 | 50647.93 |
| 2026-08-24 | reference | 693898.32 | 516.23 | 30110.18 |
| 2026-08-24 | oracle_incumbent | 693898.32 | 516.23 | 30110.18 |
| 2026-08-24 | hgb_open | 693898.32 | 516.23 | 30110.18 |
| 2026-08-24 | hgb_rolling | 693824.40 | 442.31 | 30036.26 |
| 2026-08-24 | ensemble_open | 693898.32 | 516.23 | 30110.18 |
| 2026-08-24 | ensemble_rolling | 693382.09 | 0.00 | 29593.95 |
| 2026-08-24 | naive_open | 693898.32 | 516.23 | 30110.18 |
| 2026-08-24 | naive_rolling | 693824.40 | 442.31 | 30036.26 |

Bu üst sınır deney sonrasında ve değerlendirilen politika planları da kullanılarak oluşturuldu. Ona göre bir bilgi yakalama oranı bağımsız oracle başarısı sayılamaz. Burada yeni bir bağımsız bilgi yakalama oranı üretilmedi; ham deneyin sıfır paydalı oranı tanımsız kalır.

## Oracle ve açık döngü neden referansta kaldı?

İncelenen başlangıç koşumu: 16 (4 oracle + 12 açık döngü). Süre sınırında durma: 16. Son düğüm sayısı aralığı: 2–2. Planlama amacında gözlenen en büyük referans iyileşmesi: 0.000000 TL. Solver amacı/bağımsız planlama maliyeti farkı en çok 0.000000000 TL.

| week | run_key | solver_seconds | mip_node_count | planning_improvement_tl | objective_accounting_difference_tl |
|---|---|---|---|---|---|
| 2026-01-05 | oracle | 60.02 | 2 | 0.00 | 0.00 |
| 2026-01-05 | hgb_d0 | 60.02 | 2 | 0.00 | 0.00 |
| 2026-01-05 | ensemble_d0 | 60.02 | 2 | 0.00 | 0.00 |
| 2026-01-05 | naive_d0 | 60.02 | 2 | 0.00 | 0.00 |
| 2026-03-23 | oracle | 60.02 | 2 | 0.00 | 0.00 |
| 2026-03-23 | hgb_d0 | 60.02 | 2 | 0.00 | 0.00 |
| 2026-03-23 | ensemble_d0 | 60.02 | 2 | -0.00 | 0.00 |
| 2026-03-23 | naive_d0 | 60.02 | 2 | 0.00 | 0.00 |
| 2026-06-08 | oracle | 60.02 | 2 | 0.00 | 0.00 |
| 2026-06-08 | hgb_d0 | 60.04 | 2 | 0.00 | 0.00 |
| 2026-06-08 | ensemble_d0 | 60.02 | 2 | 0.00 | -0.00 |
| 2026-06-08 | naive_d0 | 60.02 | 2 | 0.00 | 0.00 |
| 2026-08-24 | oracle | 60.02 | 2 | 0.00 | 0.00 |
| 2026-08-24 | hgb_d0 | 60.02 | 2 | -0.00 | 0.00 |
| 2026-08-24 | ensemble_d0 | 60.03 | 2 | 0.00 | 0.00 |
| 2026-08-24 | naive_d0 | 60.02 | 2 | 0.00 | 0.00 |

Kaynak kod referansı bağımsız ve bütün model satırlarıyla kontrol ettikten sonra setSolution çağırıyor. Kayıtlarda warm-start maliyeti ve imzası var; fakat setSolution dönüş kodu/kabul mesajı saklanmamış. Bu yüzden native API kabulünü doğrudan eski logdan doğrulamak mümkün değil. Son uygun planın referansla eşleşmesi kabul ile uyumludur; tek başına kabul mesajının yerine geçmez.

Ayrıntılı solver.log dosyası yok; bulunan toplam uygun çözüm sayısı, incumbent değişim sayısı ve primal/dual zaman izleri kaydedilmemiş. Uygun bir son incumbent bulunduğu biliniyor; toplam kaç uygun aday bulunduğu bilinmiyor. “Yalnız bir uygun çözüm buldu” veya “hiç arama yapmadı” denemez. Son düğüm sayıları aramanın gerçekleştiğine kanıt sağlar; hangi heuristic/cut/presolve darboğazının etkili olduğu mevcut kayıttan belirlenemez.

Kesin bulgu, bu bütçe ve seed ile başlangıç referansından daha iyi bir son incumbent raporlanmadığı ve aramanın süre sınırında durduğudur. Bunun daha ucuz uygun plan bulunmamasından kaynaklandığı söylenemez: doğrulanmış rolling planları aynı tam modele daha ucuz adaylar sağlıyor. Bu denetim, gizli bir fiziksel kısıt ya da amaç muhasebesi farkını neden olarak desteklemiyor. Tahminli d0 amaçları gerçek-fiyatlı oracle amaçlarından farklıdır; gerçekleşen maliyet ile planlama amacı arasındaki fark tek başına muhasebe hatası değildir.

## Rolling dahil seed duyarlılık önerisi — çalıştırılmadı

Aynı önceden önerilen üç geliştirme haftası: ['2026-02-09', '2026-04-27', '2026-07-20']; fold 5, 16, 28. Seed'ler: [7, 19, 42, 73, 101]. Her hafta/seed çifti için 1 oracle + 3 yöntem × d0/d1/d2 = 10 MILP. D0 açık döngü ve rolling için ortaktır. Toplam 3 × 5 × 10 = 150 MILP. Her çözüm 60 saniye; solver limitleri toplamı 150 dakika. Önceki pilotun ölçülen hızından yaklaşık 118.0 dakika; hazırlama ve ayrıntılı log maliyetleri nedeniyle bu bir kesin süre değildir.

Üç yöntemin tahminleri her hafta/gün için bir kez üretilecek ve seedler boyunca sabit tutulacak. Her d0 aynı özgün referansla başlayacak. D1/d2 yalnız aynı hafta/yöntem/seed zincirinin önceki planından devam edecek. Eski pilotun ya da başka seedin iyi planı warm start olmayacak. Her seedin açık döngü ve rolling maliyeti, ML−naive farkı, rolling−open farkı, stok/geçmiş devamlılığı, gap ve tam-model uygunluğu ayrı raporlanacak. Bütün 15 hafta/seed çifti gösterilecek; en iyi seed seçilmeyecek. Ortalama/medyan ve dağılım yalnız tanımlayıcı özet olacak.

Yeni günlükler: setSolution dönüşü; seedin model aktarımı öncesi/sonrası ve solve öncesi/sonrası geri okunması; incumbent olay sayısı ve amaç/zaman izi; primal/dual izleri; node/LP sayaçları ve durma nedeni. API bir toplam uygun çözüm sayısı sağlamıyorsa callback olay sayısı bunun yerine aynı şeymiş gibi sunulmayacak. Rolling–open farkında yeni bilgi ve ek hesap bütçesi yine birlikte değişir; bu öneri bunların nedensel ayrıştırmasını sağlamaz.

## 34 hafta mevcut sistemle neyi ölçer?

Sabit firma senaryosu, bilgi zamanları, 60 saniyelik bütçe ve seed 42 altında üç yöntemin açık döngü/rolling gerçekleşen PTF-temelli maliyetini; haftalar arası değişimi; basit yönteme karşı ML farkını; süre sınırlı çözücü gaplerini ve doğrulanmış uygun maliyet sınırlarını ölçebilir. Referans ve yöntemler arasındaki gözlenen maliyet farkları, optimum bilinmese de geçerli planlar üzerinde hesaplanabilir.

Global optimum ve gerçek regretin noktasal değeri; solver seedine/arama yoluna dayanıklılık; rolling kazancının bilgi güncellemesi ile ek çözüm bütçesine ayrı payları; sentetik firmanın gerçek tesise aktarılabilirliği belirsiz kalır. 34 hafta geliştirme dönemidir ve daha önce görülmüştür; yeni bağımsız test diye sunulamaz. Daha geniş geliştirme çalışması bu belirsizlikleri tek başına gidermez.

34 hafta, 150 MILP seed önerisi ve Görev 5 başlatılmadı. Bu ek denetimin dosyaları ayrı commit onayı bekler.
