# Planlama akışı

`scripts/planlama_calistir.py`, kayıtlı firma tablolarını okur, fiyat girdisini hazırlar, çizelgeyi hesaplar ve bağımsız fiziksel/maliyet kontrollerinden geçen sonucu yeni bir klasöre kaydeder. Firma takvimi ve işletme kuralları CSV tablolarından alınır; tarihler otomatik taşınmaz.

Proje kökünden:

```text
python scripts/planlama_calistir.py --yontem aciklanmis
python scripts/planlama_calistir.py --yontem basit
python scripts/planlama_calistir.py --yontem ml
```

- `aciklanmis`: Kayıtlı 72 saatin tamamının fiyatlarının bilindiği planlama. Tarihsel veriyle kullanıldığında tam fiyat bilgili karşılaştırmadır; ileri günler için uygulanabilir bir tahmin değildir.
- `basit`: İlk günün 24 saatlik açıklanmış profilini sonraki iki gün için tekrarlar.
- `ml`: İlk günün açıklanmış profilinden sapmayı öğrenen mevcut `hgb_duzeltme_365` modelini kullanır. Daha düşük gerçekleşmiş üretim maliyeti garantisi vermez.

Tahminli seçeneklerde ilk 24 saatin tamamının açıklanmış olduğu varsayılır. Sonraki 48 saatin gerçek fiyatları model eğitimine veya çizelge seçimine verilmez. Gerçekleşmiş fiyatlar dosyalarda varsa plan seçildikten sonra ayrıca maliyet değerlendirmesi yapılır. Bu değerlendirme, tahmini maliyetten ayrı dosyada tutulur.

Her çalıştırmanın çıktıları `data/results/planlama` altında yeni bir klasöre yazılır. `karsilastirma.csv` planlamada kullanılan fiyatlarla karşılaştırmadır. Varsa `gerceklesen_karsilastirma.csv` tarihsel gerçekleşmiş fiyatlarla değerlendirmedir. `sonuc.json` çözücü durumunu, optimalite açığını, kontrol sonuçlarını ve kaynak dosyaların özetlerini içerir. Süre sınırında bulunan uygun plan kesin optimum olarak adlandırılmaz.

`--sure` ana aramanın saniye cinsinden süresidir; mevcut yerel iyileştirmeler ayrıca süre alabilir. `--degisiklik-gideri`, değişen üretim kaynak-saati başına TL cinsinden senaryo parametresidir. Karşılaştırılan maliyet PTF bedeli ve modelde tanımlı ek giderleri kapsar; toplam elektrik faturası değildir.
