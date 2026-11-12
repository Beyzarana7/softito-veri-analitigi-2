# Kazanç potansiyeli ve kısıt tanıları

## Amaç

Fiyat tahmini karşılaştırmalarını yorumlamadan önce, aynı işletme kurallarında bulunabilen maliyet azalmasını ve çözülememiş iyileştirme alanını ölçmek. Önceki 19 seçenekli deney, tahmin etkisini arama süresinden ayırıyordu; burada ana MILP bütün tanımlı çizelgeleri araştırır.

Üç geriye dönük örnek 2–4 Şubat, 4–6 Mayıs ve 5–7 Ekim 2026'dır. Talep, başlangıç/son stoklar, kaynak kapasitesi, ürün uygunluğu, minimum süreler, bakım ve göreli teslim takvimi aynıdır. Yalnız tarih ve gerçekleşmiş PTF değişir. Bu tarihler mevsimlerin tamamını temsil etmez. Firma verisi sentetiktir; “gerçek” sözcüğü gerçekleşmiş fiyatla hesaplamayı belirtir.

## Başlangıç ve tam arama

Her kaynakta referansın günlük üretim miktarlarını koruyan iki ürün sırası denenir. Üç kaynak ve üç gün için 512 bileşim vardır. Ürün hazırlıkları açıkça yerleştirilir; sonraki günün ayarı gerekiyorsa ufuk içinde hazırlanır. Bütün stok, teslim, minimum süre, bakım ve güç kontrollerinden geçen 32 farklı başlangıç saklanır. Bunların fiziksel enerji vektörleri bağımsız tesis hesabından elde edilir.

Başlangıç adayları bu sıralar, önceki 2025 planları ve varsa aynı karar örneğinde doğrulanmış uygun planlardır. Fiyat bilgisine göre en düşük amaçlı uygun başlangıç seçilir. Tam MILP'nin çözüm uzayı bu seçeneklerle sınırlanmaz. İşletme verileri veya kurallar, kazanç elde etmek amacıyla değiştirilmez.

Tam fiyat bilgisi aramalarında üç günün fiyatı biliniyor kabul edilir. Her ana arama 300 saniye ve 0,0001 göreli açık (%0,01) hedefiyle çalışır; hedefe ulaşılamaması ayrıca kaydedilir. Ayrı ön arama kullanılmaz. 5 Ekim'de basit gün tekrarı da aynı 300 saniye bütçesiyle çalıştırılır. İlk 24 saatin fiyatı bu yöntemde bilinir; sonraki iki gün için aynı profil tekrarlanır.

## Maliyet aralıkları

L, tam fiyat bilgisi modelinin matematiksel alt sınırı; U, bağımsız denetimden geçen en düşük maliyetli uygun plan olsun. Modelin bilinmeyen optimumu C* için L ≤ C* ≤ U'dur. Başka yöntemle bulunmuş ve aynı gerçek koşullarda doğrulanmış daha düşük maliyetli plan varsa U olarak kullanılabilir; bu durum kaynak adıyla kaydedilir. Farklı fiyat tahmini amacının alt sınırı, gerçek maliyet için alt sınır olarak kullanılmaz.

Referans R için:

- **Bulunmuş maliyet azalması:** R−U. Gerçekleşmiş fiyatlarla hesaplanan uygun planın farkıdır.
- **Olası azami azalmanın üst sınırı:** R−L. Elde edileceği kanıtlanmış kazanç değildir.
- **Kalan çözüm açıklığı:** U−L. Ek iyileştirme miktarının henüz kesinleşmediğini gösterir.

Bunlar istatistiksel güven aralığı değildir. Vergi ve bütün sözleşme bedellerini içeren fabrika faturası yerine PTF ve tanımlanmış başlatma/geçiş giderleri değerlendirilir. Farklı yöntemlerin farklı arama performansları bulunduğundan R−U saf “fiyat bilgisinin değeri” diye adlandırılmaz.

## Stok, teslim ve kaynak tamponları

Bulunan tam bilgi planlarında şu göstergeler hesaplanır: tüketimden sonra minimum stoğa kalan ton, stok kapasitesine temas, son yükleme bitişi ile teslim arasındaki saat, iş emri bitişi ile sınırı arasındaki saat, minimum sürede biten üretim/duruş blokları, hazırlık saatleri ve ortak güç sınırına kalan marj.

Bir sınırın planda dolması, o kuralın ekonomik etkisinin tek başına ölçüldüğü anlamına gelmez. Dolmaması da global optimumda önemsizliğini kanıtlamaz. İlk gün paketleme emirleri 12 saat net üretim ve en az 2 saat ürün hazırlığı gerektirir; 14 saatlik tamamlanma penceresinde boşluk yoktur. UR03 yalnız H01'de öğütülebilir. Bu koşulların birlikte ele alınması gerekir.

