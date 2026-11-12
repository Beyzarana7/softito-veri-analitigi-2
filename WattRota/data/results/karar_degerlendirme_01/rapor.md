# Karar odaklı değerlendirme

Dönem: 2026-01-05–2026-11-02; 44 haftalık karar, 19 aday plan.

## Kapsam ve tanımlar

- Bu çalışma mevcut tahminleri yeniden değerlendirir; yeni model eğitmez. 2026 dönemi önceden görülmüştür.
- Oracle yerine **havuz-oracle** kullanılır: aynı 19 geçerli planın gerçekleşmiş fiyatlarla en ucuzu. Tam MILP oracle maliyeti değildir; tam çözüm uzayındaki regret ve bilgi yakalama oranı burada hesaplanmış sayılmaz.
- Havuz regret = seçilen planın gerçekleşmiş maliyeti − havuz-oracle maliyeti. Bilgi değeri yakalama = (referans − seçilen)/(referans − havuz-oracle). Payda 0,02 TL veya altındaysa oran tanımsızdır; 0 yazılmaz. Negatif oranlar kırpılmaz.
- Saatlik fiyat metrikleri yalnız tahmin edilen 48 saati kapsar. Yük ağırlıklı MAE = Σ(yük × mutlak fiyat hatası)/Σyük; kWh/kWh ağırlıklarıyla sonuç TL/MWh olur. Birincil ağırlık sabit referans yüküdür; seçilen plan yükü ayrıca raporlanır.
- Spearman: 48 saatlik fiyat sıralaması ve ayrıca 19 planın maliyet sıralaması. Sabit dizide korelasyon tanımsız bırakılır.
- En ucuz k: iki hedef günün her birinde k=6. Tahmin eşitlikleri saat sırasıyla çözülür; gerçek fiyatın k sınırındaki eşitliklere kesirli kredi dağıtılır. Saat sırasına göre deterministik örtüşme de ayrı sütundadır.
- Haftalık oranların ortalaması ile toplam kazanç/toplam bilgi değeri ayrı raporlanır. Küçük pozitif paydalı bir haftadaki kayıp, haftalık oran ortalamasını çok negatif yapabilir. Toplam oran bu küçük paydalara eşit ağırlık vermez; iki değer aynı ölçü değildir.
- Bootstrap aynı haftaların A−B maliyet farklarını birlikte örnekler; 10.000 tekrar ve seed=42 kullanılır. IID varsayımına ek olarak ardışık 4 haftalık hareketli blok duyarlılığı gösterilir. Aralıklar bu retrospektif örneklemin belirsizliğidir; gelecek kazanç garantisi veya çoklu test düzeltilmiş anlamlılık sonucu değildir.

## Model özeti

| Yöntem | Regret TL/hafta | Toplam bilgi yakalama | Yük ağırlıklı MAE | Fiyat Spearman | Ucuz 6 saat oranı |
|---|---:|---:|---:|---:|---:|
| hgb_duzeltme_365 | 827.48 | 0.756 | 459.76 | 0.778 | 0.694 |
| random_forest_365gun | 562.52 | 0.834 | 506.11 | 0.763 | 0.664 |
| son_yayinlanan_gun | 561.17 | 0.835 | 574.17 | 0.731 | 0.633 |

## Eşleştirilmiş maliyet farkları

| A − B | Bootstrap | Ortalama TL/hafta | %95 aralık |
|---|---|---:|---|
| son_yayinlanan_gun − random_forest_365gun | paired_iid | -1.34 | [-228.46, 240.48] |
| son_yayinlanan_gun − random_forest_365gun | paired_moving_block | -1.34 | [-186.07, 224.50] |
| son_yayinlanan_gun − hgb_duzeltme_365 | paired_iid | -266.31 | [-632.04, 15.87] |
| son_yayinlanan_gun − hgb_duzeltme_365 | paired_moving_block | -266.31 | [-616.32, -21.50] |
| random_forest_365gun − hgb_duzeltme_365 | paired_iid | -264.96 | [-669.07, 75.02] |
| random_forest_365gun − hgb_duzeltme_365 | paired_moving_block | -264.96 | [-688.49, 65.63] |

## Doğrulama

Her haftanın referans, havuz-oracle ve seçilen planları bağımsız fiziksel/maliyet doğrulamasından geçirildi (108 benzersiz hafta-plan kontrolü). Matris maliyetleri ve seçimler kayıtlı deneyle karşılaştırıldı. Girdi dosyalarının çalışma öncesi ve sonrası SHA-256 özetleri eşleşti.

Haftalık tam-MILP oracle serisi mevcut olmadığından bu kapsamın dışındaki oracle/regret sonuçları üretilmedi. Üç ayrı tarihsel MILP örneği 44 haftaya genellenmedi.
