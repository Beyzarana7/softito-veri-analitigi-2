# Görev 3 tahminlerinin geliştirme dönemindeki karar karşılaştırması

Yalnız 5 Ocak–24 Ağustos 2026 arasındaki 34 geliştirme haftası kullanıldı. Son 10 kilitli hafta puanlanmadı. Görev 4 başlatılmadı; yeni tahmin modeli veya MILP çözümü üretilmedi.

Regret = seçilen planın gerçek maliyeti − 19 plan içindeki gerçek minimum. Bilgi değeri yakalama = (referans − seçilen)/(referans − havuz minimumu). Bunlar tam MILP oracle metrikleri değildir. Lasso alpha=1, Görev 3 geliştirme MAE sonucundan sabitlendi; maliyet karşılaştırmasına göre yeniden seçilmedi.

| Yöntem | MAE | Ortalama regret TL | Toplam bilgi yakalama | Haftalık oran ortalaması | Tanımlı hafta |
|---|---:|---:|---:|---:|---:|
| ensemble_level_fixed | 480.13 | 719.35 | 0.7071 | 0.1871 | 33 |
| hgb_expanding_cached | 492.64 | 641.64 | 0.7388 | 0.2160 | 33 |
| lear_level_1 | 491.62 | 755.23 | 0.6925 | -0.4575 | 33 |
| naive_yesterday_recursive | 582.62 | 662.18 | 0.7304 | 0.0457 | 33 |

## Yorumlama ve kontrol

Payda 0,02 TL veya altındaysa bilgi oranı tanımsızdır; sıfıra çevrilmez. Negatif oranlar kırpılmaz. Küçük paydalı kayıplar haftalık oran ortalamasını çok negatif yapabilir; toplam oranla aynı ölçü değildir.
İlk günün açıklanmış fiyatı bütün yöntemlerde aynıdır. Sonraki 48 saat kayıtlı tahminlerden alınır. Gelecek gerçek fiyat yalnız seçilen planın puanlanması ve havuz-oracle hesabında kullanılır.
Referans, havuz-oracle ve seçilen planlar için 82 benzersiz hafta-plan fiziksel/maliyet denetimi geçti. Matris maliyetleri bağımsız hesapla eşleşti. Basit yöntemin seçim ve regret değerleri Görev 1'in aynı haftalarıyla eşleşti.

| A − B | Ortalama maliyet farkı TL/hafta | A daha ucuz | Eşit | B daha ucuz |
|---|---:|---:|---:|---:|
| naive_yesterday_recursive − lear_level_1 | -93.05 | 3 | 29 | 2 |
| naive_yesterday_recursive − hgb_expanding_cached | 20.54 | 0 | 33 | 1 |
| naive_yesterday_recursive − ensemble_level_fixed | -57.16 | 1 | 32 | 1 |
| lear_level_1 − hgb_expanding_cached | 113.59 | 1 | 30 | 3 |
| lear_level_1 − ensemble_level_fixed | 35.88 | 1 | 31 | 2 |
| hgb_expanding_cached − ensemble_level_fixed | -77.70 | 1 | 33 | 0 |

Bu geliştirme dönemi ve dar plan havuzu dışında ekonomik üstünlük çıkarımı yapılmaz. Görev 3 fiyat tahmini skorları burada bütün fabrikayı yeniden optimize eden bir deney olarak yorumlanamaz.