## Ayrı ve etiketli kural tanıları

Yalnız 5 Ekim örneğinde üç teşhis kopyası oluşturulur: minimum stokları sıfıra indirmek; iç iş emri bitiş sınırlarını plan sonuna uzatmak (müşteri teslim saatleri aynı); minimum üretim/duruş sürelerini bir saate indirmek. Miktarlar, motor güçleri, kaynak uygunluğu ve dönem sonu stokları değişmez. Orijinal firma CSV'leri korunur. Bu kopyalar ana sonuçların veya gerçek fabrika önerisinin yerine geçirilmez.

Her teşhis 120 saniye çalışır. Çözüm teşhis kurallarında denetlenir; ayrıca asıl kurallara uyup uymadığı kaydedilir. Orijinal optimum [Lb,Ub], gevşetilmiş optimum [Lr,Ur] aralığındaysa, kuralı gevşetmenin maliyet etkisi şu aralıkla sınırlanır:

**max(0, Lb−Ur) ≤ Cb*−Cr* ≤ Ub−Lr.**

Orijinal uygun plan gevşetilmiş kopyada da uygundur; Ur gerekirse orijinal uygun maliyetle daraltılır. Alt etkinin sıfır çıkması kural etkisinin sıfır olduğunu kanıtlamaz. Nokta maliyetler aynı kaldıysa ve aralıklar genişse, kısa aramada etkisi ayrıştırılamadı denir.

## Fiyat hatasının belirli karar farkına etkisi

Her örnekte yöntemin bulduğu plan, tam bilgiyle bulunan en düşük uygun planla sonradan fiyatlandırılarak karşılaştırılır. Bu ikinci plan gerçekleşmiş gelecek fiyatlarıyla bulunmuştur; tanısal karşılaştırma dışında tahminli yönteme verilmez. Bu nedenle sonuç bir ileriye dönük performans iddiası veya geleceği bilmeyen algoritmanın bu planı bulduğu iddiası değildir.

Saatlik enerji farkı ΔE = yöntemin enerjisi − iyi planın enerjisi olsun. İki plan arasındaki maliyet farkının tahmin kaynaklı yanılması tam olarak şöyledir:

**Tahminle hesaplanan fark − gerçek fiyatla hesaplanan fark = Σ ΔE × (tahmin − gerçek fiyat) / 1.000.**

Başlatma/geçiş giderleri aynı plan çifti için sabit olduğundan bu hata farkında elenir. İlk günün açıklanmış fiyatı iki hesapta aynıdır. Her saat böylece TL cinsinden karar-farkı etkisine ayrılır. Bu, genel fiyat MAE'sinden ayrı bir ölçüdür.

Gerçek fiyatla daha iyi bir plan, yöntemin kendi tahmin fiyatlarıyla da daha iyiyse, bu çiftte arama fırsatı görülür. Tahmin fiyatlarıyla daha pahalı görünüyorsa fiyat hatası bu planın tercih edilmesini engelliyor olabilir. Yorum sadece incelenen plan çifti içindir; bütün çizelgeler için nedensel üstünlük iddiası değildir.

## Dosyalar ve yeniden üretim

Kodlar `src/kazanc_potansiyeli.py` ve `src/kazanc_tanilari.py`; sonuçlar `data/results/kazanc_potansiyeli`; değerlendirme `notebooks/08_kazanc_potansiyeli_ve_kisitlar.ipynb` dosyasındadır. `kazanc_araliklari.csv`, `ikili_plan_teshisi.csv`, `saatlik_karar_hatasi.csv`, `kural_teshis_araliklari.csv` ana özetlerdir. Her aramanın ayrı planı, stok/enerji akışı ve çözüm bilgisi vardır.

```text
python src/kazanc_potansiyeli.py baslangic . data/results/kazanc_potansiyeli
python src/kazanc_potansiyeli.py kiyas . data/results/kazanc_potansiyeli --karar 2026-10-05 --sure 300
python src/kazanc_potansiyeli.py kiyas . data/results/kazanc_potansiyeli --karar 2026-10-05 --sure 300 --yontem basit_tahmin
python src/kazanc_potansiyeli.py kiyas . data/results/kazanc_potansiyeli --karar 2026-10-05 --sure 120 --tani ic_is_emri_sureleri
python src/kazanc_tanilari.py . data/results/kazanc_potansiyeli
python tests/test_kazanc_potansiyeli.py
```

Diğer tanı adları `stok_alt_siniri` ve `minimum_blok_sureleri`dir. Üç ana tarih için tam bilgi araması tamamlandıktan sonra özetleme çalıştırılır. Zaman sınırına bağlı çizelgeler farklı çalıştırmalarda değişebilir; kaydedilmiş çözümler kendi kaynak izleri ve bağımsız kontrolleriyle değerlendirilir.
