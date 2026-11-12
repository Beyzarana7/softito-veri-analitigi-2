# WattRota — 60 saniyelik dört haftalık doğrudan MILP pilotu

Deney: `pilot04_60s_b8c91cd50d2b09b2`. Önceki deney: `pilot04_8ca16b7c875acecb`. Girdiler PostgreSQL okuma katmanından alındı; hash'ler önceki deneyle eşleşti. Haftalar: 5 Ocak, 23 Mart, 8 Haziran ve 24 Ağustos 2026.

## Protokol ve doğrulama

Her hafta bir oracle ve üç yöntem için d0/d1/d2 çözümü: 10 MILP; toplam 40. Gap hedefi 0,001; tek thread; seed 42; yerel arama kapalı; her çözüm en fazla 60 saniye. Açık döngü ve rolling ilk kararı ortaktır. Fiyattan bağımsız referans çözülmez; uygun plan olarak değerlendirilir. Naive, önceki son_yayinlanan_gun yöntemidir; açıklanmış günün profilini sonraki iki gün için tekrarlar.

İlk çözümlerin warm startı aynı PostgreSQL referansıdır. Önceki 15 saniyelik planlar kullanılmadı. Rolling yalnız kendi yönteminin önceki gün planıyla devam eder; uygulanmış saatler, stok, ayar, hazırlık ve minimum süre geçmişi sabitlenir. Her gün yalnız 24 saat uygulanır. Kalan son gün bütünüyle açıklanmış olduğundan d2 tahmin gerektirmez.

Her çözümün solver_objective_tl ve lower_bound_tl alanları o koşumun planlama fiyatlarına göredir. actual_cost_tl aynı planın gerçek fiyatlarla yeniden hesaplanan maliyetidir. Tahminli çözümün alt sınırı, gerçek fiyatlı regret hesabında kullanılmaz; bu hesap yalnız oracle alt sınırını kullanır.

40 plan bağımsız doğrulandı ve diskten yeniden doğrulandı. İhlal: 0. Warm-start denetimi: 40; bilinen fiyat öneki: 36; gerçek model hattında gelecek fiyatlarını bozma testi: üç yöntem. PostgreSQL çift yükleme içerik/sayı eşitliği geçti. 40 koşum + 32 haftalık politika + 8 yöntem özeti ayrı deney kimliğiyle saklandı. Eski deney dosyaları ve SQL kayıtları korundu.

## Gerçekleşen maliyet ve oracle belirsizliği

| policy | total_savings_tl | mean_actual_cost_tl | mean_oracle_incumbent_gap_tl | mean_regret_lower_tl | mean_regret_upper_tl | capture_vs_incumbent |
|---|---|---|---|---|---|---|
| ensemble_open | 0.00 | 472017.39 | 0.00 | 0.00 | 32082.10 | tanımsız |
| ensemble_rolling | 4601.63 | 470866.98 | -1150.41 | 0.00 | 30931.69 | tanımsız |
| hgb_open | 0.00 | 472017.39 | 0.00 | 0.00 | 32082.10 | tanımsız |
| hgb_rolling | 11179.35 | 469222.55 | -2794.84 | 0.00 | 29287.26 | tanımsız |
| naive_open | 0.00 | 472017.39 | 0.00 | 0.00 | 32082.10 | tanımsız |
| naive_rolling | 16365.45 | 467926.02 | -4091.36 | 0.00 | 27990.74 | tanımsız |
| oracle_incumbent | 0.00 | 472017.39 | 0.00 | 0.00 | 32082.10 | tanımsız |
| reference | 0.00 | 472017.39 | 0.00 | 0.00 | 32082.10 | tanımsız |

Tasarruf referans eksi politika maliyetidir. Negatif tasarruf gerçek fiyatlarla daha pahalı plan demektir. Oracle plana göre ham fark, kesin optimuma göre gerçek regret değildir. Oracle alt sınırı L ve bulunan uygun plan U için C* ∈ [L,U]; gerçek regret ∈ [max(0,C−U), max(0,C−L)]. Oracle sertifikalanmadıkça noktasal gerçek regret raporlanmaz. Bulunan oracle plandan daha ucuz bir tahminli plan, geçerli bir gözlemdir; negatif gerçek regret anlamına gelmez.

