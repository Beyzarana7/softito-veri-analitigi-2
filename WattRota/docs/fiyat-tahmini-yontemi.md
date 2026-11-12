# Elektrik fiyat tahmini ve karar maliyeti

## Bilgi zamanı

Karar saati Türkiye yerel zamanıyla 00.00, plan ufku 72 saattir. Normal EPİAŞ açıklanma süreci varsayımıyla ilk günün 24 saatlik PTF'si zaten bilinir; sonraki iki günün 48 fiyatı tahmin edilir. EPİAŞ normal süreç sayfası ertesi gün fiyatlarının önceki gün kesinleştiğini açıklar. Arşiv dosyalarında yayın/revizyon zamanları bulunmadığından teknik gecikmeler ve tarihsel veri sürümleri ayrıca yeniden oluşturulmaz.

Fiyatın teslim saatinin gelecekte olması, mutlaka bilinmediği anlamına gelmez. Açıklanmış ilk gün fiyatları hem bilgi kümesine hem eğitime alınabilir. Kod, bütün seriyi önce ilk günün son saatinde keser; özellikler ve eğitim bundan sonra oluşturulur. Tahmin edilen ikinci ve üçüncü günün gerçekleşmiş fiyatları eğitimde veya özelliklerde kullanılmaz. Değerlendirici gerçek hedefleri ancak tahmin üretildikten sonra ekler.

## Yöntemler

Üç basit yöntem: açıklanmış ilk günün saatlik profilini iki güne tekrar etmek, hedef saatin önceki haftadaki fiyatını kullanmak ve önceki dört haftanın aynı saatlerinin ortalamasını almak.

Random Forest 80 ağaç, en fazla 10 derinlik ve yaprakta en az 8 örnek ile kurulur; rastgelelik tohumu 42'dir. Son 180 ve 365 günlük eğitim pencereleri doğrulamada karşılaştırılır. Diğer parametreler sabittir. Yalnızca fiyat ve takvim kullanılır; hava durumu, talep tahmini veya üretim portföyü verisi eklenmez.

## Özellik sözlüğü

| Alan | Anlam / birim |
|---|---|
| `saat` | Hedef saatin gün içindeki değeri, 0–23 |
| `haftanin_gunu` | Pazartesi 0, pazar 6 |
| `ay`, `yil` | Hedef zamanın takvim alanları |
| `ptf_gecikme_48`, `72`, `168`, `336`, `504`, `672` | Hedef saatten belirtilen saat kadar önceki PTF, TL/MWh |
| `son_24_ortalama` | 48 saat geciktirilmiş serinin son 24 değer ortalaması, TL/MWh |
| `son_24_en_dusuk`, `son_24_en_yuksek` | Aynı pencerenin minimumu ve maksimumu, TL/MWh |
| `son_168_ortalama` | 48 saat geciktirilmiş serinin son 168 değer ortalaması, TL/MWh |

En yeni geçmiş özellik t−48'dir. Böylece 72 saatlik planın son hedefinde bile kullanılan en yeni fiyat, bilinen ilk günün son saatidir. Bu, iki hedef gün için ortak ve muhafazakâr bir özellik düzenidir. Gelecekteki fiyatları çok büyük değerlerle değiştirme ve tamamen kaldırma testlerinde tahminlerin değişmediği kontrol edilir.

## Eğitim, seçim ve değerlendirme

2024 başlangıç geçmişidir. 2025'in 52 pazartesi başlangıcında, her defasında yalnız o kararın bilgi kümesiyle eğitim ve 48 saatlik tahmin yapılır. En iyi basit yöntem ile en iyi Random Forest eğitim penceresi, 2025 ortalama mutlak hatasıyla ayrı ayrı seçilir. Bu seçim dosyaya yazıldıktan sonra 2026'nın 44 pazartesi başlangıcı değerlendirilir. Daha önce açıklanmış 2026 fiyatları ilerleyen haftalarda eğitime girer; yöntem ve pencere seçimi değiştirilmez. Rastgele eğitim/test bölmesi kullanılmaz.

2026 verileri keşifsel analizde daha önce incelendiği için bütünüyle hiç görülmemiş bir kör test iddiası taşınmaz. Bu, karar zamanındaki bilgi sınırını koruyan geriye dönük zamansal değerlendirmedir. Hedefler salı/çarşamba saatleridir ve bütün hafta günlerini temsil etmez.

