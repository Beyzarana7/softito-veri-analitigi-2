# İstanbul'da Sektörel Elektrik Tüketimi ve Elektrik Kaynaklı Karbon Emisyonları

**Dönem:** Ocak 2020 – Ağustos 2026  
**Eğitim:** İTO SoftITo Yazılım-Bilişim Akademisi · Veri Analitiği - 2  
**Hazırlayan:** Rana Beyza Culus · **Öğrenci kodu:** 112

## Amaç ve veri seti

İstanbul'un elektrik tüketimini yıllar, aylar ve tüketici grupları açısından incelemek; elektrik tüketimine bağlı tahmini dolaylı sera gazı emisyonlarını hesaplamak.

- **Kaynak:** EPDK elektrik piyasası aylık sektör raporlarından derlenen İstanbul tüketim verileri
- **Kapsam:** Ocak 2020–Ağustos 2026; 80 ay, 5 tüketici grubu, 400 gözlem
- **Teknolojiler:** Python, Pandas, NumPy, Matplotlib
- **Analizler:** Veri temizleme, EDA, sektörel ve dönemsel karşılaştırmalar, aykırı gözlemler, emisyon senaryoları ve grafikler

## Emisyon yönteminin sınırları

2020–2023 döneminde ilgili yılın ulusal elektrik tüketim noktası emisyon faktörü; 2024–2026 için ise **2023 faktörüyle sabit referans senaryosu** kullanılmıştır. İletim ve dağıtım faktörleri ayrı senaryolar olarak hesaplanır ve birbirine eklenmez. Sonuçlar sektörlerin doğrudan saldığı toplam CO₂ miktarı değil, **elektrik tüketimiyle ilişkilendirilen dolaylı sera gazı emisyonu tahminleridir**. 2026 verileri yalnızca Ocak–Ağustos dönemini kapsar. Sektör sınıflandırmalarındaki yıllar arası değişimler karşılaştırmalarda sınırlılık oluşturur.

## Öne çıkan sonuçlar

- Toplam yıllık elektrik tüketimi 2020'de yaklaşık **38,49 milyon MWh**, 2025'te yaklaşık **44,59 milyon MWh**.
- 2025'te en büyük tüketim payı **%41,37** ile Hizmetler/Ticarethane grubuna ait.
- 2026 Ocak–Ağustos tüketimi, 2025'in aynı dönemine kıyasla **%2,39** daha yüksek.
- 2023'te tüketim artmasına rağmen yıllık emisyon faktöründeki düşüş nedeniyle hesaplanan dağıtım senaryosu emisyonu azalmıştır.

## Dosyalar

- `112_istanbul_elektrik_karbon_analizi.ipynb`: Kodlar, tablolar, grafikler ve bulgular. **112**, SoftITo kapsamındaki öğrenci kodudur.
- `istanbul_aylik_sektorel_elektrik_tuketimi_2020_2026_agustos.csv`: Kullanılan tüketim veri seti.

Her iki dosyayı aynı klasöre yerleştirerek notebook'u Jupyter veya VS Code ile çalıştırabilirsiniz. Python ortamında Pandas, NumPy ve Matplotlib bulunmalıdır. Colab'da CSV'nin oturumun çalışma dizinine yüklenmesi gerekir.

## Kaynaklar

- [EPDK](https://www.epdk.gov.tr/) — Elektrik piyasası aylık sektör raporları
- [Enerji ve Tabii Kaynaklar Bakanlığı](https://enerji.gov.tr/evced-cevre-ve-iklim-elektrik-uretim-tuketim-emisyon-faktorleri) — Elektrik tüketim noktası emisyon faktörleri

> Bu proje eğitim kapsamında gerçekleştirilmiş kişisel analizdir; resmî İstanbul karbon envanteri değildir.