Kesin oracle sertifikası: 0/4. Oracle MIP gap aralığı: 0.03633–0.23625. Süre sınırına ulaşan koşum: 27/40. HiGHS 'Optimal' durumu yalnız göreli gap toleransına ulaşmış olabilir; kesin optimum diye adlandırılmaz.

Bilgi yakalama, toplam kazanç / toplam (referans−oracle bulunan plan) olarak hesaplanır; haftalık oran ortalaması alınmaz. Sıfır payda tanımsız bırakılır. Oracle optimumu kesin değilse bu bulunan plana göre oran da geçicidir. Gerçek oranın alt/üst sınırları policy_summary.csv içinde ayrıca tutulur. Gözlenen iki geçerli planın maliyet farkı hesaplanabilir; bu farkın gözlenmesi optimumun bilinmesini gerektirmez.

## 15 ve 60 saniye karşılaştırması

| policy | saving_from_60s_tl |
|---|---|
| ensemble_open | 0.00 |
| ensemble_rolling | 3126.99 |
| hgb_open | 0.00 |
| hgb_rolling | 9704.71 |
| oracle_incumbent | 0.00 |
| reference | 0.00 |

Pozitif değer, aynı dört hafta/politikada 60 saniyelik koşumun toplam gerçek maliyetinin daha düşük olduğunu gösterir. İki deneyin en iyi planları birleştirilmedi. Naive 15 saniyelik deneyde olmadığından onun için süre karşılaştırması yapılamaz. Detay: budget_comparison.csv ve budget_schedules.csv.

Aynı başlangıç karar problemlerinde (oracle ve HGB/ensemble d0, 12 eşleşme) ortalama gap: 15 s 0.06753, 60 s 0.06626. Rolling d1/d2, farklı geçmiş planlar nedeniyle farklı kalan uygun çözüm kümelerine sahip olabilir; bu alt sınırlar aynı problemin iyileşmesi gibi yorumlanmaz.

## HGB ve ensemble: maliyet mi, çizelge mi aynı?

| seconds | identical_costs | identical_full_schedules | comparisons | identical_machine_schedules |
|---|---|---|---|---|
| 15 | 8 | 8 | 8 | 8 |
| 60 | 5 | 5 | 8 | 5 |

Her süre için dört hafta × iki politika = sekiz karşılaştırma. Tam eşitlik hem kaynak/saat faaliyetlerini (ürün ve iş emri dahil), hem sipariş/kaynak/saat yükleme miktarlarını gerektirir; yükleme toleransı 10⁻⁶ ton. Aynı maliyet, aynı çizelge varsayılmadı. Ayrıntı: hgb_ensemble_schedules.csv.

## Basit yönteme karşı ML

| mode | source | naive_minus_ml_tl | weeks_ml_cheaper | weeks_same_cost | weeks_naive_cheaper |
|---|---|---|---|---|---|
| open | ensemble | 0.00 | 0 | 4 | 0 |
| open | hgb | 0.00 | 0 | 4 | 0 |
| rolling | ensemble | -11763.82 | 2 | 0 | 2 |
| rolling | hgb | -5186.10 | 1 | 1 | 2 |

Pozitif değer ML planının basit yöntemden daha ucuz olduğunu, negatif değer basit yöntemin daha ucuz olduğunu gösterir. Bu, dört haftanın sabit seed/süre koşullarındaki gözlenen farkıdır. Rolling avantajı doğrudan ML katkısı değildir: yeni açıklanan fiyatların ve ek çözüm bütçesinin etkisi henüz ayrıştırılmamıştır. Yöntem farklarının çözücü seedlerine dayanıklılığı da bu pilotla kanıtlanmaz.

## Maliyet kalemleri

