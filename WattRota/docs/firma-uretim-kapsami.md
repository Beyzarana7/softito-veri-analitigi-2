# WattRota — Firma Üretim Yapısı ve Model Kapsamı

## 1. Amaç ve tesis tanımı

Çalışma, tek bir kurgusal çimento öğütme ve sevkiyat firmasının üretim planlamasını ele alır. Firma, klinker ve katkı maddelerini işleyerek üç ürün üretir; ürünleri dökme ve torbalı biçimde sevk eder. Üretim verileri kaynaklarla desteklenen sentetik senaryo verileridir. Firma adı herhangi bir gerçek işletmeyi temsil etmez.

Amaç, sipariş miktarlarını ve teslimat koşullarını koruyarak elektrik fiyatlarına duyarlı üretim çizelgesi oluşturmaktır. Makine seçimi, ürün sırası, üretim zamanı, paketleme ve yükleme kararları birlikte ele alınır.

Tesis yapısı, aynı sektördeki bütün fabrikaları temsil eden evrensel bir tasarım değildir. Ekipman sayıları ve ürün uygunlukları bu firma senaryosuna ait tasarım seçimleridir.

## 2. Üretim akışı

```text
Klinker ve katkı tedariki
          │
    ┌─────┴─────┐
    │           │
Öğütme H01  Öğütme H02
    │           │
    └─────┬─────┘
          │
 Ürünlere ayrılmış dökme siloları
          │
    ┌─────┴────────────────┐
    │                      │
Dökme yükleme Y01     Paketleme P01
    │                      │
Dökme teslimat       Torbalı ürün stoğu
                           │
                     Torbalı yükleme Y02
                           │
                     Torbalı teslimat
```

Ürünler silolarda birleştirilmez. Torbalı siparişler paketleme aşamasından geçer; dökme siparişler bu aşamayı kullanmaz. Öğütme, paketleme ve yükleme farklı kaynaklar olduğundan uygun stok bulunduğunda eşzamanlı çalışabilir.

## 3. Ürünler ve kaynaklar

| Kod | Ürün | H01 uygunluğu | H02 uygunluğu | Teslim biçimi |
|---|---|---|---|---|
| UR01 | Portland çimentosu | Uygun | Uygun | Dökme / torbalı |
| UR02 | Kalker katkılı çimento | Uygun | Uygun | Dökme / torbalı |
| UR03 | İnce öğütülmüş Portland çimentosu | Uygun | Uygun değil | Dökme / torbalı |

UR03 için H01 uygunluğu, tesisin ürün bazlı hat yeterliliği varsayımıdır; sektördeki bütün ikinci hatların bu ürünü üretemediği anlamına gelmez. Ürün adları bir kalite sınıfı veya standart uygunluk belgesi yerine kullanılmaz. Reçete ve kalite koşulları sabit ve kabul edilmiş çalışma modları olarak tanımlanır.

| Kaynak | Sayı | İşlev |
|---|---:|---|
| Öğütme hattı | 2 | Ürün bazında farklı kapasite ve enerji tüketimiyle üretim |
| Dökme ürün silosu | 3 | Her ürüne ayrılmış stok |
| Paketleme hattı | 1 | Bütün ürünlerin ortak torbalama kaynağı |
| Torbalı stok bölümü | 3 | Ürün bazında ayrı stok; ortak depo toplam kapasitesiyle sınırlı |
| Dökme yükleme noktası | 1 | Dökme siparişlerin sevki |
| Torbalı yükleme noktası | 1 | Torbalı siparişlerin sevki |

İki öğütme hattı alternatif makine atamasını, üç ürün hat uygunluğu ve ürün sırasını, ortak paketleme hattı ise ardışık süreçteki kapasite paylaşımını temsil eder. Ekipman sayısı ile karar karmaşıklığı bu bağlantılar üzerinden gerekçelendirilmiştir.

## 4. Birimler ve zaman

- Miktarlar ton, kapasiteler ton/saat, güç kW, enerji kWh, fiyat TL/MWh cinsindedir.
- Torbalı ürün miktarı da ton cinsinden tutulur; torba ve palet sayısı ayrı karar değişkeni değildir.
- Zaman çözünürlüğü bir saattir. Üretim ve hazırlık çalışma modları saatlik olarak tanımlanır.
- İlk veri dönemi 6 Ekim 2025 00.00–9 Ekim 2025 00.00 aralığıdır; bitiş anı hariçtir.
- Siparişler, üretimin önceden planlanabilmesini gerektiren farklı teslim günleri ve saatleri içerir. Tüm teslimler tek bir son saate yığılmaz.

