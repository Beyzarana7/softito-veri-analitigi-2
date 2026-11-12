# Karar odaklı değerlendirme — görev 1

Bu klasör mevcut tahmin/plan deneylerini salt okunur kullanır; eski sonuçları değiştirmez. Modelleri yeniden eğitmez, PostgreSQL ve arayüz koduna müdahale etmez.

## Mevcut kod haritası

- `src/firma_verisi.py`: sentetik firma girdileri ve bağımsız fiziksel plan denetimi.
- `src/firma_cizelgeleme.py`: CSV okuma, HiGHS MILP, maliyet hesabı ve sonuç kaydetme.
- `src/planlama_akisi.py`: fiyat hazırlama, çizelgeleme ve bağımsız kontrolleri birleştiren akış.
- `src/fiyat_tahmini.py`, `src/fiyat_tahmini_gelistirme.py`: temel/ML fiyat tahminleri ve tarihsel değerlendirme.
- `src/ortak_plan_karsilastirmasi.py`: aynı 19 uygulanabilir plan üzerindeki karşılaştırma.
- `src/firma_senaryolari.py`, `src/karar_*.py`, `src/kazanc_*.py`: senaryo, karar maliyeti ve kazanç teşhis deneyleri.
- `notebooks/01`–`08`: veri analizi, firma girdileri, çizelgeleme, tahmin ve karar değerlendirmesi sunumları.
- `scripts/veritabani_sql_hazirla.py`, `sql/`: PostgreSQL ilk aktarım ve veri bütünlüğü sorguları. Ana Python akışı CSV okumaktadır.

## Çalıştırma

Proje kökünden, proje Python ortamıyla:

```text
python -m unittest discover -s experiments/01_karar_degerlendirme -p test_metrics.py -v
python experiments/01_karar_degerlendirme/run.py --project . --output data/results/karar_degerlendirme_01_yeni
```

Çıktı klasörü mevcutsa üzerine yazılmaz. Ayarlar `config.json` dosyasındadır. Kayıtlı deneyin kaynak dosyası izleri veya girdi dosyaları uyuşmazsa çalışma durur.

## Ölçüm kapsamı

44 haftalık üç yöntem, 19 planlık aynı havuzda değerlendirilir. Havuz-oracle, bu havuzun gerçekleşmiş fiyatlarla tam taranmış minimumudur; bütün MILP uzayının optimumu değildir. Bu aşamada tam-MILP haftalık regret hesaplandığı iddia edilmez. Üç eski oracle örneği 44 haftaya taşınmaz.

Haftalık tabloda havuz regret, bilgi değeri yakalama, MAE, sabit referans/ seçilen plan yüküyle ağırlıklı MAE, fiyat ve plan maliyeti sıralama korelasyonları ve günlük en ucuz altı saati bulma oranları bulunur. Eşit fiyatlar ve tanımsız oranlar açıkça ele alınır. Karşılaştırmalar, ilk günün bilinen fiyat hatasıyla yapay olarak iyileştirilmez: fiyat metrikleri yalnız kalan 48 saatte ölçülür.

Bootstrap maliyet farkları eşleştirilmiş haftalar üzerinde hesaplanır. Bağımsız haftalar varsayımına karşı dört haftalık blok duyarlılığı da verilir. 2026 dönemi önceden görülmüş olduğundan bu bir kör test değildir. Son 10 haftanın ileriye dönük yeni protokolde kilitlenmesi geçmişte görülmüş olmasını ortadan kaldırmaz.

## Çıktılar

- `haftalik_metrikler.csv`: hafta/yöntem bazında maliyet ve tahmin metrikleri.
- `model_ozeti.csv`: yöntem özetleri ve tanımlı metrik sayıları.
- `eslestirilmis_bootstrap.csv`: A−B ortalama maliyet farkı ve %95 aralıkları.
- `metrik_karsilastirmasi.png/pdf`, `haftalik_regret.png`, `bootstrap_guven_araliklari.png`.
- `rapor.md`: tanımlar, bulgular ve kapsam sınırları.
- `deney_bilgisi.json`: config, kaynak/girdi özetleri ve kontrol sayıları.

## Git kontrol noktası

İnceleme sırasında proje klasörü Git deposu değildi. Yeni bir depo oluşturulduktan sonra yalnız bu aşamanın kodu ve raporları için önerilen commit başlığı:

`feat: add reproducible decision-focused forecast evaluation`

Sanal ortam, parolalar ve geçici dosyalar commit edilmemelidir. Mevcut `.gitignore`, `.venv/` ve `.env` dosyalarını dışlar.