| policy | operating_electricity_tl | startup_electricity_tl | transition_electricity_tl | startup_non_electric_tl | transition_non_electric_tl | plan_change_tl | total_cost_tl |
|---|---|---|---|---|---|---|---|
| ensemble_open | 1846964.22 | 7035.41 | 25749.92 | 5880.00 | 2440.00 | 0.00 | 1888069.54 |
| ensemble_rolling | 1841173.40 | 7043.81 | 26605.69 | 6130.00 | 2515.00 | 0.00 | 1883467.91 |
| hgb_open | 1846964.22 | 7035.41 | 25749.92 | 5880.00 | 2440.00 | 0.00 | 1888069.54 |
| hgb_rolling | 1832748.33 | 7338.21 | 27758.66 | 6420.00 | 2625.00 | 0.00 | 1876890.19 |
| naive_open | 1846964.22 | 7035.41 | 25749.92 | 5880.00 | 2440.00 | 0.00 | 1888069.54 |
| naive_rolling | 1828725.86 | 7741.20 | 26302.02 | 6460.00 | 2475.00 | 0.00 | 1871704.09 |
| oracle_incumbent | 1846964.22 | 7035.41 | 25749.92 | 5880.00 | 2440.00 | 0.00 | 1888069.54 |
| reference | 1846964.22 | 7035.41 | 25749.92 | 5880.00 | 2440.00 | 0.00 | 1888069.54 |

Operating electricity: üretim, yükleme ve temel yük elektriği. Startup electricity: açılış ek enerjisi. Transition electricity: hazırlık sırasındaki enerji. Son iki olayın elektrik dışı giderleri ayrı sütunlardır. Bu altı kalem toplanır; total_electricity_tl ilk üç elektrik sütununun toplamıdır, ikinci kez eklenmez. Plan değişikliği modelde sıfır TL/kaynak-saat parametresiyle bulunur; sıfır korunmuştur. Saatlik kalemler bağımsız doğrulayıcı maliyetine eşleştirildi.

## Ölçülen süre ve kapsam

40 MILP pilotu: 31.47 dakika. Son kontrol/raporlama: 0.51 dakika (MILP içermez). Üç tahmin yöntemli 34 hafta, 340 MILP için ölçülen hafta ortalamasından tahmin: 267.19 dakika. Gözlenen en kısa/uzun haftanın ölçeklenmesi: [262.41976481661357, 272.9397776899976] dakika; güven aralığı değildir. Sadece çözücü limitlerinin toplam üst bütçesi 340 dakikadır; hazırlama/tahmin/doğrulama ayrıca zaman alır.

34 hafta, kilitli test, duyarlılık deneyi, Görev 5 ve stokastik mod çalıştırılmadı. Commit için kullanıcı onayı gerekir.

## Önerilen çözücü duyarlılık deneyi — çalıştırılmadı

Önceden yazılan seçim kuralı: geliştirme döneminin içinden yaklaşık eşit aralıklı fold 5, 16, 28. Tarihler: ['2026-02-09 00:00:00', '2026-04-27 00:00:00', '2026-07-20 00:00:00']. Seed'ler: [7, 19, 42, 73, 101]. Bu seçim maliyet sonuçlarına göre yapılmadı; geliştirme verisinin daha önce görülmüş olduğu gerçeğini değiştirmez. Onayla sabitlenecek protokol: üç hafta × beş seed × (oracle + naive/HGB/ensemble açık döngü) = 60 MILP; her biri 60 saniye; rolling eklenmez. Tüm seed sonuçları raporlanır, en iyi seed seçilmez. Maliyet/gap dağılımı, plan eşitliği ve ML−naive farkının işaret kararlılığı incelenir.

HiGHS random_seed seçeneği her çözümde setOptionValue ile atanıp getOptionValue ile geri okundu; kabul durumu ve etkili seed 42 tüm 40 kayıtta doğrulandı. Bu yalnız config alanı değildir. Ancak seed değiştirildiğinde sonuçların gerçekten ne kadar değiştiği henüz deneyle ölçülmedi.

## Stokastik mod

Önceki senaryo kapsaması %61,89 olduğu için henüz önerilmez. Önce deterministik çözüm kalitesi ve seed duyarlılığı anlaşılmalı. Tek sabit çizelgede doğrusal senaryo ortalama maliyeti yalnız ortalama fiyatla çözmeye eşdeğerdir; ek değer iddiası için kalibrasyon ve recourse veya risk hedefi gerekir.