## 5. İşletme kuralları

### 5.1. Öğütme

1. Bir hat aynı saatte yalnızca bir ürün üretir veya ürün değişimi hazırlığı yapar.
2. Üretim, hat–ürün uygunluğuna bağlıdır. Kapasite ve güç değerleri hat–ürün eşleşmesinden alınır.
3. Bir ürünün üretimi farklı hatlara ve zaman bloklarına bölünebilir. Aynı ürün iki uygun hatta eşzamanlı üretilebilir.
4. Her üretim bloğu, ilgili hattın minimum kesintisiz üretim süresini karşılar.
5. Kapalı kalan hattın yeniden açılması için minimum duruş süresi sağlanır.
6. Ürün geçişleri hat, önceki ürün ve sonraki ürüne göre hazırlık süresi ve enerji gerektirir. Hazırlık sırasında satılabilir ürün üretilmez.
7. Başlatma enerjisi ve elektrik dışı başlatma gideri, kapalıdan aktif duruma geçişte bir kez oluşur. Ürün hazırlığından üretime geçiş ikinci bir başlatma sayılmaz.
8. Bakım saatleri bağlayıcıdır. Başlangıç durumu, geçen durum süresi ve ürün ayarı veri olarak tutulur.

### 5.2. Stok ve paketleme

1. Her ürün kendi dökme silosuna girer. Silo minimumu, kapasitesi ve dönem sonu hedefi korunur.
2. Dökme silo çıkışı hem dökme yüklemeyi hem paketlemeyi besler. Aynı ton iki çıkışa birden ayrılamaz.
3. Paketleme hattı aynı saatte tek ürün işler. Ürün değişimi, çalışma takvimi ve ürün bazlı kapasite dikkate alınır.
4. Paketlenen miktar ilgili ürünün torbalı stoğuna girer. Torbalı yükleme bu stoktan karşılanır.
5. Torbalı stokların ürün bazlı sınırları yanında ortak depo toplam kapasitesi korunur.
6. Üretim ve paketleme çıktıları saat sonunda kullanılabilir hâle gelir. Saatlik çıkışlar dönem başı mevcut stokla karşılanır. Böylece model malzemeyi aynı saat içinde iki aşamadan birden geçirmiş saymaz.
7. Paketlemede ton bazlı dönüşüm 1:1 kabul edilir; ambalaj kütlesi üretim tonajına eklenmez. Hazırlık sırasında üretim kaybı varsa senaryo parametresi olarak ayrıca gösterilir; kayıp kendiliğinden varsayılmaz.

### 5.3. Sipariş ve yükleme

1. Sipariş; ürün, miktar, geliş zamanı, en erken yükleme zamanı, son teslim zamanı ve dökme/torbalı tür içerir.
2. Yükleme, siparişin gelişinden ve kabul edilen en erken zamandan önce başlayamaz.
3. Sipariş birden fazla yükleme saatine bölünebilir; toplam sevkiyat sipariş miktarına eşittir.
4. Dökme ve torbalı siparişler kendi yükleme noktalarını kullanır. Her nokta aynı saatte tek siparişe ayrılır.
5. Kaynak kapasitesi ve çalışma takvimi korunur. Son teslim anı, yüklemenin tamamlanması gereken sınırdır.
6. Kamyon rotası ve tek tek seferler ton/saat cinsinden toplulaştırılmış yükleme kapasitesiyle temsil edilir.

### 5.4. Elektrik ve maliyet

1. Öğütme, hazırlık, başlatma, paketleme, yükleme ve kontrol dışı temel yük birlikte enerji hesabına girer.
2. Kaynakların toplamı, tesisin ortak saatlik ortalama güç sınırını aşamaz. Kısa süreli kalkış akımı bu sınırdan çıkarılamaz.
3. PTF'nin saatlik tüketime yansıtıldığı sözleşme senaryosu kullanılır. PTF bedeli tam fatura olarak adlandırılmaz.
4. Amaç; modellenen elektrik bedeli, başlatma/geçiş giderleri, ek çalışma ve mevcut planı değiştirme giderlerinin toplamıdır. Aynı gider iki kez sayılmaz.
5. Referans ve önerilen plan aynı siparişleri ve stok hedeflerini karşılar. Enerji miktarı değişirse maliyet farkının yalnızca saat kaydırmadan kaynaklandığı söylenmez.

