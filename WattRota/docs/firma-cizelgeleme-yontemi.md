# Firma çizelgeleme yöntemi

## Problem

Üç günlük çimento öğütme, paketleme ve yükleme faaliyetleri aynı modelde planlanır. Girdiler `data/synthetic/firma_01` klasöründeki tablolardır. Referans plan bir karşılaştırma ve uygulanabilir başlangıç çözümüdür; çözücünün üreteceği öneri önceden sonuç tablosuna yazılmaz.

İkili kararlar kaynak/ürün/saat bazında üretim, ürün ayarı, hazırlık başlangıcı, çalıştırma/durdurma, iş emri ataması ve yükleme seçimini gösterir. Yüklenen tonaj ile stok miktarları sürekli değişkendir. Üretim bir saatlik tam kapasite dilimleriyle yürütülür. Bölünebilir iş emirleri uygun kaynaklar arasında dağıtılabilir.

## Amaç fonksiyonu

Minimize edilen tutar:

**PTF bedeli + başlatma giderleri + ürün geçişi giderleri + seçilmişse plan değişikliği gideri.**

PTF bedeli saatlik toplam kWh / 1.000 × TL/MWh ile hesaplanır. Temel yük, üretim, hazırlık, başlatma enerjisi ve yükleme birlikte yer alır. Yükleme kaynağı kısmi tonajla da çalışsa o saatin tanımlanmış tam enerji gideri kullanılır. Bu senaryo varsayımı gerçek ölçüm yerine geçmez.

Varsayılan plan değişikliği gideri sıfırdır. Pozitif seçilirse üretim/paketleme kaynağının referansa göre durum veya ürününün değiştiği her saat için sabit TL eklenir. Yükleme saat değişiklikleri bu cezanın kapsamına girmez. İşçilik, doğal gaz, su, bakım aşınması ve sözleşmedeki bütün fatura bileşenleri hakkında veri bulunmadığından elde edilen toplam, firmanın bütün işletme maliyeti olarak yorumlanamaz.

## Kısıtlar ve zaman yorumu

- Kaynak bir saatte üretim, hazırlık veya kapalı durumlarından birindedir. Bakım sırasında çalışamaz.
- Üretim yalnızca makine–ürün uygunluk tablosundaki eşleşmelerde yapılır. Ürün ayarı kapalı saatte korunur; değişiklik hazırlık tamamlandığında gerçekleşir.
- Hazırlık süresince üretim yapılamaz. Hazırlık kapalı süre sayılmaz; hazırlıktan üretime geçiş yeni başlatma sayılmaz.
- Minimum üretim süresi kaynak–ürün bloğuna uygulanır. Aynı ürünün farklı iş emirleri arasındaki geçiş bu bloğu kesmez. Minimum duruş ve ufuk sonundaki süreler de korunur.
- Her iş emrinin miktarı kendi serbest bırakma/tamamlanma aralığında üretilir. Her sipariş eksiksiz ve izin verilen yükleme penceresinde sevk edilir.
- Ürünler ortak stok üzerinden takip edilir. Bir iş emrinin tüm öğütmesinin bitmesi paketlemenin başlaması için zorunlu değildir; yeterli dökme stok bulunması zorunludur. Başlangıç stokları kullanılabilir.
- Saat başında eldeki stok, paketleme ve sevkiyat tüketiminden sonra minimum stoktan düşük olamaz. Aynı saatin üretimi saat sonunda eklenir. Böylece henüz üretilmemiş malzeme aynı saat içinde kullanılmaz.
- Saat sonu stokları ürün kapasitesini ve ortak torbalı depo kapasitesini aşamaz. Dönem sonu hedefleri referansla aynıdır.
- Saatlik toplam enerji, bir saatlik dönem için ortalama kW'a karşılık gelir ve ortak tesis sınırını aşamaz. Bu kısıt anlık elektriksel kalkış akımı analizi değildir.

Bu sürüm kapalı başlangıç ve bölünebilir iş emirleri için tanımlıdır; farklı başlangıç veya bölünemez emirler sessizce aynı modele alınmaz. Kapsam, bu firmanın dökme/torbalı üretim rotalarıdır; genel amaçlı fabrika modeli değildir.

## Çözüm ve doğrulama

Model HiGHS ile çözülür. Kontrol edilmiş referans hem bağımsız simülatörde hem tüm model satırlarında doğrulanıp başlangıç çözümü olarak verilir. Ön aramada bazı üretim kaynakları sabitlenerek aynı modelin alt problemleri çözülür. Ardından bütün kararların serbest olduğu ana arama yapılır. Alt problemlerin sonuçları global optimum kanıtı sayılmaz.

