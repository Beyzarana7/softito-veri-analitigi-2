# Firma senaryoları

## Amaç

Tek bir örnekte bulunan avantajın farklı fiyatlar, artan talep ve yüksek plan değişikliği gideri altında nasıl değiştiğini incelemek. Firma sentetiktir; elektrik fiyatları EPİAŞ'ın 2025 CSV dosyasından alınır. Fiyatların tamamı planlama sırasında biliniyor kabul edilir.

## Senaryolar

| Senaryo | Değişen koşul | Korunan koşullar |
|---|---|---|
| Temel | 6–8 Ekim 2025 fiyatları | Kayıtlı firma ve referans plan |
| Kış | 6–8 Ocak 2025 fiyatları | Talep, kaynaklar, stoklar, göreli takvim |
| İlkbahar | 7–9 Nisan 2025 fiyatları | Talep, kaynaklar, stoklar, göreli takvim |
| Yaz | 7–9 Temmuz 2025 fiyatları | Talep, kaynaklar, stoklar, göreli takvim |
| Yoğun dökme talep | İkinci gün UR02 dökme siparişi 400→560 ton | Fiyatlar, kaynak kapasiteleri, stok sınırları, teslim saatleri |
| Yüksek değişiklik gideri | Değişen üretim/paketleme kaynak-saati başına 10.000 TL | Talep, fiyat, kaynak ve stok koşulları |
| Kapasite aşımı | İkinci gün UR02 torbalı siparişi 400→800 ton | Kaynak kapasitesi ve yükleme takvimi |

Fiyat tarihlerinin tamamı pazartesi–çarşamba aralığıdır; sonuçlara bakılmadan seçilmiştir. Bunlar tek tek üç günlük örneklerdir; mevsimlerin tümünü temsil eden istatistiksel bir örneklem değildir.

## Talep artışının tutarlılığı

Sipariş değiştiğinde bağlı öğütme/paketleme iş emirleri ve ton tahsisleri birlikte güncellenir. Yoğun dökme senaryosunda toplam talep 6.720→6.880 tondur. Bu artış küçük görünse de ikinci gün Y01 için gereken en az yükleme süresi 9 saatin tamamını kullanır; saat 12.00–13.00 bakım aralığı korunur.

Yoğun senaryonun fiyatlardan bağımsız referansında H02'nin ikinci gün UR02 üretimi 19.00–21.00 arasında uzatılır. Ek dökme yükleme saat 11.00'e yerleştirilir; UR01 yüklemeleri 13.00, 14.00, 15.00 ve 17.00'e alınır. Başlangıç ve son stok hedefleri korunur. Her öneri kendi senaryosundaki bu uygulanabilir referansa göre fiyatlandırılır; temel senaryoyla mutlak toplam maliyet karşılaştırması tasarruf diye yorumlanmaz.

## Kapasite ön kontrolü

Bu firmada her yükleme türünün tek kaynağı vardır ve bir saatte bir sipariş işlenebilir. Siparişin zorunlu saat alt sınırı, tonaj / saatlik kapasite hesabının yukarı yuvarlanmasıdır. Aynı gün teslim edilmesi gereken siparişlerin toplam zorunlu saati, o gün ilgili pencerede kullanılabilir saatten fazlaysa çizelge mümkün değildir. Bu kontrolün geçilmesi ise üretim ve stok koşullarını tek başına kanıtlamaz.

Negatif kontrolde ikinci gün Y02 için en az 3 + 7 + 2 = 12 saat gerekir; kullanılabilir süre 10 saattir. Sonuç bu matematiksel çelişkiyle reddedilir. Çözücü çalıştırılmaz ve geçerli çizelge ya da maliyet avantajı kaydedilmez.

## Değişiklik giderinin kapsamı

10.000 TL/kaynak-saat değeri özellikle yüksek seçilmiş bir davranış testi parametresidir; sektör için gerçekçi maliyet iddiası taşımaz. Ceza üretim ve paketleme kaynaklarının durum/ürün değişiklikleri içindir. Yükleme saatlerini veya kısmi yük miktarlarını değiştirmek bu cezaya dahil değildir. Bu yüzden üretimin korunması, bütün sevkiyat planının değişmeden kaldığı anlamına gelmez; iki değişim ayrı raporlanır.

## Çözüm bütçesi ve değerlendirme

Uygulanabilir beş yeni senaryoda ana süre sınırı 120 saniye, hedef göreli açık 0,001'dir (%0,1). Ön aramada aynı kısıtlarla en fazla dört adet 10 saniyelik alt problem çözülür. Alt problemler küçük avantajları erken bırakmamak için en fazla 0,000001 göreli açık hedefler. Süre sınırında kalan çözüm kesin optimum değildir; gerçekleşen açık kaydedilir. Temel satır, aynı 120 saniyelik ana arama bütçesiyle daha önce bulunan kayıtlı sonuçtur; bu karşılaştırmada tekrar çözülmez.

Her senaryonun referansı önce bağımsız kontrol edilir. Öneri, çözücü matrisinden ayrı çalışan saatlik üretim/stok denetiminden geçirilir; teslim miktarları, bakım, ürün geçişleri, minimum süreler ve güç sınırı yeniden hesaplanır. Maliyet, çözücü amaç değeriyle karşılaştırılır. Fiziksel kontrollerden geçmek gerçek tesiste uygulanabilirliğin saha doğrulaması değildir.

Sonuç klasöründe `girdiler.zip` kullanılan tabloları CSV olarak içerir. `sonuc.json`, kaynak kodların ve girdi arşivinin SHA-256 izlerini, ayarları, maliyetleri ve çözüm durumunu kaydeder. `04_senaryo_karsilastirmalari.ipynb` arşivleri yeniden hazırlanan senaryolarla karşılaştırır ve bütün önerileri tekrar denetler.

## Yeniden üretim

Proje kökünden örnek çalıştırma:

```text
python src/firma_senaryolari.py . kis_fiyatlari data/results/firma_01_senaryolar --sure 120
python tests/test_firma_senaryolari.py
```

Senaryo adları: `kis_fiyatlari`, `ilkbahar_fiyatlari`, `yaz_fiyatlari`, `yogun_dokme_talep`, `yuksek_degisim_gideri`, `kapasite_asimi`.

Kaynaklar: `data/raw/epias/Piyasa_Takas_Fiyati-01012025-31122025.csv`; firma parametrelerinin kaynak/varsayım ayrımı için `data/synthetic/firma_01/parametre_dayanaklari.csv` ve `docs/firma-uretim-kapsami.md`.