## 6. Veri yapısı

| Tablo | Temel içerik |
|---|---|
| urunler | Ürün kimliği ve açıklaması |
| kaynaklar | Öğütme, paketleme ve yükleme kaynaklarının kimlikleri ve türleri |
| kaynak_urun | Kaynak–ürün uygunluğu, kapasite ve çalışma gücü |
| isletme_kurallari | Minimum süreler, başlangıç durumu, başlangıç ayarı, başlatma bileşenleri |
| urun_gecisleri | Kaynak ve ürün çiftine göre hazırlık süresi, güç ve gider |
| stok_alanlari | Ürün, dökme/torbalı stok türü, alt/üst sınır, başlangıç ve son hedef |
| depo_kurallari | Ortak torbalı depo toplam kapasitesi |
| siparisler | Ürün, miktar, teslim türü ve zaman penceresi |
| takvim | Kaynak bazlı uygun saatler ve bakım |
| tesis_takvimi | Temel elektrik yükü ve ortak güç sınırı |
| fiyatlar | EPİAŞ saatlik PTF ve kaynak bilgisi |
| parametre_dayanaklari | Değer, birim, kaynak veya varsayım niteliği ve gerekçe |

Ekipman kimlikleri tablolardan okunur. Bu veri modeli seçilen firmanın yapısına göre tasarlanmıştır; farklı sektörlere uyarlanabilirlik bitirme projesinin geliştirme kapsamındadır.

## 7. Verinin oluşturulması ve doğrulanması

Kapasite ve tüketim değerleri aynı ürün, ekipman ve çalışma koşulu için eşleştirilir. Ana motor etiket gücü toplam hat tüketimi gibi kullanılmaz. Sayısal değeri doğrulanamayan alan senaryo varsayımı olarak işaretlenir.

Sipariş verileri elektrik fiyatlarına göre seçilmez. Önce kapasite, stok ve teslimat açısından mümkün bir üretim/sevkiyat akışı hazırlanır; uygunluğu kontrol edildikten sonra referans plan olarak kullanılır. Girdi miktarları ve ürün karışımı, alternatif hat seçimi ve ortak kaynak kullanımını etkileyen bir yük oluşturur. Gerçek tesis kapasite kullanımına ilişkin iddia kurulmaz.

Veri kabul kontrolleri:

- Kimlikler tekil, tablo bağlantıları geçerli ve birimler tutarlıdır.
- Uygun olmayan kaynak–ürün eşleşmeleri üretim yapamaz.
- Dökme ve torbalı stokların malzeme dengesi ayrı sağlanır.
- Paketleme ve yükleme kapasitesi, bakım ve ortak güç sınırı korunur.
- Her sipariş kendi zaman penceresinde tamamlanır.
- Başlangıç ve dönem sonu stok hedefleri kontrol edilir.
- Sabit fiyat, sınırlı stok, bakım ve karşılanamaz sipariş örnekleriyle davranış sınanır.

Mevcut tek hatlı örnek, hesapların küçük ölçekte doğrulanması için test verisidir; bu firma veri setinin yerine kullanılmaz.

## 8. Kaynaklar ve varsayım sınırları

- [ECRA Teknoloji Raporu 2022, Teknoloji Belgesi 25](https://api.ecra-online.org/fileadmin/files/tp/ECRA_Technology_Papers_2022.pdf): Öğütme esnekliği, stok kapasitesi ve dur-kalk sınırlarının teknik dayanağı.
- [Berkeley Lab — Cement Industry Demand Response](https://ets.lbl.gov/publications/opportunities-energy-efficiency-and-2): Çimento üretiminde depolama ve yük kaydırma bağlantıları.
- [Gebr. Pfeiffer MVR teknik bilgileri](https://www.gebr-pfeiffer.com/en/products/mvr-vertical-roller-mill-conventional-drive/): Öğütme ekipmanı ve ürün koşullarının değerlendirilmesi.
- [EPİAŞ Şeffaflık Platformu](https://seffaflik.epias.com.tr/): Saatlik PTF kaynağı.

Kaynaklar süreç seçimini destekler; bu belgede tanımlanan iki hat, üç ürün, ürün uygunluk matrisi ve stok yerleşiminin gerçek bir tesisten alındığı anlamına gelmez. Reçete optimizasyonu, fırın işletmesi, kalite tahmini, su/gaz dengesi ve taşıma rotaları model kapsamı dışındadır.