MAE ve RMSE TL/MWh olarak raporlanır. Bilinen ilk gün metriklere dahil değildir. Sıfır fiyatlar nedeniyle MAPE kullanılmaz. Her hedef günün ve ayın hatası ayrıca gösterilir; aylık sonuçlar yalnız değerlendirilen haftalık pencereleri kapsar.

## Tahminin üretim kararına bağlanması

Karar örneği 5 Ekim 2026 00.00'da başlar. Aynı sentetik firmanın göreli iş/bakım takvimi bu pazartesiye taşınır. Yöntemler:

1. Üç günün gerçekleşmiş fiyatlarının tamamının bilindiği karşılaştırma.
2. İlk gün açıklanmış fiyatları + doğrulamada seçilmiş basit yöntemin sonraki 48 saat tahmini.
3. İlk gün açıklanmış fiyatları + doğrulamada seçilmiş ML yönteminin sonraki 48 saat tahmini.

Her yöntem aynı sipariş, kaynak, stok ve teslim koşullarıyla çözülür. Ana çözüm sınırı 120 saniye, hedef göreli açık %0,1'dir. Tahminli yöntemlerin planlayıcısına gerçekleşmiş gelecek fiyat sütunu verilmez. Üretilen plan fiziksel olarak doğrulandıktan sonra gerçekleşmiş 72 saatlik fiyatlarla yeniden fiyatlandırılır. Planlama sırasında beklenen tutar ile bu gerçekleşmiş tutar ayrı kaydedilir. Tahmin hatası yalnız bilinmeyen 48 saat üzerinden ölçülür.

Tüm fiyatların bilindiği koşulda çözülen karşılaştırma da süre sınırlıdır; matematiksel optimum olduğu varsayılmaz. Tahminli bir planın gerçekleşmiş maliyeti bu karşılaştırmadan daha düşük çıkarsa fark gizlenmez veya sıfıra kırpılmaz. Tek karar örneği ekonomik etkinin genel kanıtı değildir. Fiyat tahmininin daha doğru olması mutlaka daha ucuz karar üretmez.

## Çıktı sözlüğü

| Dosya / alan | Açıklama |
|---|---|
| `saatlik_tahminler.csv` | Bölüm, model, karar zamanı, hedef saat, hedef gün, gerçekleşmiş PTF ve tahmin |
| `hata_ozeti.csv` | Yöntem/bölüm bazında saat ve karar sayısı, MAE, RMSE, ortalama işaretli hata |
| `ufuk_hatalari.csv` | İkinci ve üçüncü günün hata büyüklükleri |
| `egitim_izleri.csv` | Her kararın bilinen son saati; ML eğitim aralığı ve en yeni geçmiş özellik saati |
| `model_secimi.json` | Doğrulamadan seçilen yöntemler ve sabit parametreler |
| `deney_bilgisi.json` | Veri kapsamı, süre ve ham dosya/kod SHA-256 izleri |
| `planlama_fiyatlari.csv` | Karar deneyinde kullanılan ve gerçekleşmiş fiyatlar; bilginin türü |
| `maliyet_karsilastirmasi.csv` | Referansın gerçek fiyat maliyeti; önerinin planlama fiyatı ve gerçek fiyat maliyetleri |
| `sonuc.json` | Karar yönteminin beklenen/gerçekleşmiş maliyeti, hata, çözüm durumu ve kaynak izleri |

## Yeniden üretim

Proje kökünde:

```text
python src/fiyat_tahmini.py . data/results/fiyat_tahmini
python tests/test_fiyat_tahmini.py
python tests/test_tahminli_cizelgeleme.py
python src/tahminli_cizelgeleme.py . data/results/fiyat_tahmini basit_tahmin data/results/tahminli_cizelgeleme --sure 120
```

Son komuttaki yöntem `tum_fiyatlar_biliniyor`, `basit_tahmin` veya `ml_tahmin` olabilir. Zaman sınırı nedeniyle farklı çalıştırmalarda bulunan çizelgeler değişebilir.

## Kaynaklar

- [EPİAŞ — GÖP normal süreçleri](https://www.epias.com.tr/gun-oncesi-piyasasi/surecler/): fiyat açıklanma takvimi.
- [scikit-learn — RandomForestRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html): kullanılan tahminleyici.
- [scikit-learn — Gecikmeli özelliklerle zaman serisi tahmini](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html): gecikmeli girdiler ve zaman sırasını koruyan değerlendirme örneği.