Çözücü durumu, hedef ve gerçekleşen göreli açık, alt sınır ve süreler `cozum_bilgisi.json` dosyasında saklanır. Süre sınırında kalan uygun çözüm “kesin optimum” olarak sunulmaz. Arama süresi artırılabilir; farklı bilgisayarlarda zaman sınırına bağlı sonuçlar değişebilir.

Sonuç planı, model matrisinden ayrı çalışan `firma_planini_dogrula` ile saat saat yeniden hesaplanır. Üretim, stok, teslim, bakım, hazırlık ve güç kontrolleri geçmeden çıktı kaydedilmez. Bağımsız maliyet hesabı çözücü amaç değeriyle karşılaştırılır. Kayıtlı sonuçların güncel girdilerle karıştırılmasını önlemek için girdi ve model dosyalarının SHA-256 izleri tutulur.

Küçük model testi iki alternatif değirmen ve paketleme kaynağı içerir. İki saatlik üretim blokları ve bütün yükleme saatleri bağımsız taranır; 1.316 uygulanabilir alternatif içinden hesaplanan maliyet çözücüyle karşılaştırılır. Test koşullarında tek saatte sevk edilebilen siparişleri bölmek daha az aktif yükleme saati sağlamaz; stok kapasiteleri de tek sevkiyata yeterlidir. Bu özel test ana fabrikanın bütün olası çizelgelerinin tarandığı anlamına gelmez. Sabit fiyat ve yüksek değişiklik gideri ayrıca sınanır.

## Çalıştırma

Proje kökünde:

```text
python scripts/firma_cizelgeleme_calistir.py --sure 120 --acik 0.001
python tests/test_firma_verisi.py
python tests/test_firma_cizelgeleme.py
```

Çıktılar `data/results/firma_01_cizelgeleme` klasörüne yazılır. `03_firma_cizelgeleme.ipynb` kayıtlı çıktıyı okuyup denetimi tekrar çalıştırır; karşılaştırma tablosunu, çizelgeyi, güç profilini ve stokları gösterir.

## Kaynak

- [HiGHS Python arayüzü](https://ergo-code.github.io/HiGHS/dev/interfaces/python/example-py/): çözüm motorunun Python arayüzü.
- Firma girdilerinin kaynak/varsayım ayrımı: `parametre_dayanaklari.csv`, `veri_sozlugu.csv` ve `firma-uretim-kapsami.md`.

Bu çalışma bilinen geçmiş fiyatlarla yapılan senaryo karşılaştırmasıdır. Sonuç, fiyat tahmin performansı, gerçek fabrikada elde edilmiş tasarruf veya bütün maliyet bileşenleri için ekonomik fizibilite kanıtı değildir.

## Arama ayarı ve esneklik incelemesi

İlk gün P01 iş emirleri 12 saat net üretim ve en az 2 saat hazırlık gerektirir; tamamlanma sınırı ilk 14 saattir. İlk gün bu kaynağın boş zamanı yoktur. Bu hesap ürün sırasını tek başına sabitlemez; stoklar diğer sıraları ayrıca sınırlar. Y02 için sipariş bazlı yükleme kapasitesi en az 27/30 saat kullanım gerektirir. UR03 yalnızca H01'de öğütülebilir. Bu koşullar plan değişikliğini zorlaştırır, imkânsız olduğunu göstermez.

Ön aramada yüzde 1 tolerans, küçük fakat geçerli maliyet avantajlarını bulmadan durmaya izin verebiliyordu. Alt problem toleransı en fazla 0,000001 göreli açık olacak şekilde daraltıldı. Bu davranış küçük bir farkın yüksek toplam maliyet içindeki payıyla sınanan ek testle kontrol edilir. Ana arama toleransı ayrı parametredir; varsayılan komutta yüzde 0,1 hedeflenir. Süre sınırı bu hedefe ulaşılmasını garanti etmez.

Arama karşılaştırmaları `arama_karsilastirmasi.csv` dosyasında tutulur. Süre ve algoritma ayarları birlikte değiştiği için bu tablo yalnızca süre etkisinin izole edildiği bir deney değildir. Firma girdileri ve kısıtlar aynı kalmıştır. Kayıtlı bir öneri güncel koşullarda doğrulanıp referanstan pahalı değilse sonraki çalıştırmada başlangıç çözümü olarak kullanılır; böylece kısa bir yeniden arama daha iyi bir planı kaybettirmez.
