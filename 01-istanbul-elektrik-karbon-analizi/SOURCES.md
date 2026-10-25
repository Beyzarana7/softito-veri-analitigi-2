# Veri kaynakları ve hesaplama notları

## Elektrik tüketimi

**Kurum:** Enerji Piyasası Düzenleme Kurumu (EPDK)  
**Yayın:** [Elektrik Piyasası Aylık Sektör Raporları](https://www.epdk.gov.tr/Detay/Icerik/3-0-23/elektrikaylik-sektor-raporlar)

Not defterinde belirtilen kaynak belgeler 2021, 2023, 2025 ve 2026 raporlarıdır. Önceki yıl karşılaştırma sütunları kullanıldığından rapor yılı ile gözlem yılı her zaman aynı değildir. CSV'nin `kaynak` alanı kayıtların rapor kökenini belirtir.

Kapsam İstanbul'un Ocak 2020–Ağustos 2026 dönemindeki aylık, tüketici grubu bazlı faturalanan elektrik tüketimidir. İstanbul Anadolu ve Avrupa ayrımının bulunduğu tablolarda aynı ay ve grubun değerleri toplanmıştır. Birim MWh'dir. Orijinal CSV korunmuş; sınıf adı eşlemeleri analiz sırasında ayrı veri çerçevesinde yapılmıştır.

Bu depodaki kayıtlar kaynak raporlardan oluşturulan analiz veri setidir; EPDK'nın resmî dağıtım dosyası olduğu iddia edilmez. Kaynak yayınların hakları ilgili kuruma aittir.

## Emisyon faktörleri

**Kurum:** T.C. Enerji ve Tabii Kaynaklar Bakanlığı (ETKB)  
**Yayın:** [Türkiye Elektrik Üretimi ve Elektrik Tüketim Noktası Emisyon Faktörleri](https://enerji.gov.tr/evced-cevre-ve-iklim-elektrik-uretim-tuketim-emisyon-faktorleri)

Not defterinde kullanılan değerler:

| Yıl | İletim (tCO₂e/MWh) | Dağıtım (tCO₂e/MWh) |
| --- | --- | --- |
| 2020 | 0,427 | 0,462 |
| 2021 | 0,445 | 0,479 |
| 2022 | 0,445 | 0,478 |
| 2023 | 0,436 | 0,469 |

2024–2026 için not defterinde 2023 değerleri sabit tutulmuştur. Bu yöntem bir **referans senaryosudur**; daha yeni bir resmî faktörün bulunmadığı iddiasını içermez. Gelecekte güncel faktörlerle yapılacak hesaplar teslim sürümünden ayrı bir revizyon olarak ele alınmalıdır.

Tüketim noktalarının bağlantı türü bilinmediğinden iki faktör tüm veri setine ayrı ayrı uygulanır. Sonuçlar birbirine eklenmez. Ulusal faktörler İstanbul'a özgü ölçülmüş faktörler olarak yorumlanmaz.

## Yeniden üretilebilirlik sınırı

Kodun çalışması ve hesaplanan özetlerin tutarlılığı kontrol edilmiştir. Kaynak raporların tamamıyla satır bazında bağımsız mutabakat yapılmamıştır. Not defterinde planlanıp uygulanmayan yıllık rapor karşılaştırması tamamlanmış iş olarak değerlendirilmemelidir.
