# Veri kaynakları

Bu çalışma, önceki [Pandas analizinin kaynak ve yöntem notlarını](../01-istanbul-elektrik-karbon-analizi/SOURCES.md) temel alır.

## Tüketim

[EPDK Elektrik Piyasası Aylık Sektör Raporları](https://www.epdk.gov.tr/Detay/Icerik/3-0-23/elektrikaylik-sektor-raporlar) içindeki il ve tüketici türü bazında aylık faturalanan elektrik tüketimi tablolarından oluşturulan analiz veri setidir. Resmî bir EPDK CSV dağıtımı değildir.

Gözlemler 2020–Ağustos 2026 dönemine aittir. Kaynak raporlardaki önceki yıl karşılaştırma sütunları da kullanıldığından rapor yılı ile gözlem yılı aynı olmak zorunda değildir. İstanbul Anadolu/Avrupa ayrımı bulunan tablolarda iki bölgenin değerleri birleştirilmiştir. Kayıtların rapor kökeni `kaynak` alanında, son gönderilen 10 sütunlu sürümde ek kaynak tablo/dosya bilgileriyle birlikte tutulur.

## Emisyon faktörleri

[ETKB — Türkiye Elektrik Üretimi ve Elektrik Tüketim Noktası Emisyon Faktörleri](https://enerji.gov.tr/evced-cevre-ve-iklim-elektrik-uretim-tuketim-emisyon-faktorleri).

| Yıl | İletim, tCO₂e/MWh | Dağıtım, tCO₂e/MWh | Kullanım |
| --- | ---: | ---: | --- |
| 2020 | 0,427 | 0,462 | Veri setindeki yıllık faktör |
| 2021 | 0,445 | 0,479 | Veri setindeki yıllık faktör |
| 2022 | 0,445 | 0,478 | Veri setindeki yıllık faktör |
| 2023 | 0,436 | 0,469 | Veri setindeki yıllık faktör |
| 2024–2026 | 0,436 | 0,469 | Sabit 2023 referans senaryosu |

Bu sürümün referans varsayımı, daha güncel resmî faktörlerin bulunmadığı iddiası değildir. Ulusal tüketim noktası faktörleri İstanbul'a özgü ölçümler olarak yorumlanmaz. İki bağlantı senaryosu tüm tüketim verisine ayrı ayrı uygulanır ve birbirine eklenmez.

Kaynak yayınların hakları ilgili kurumlara aittir. PBIX ve CSV'lerin paylaşılması bu kaynaklara ilişkin açık veri lisansı veya bağımsız doğrulama garantisi oluşturmaz.
