# Tahmin geliştirme ve karar doğrulaması

## Amaç ve başlangıç bulgusu

İlk Random Forest modelinin fiyat hatası, basit gün tekrarından 2026 ortalamasında biraz düşüktü; tek üretim örneğinde ise daha ucuz karar sağlayamadı. İnceleme, yalnız fiyat hatasını değil, hatanın saat sıralamasını ve çizelge seçimini nasıl etkilediğini de kapsar.

Eski modelin ortak gecikme düzeninde en yeni fiyat girdisi t−48 idi. Bu bilgi sınırını koruyordu, ancak ikinci gün tahmininde ilk günün zaten açıklanmış profilinin tamamını doğrudan kullanmıyordu. 2025 ikinci gün hatası eski modelde yaklaşık 365 TL/MWh, basit yöntemde 319 TL/MWh idi. Bu gözlem geliştirme için gerekçe sağladı; tek başına nedensel kanıt değildir.

## Yeni özellikler ve modeller

Her örnek satırı bir karar başlangıcı, hedef saat ve hedef günle tanımlanır. Girdiler: hedef saat/gün/ay, kaç gün ileriye tahmin yapıldığı, açıklanmış günün aynı saat fiyatı ve günlük özeti, önceki gün/hafta profili, hedef saatin önceki dört haftadaki fiyatları ve profil değişimleri. Her örnekte kullanılan bütün kaynak fiyatlar kendi karar anında açıklanmış bilgilerle sınırlıdır.

Model, hedef fiyatın açıklanmış gün profilinden farkını öğrenir. Nihai tahmin = açıklanmış günün aynı saat fiyatı + öğrenilen düzeltmedir. Negatif çıktı sıfıra sınırlandırılır; gelecek dönemin fiyat tavanı kullanılarak üst sınır uygulanmaz.

Üç aday karşılaştırılır: 180 günlük Random Forest, 180 günlük ve 365 günlük histogram tabanlı gradient boosting. Ağaç sayısı/derinliği veya boosting ayarları kodda sabittir; sonuçlara göre geniş bir parametre taraması yapılmaz. Boosting modelinde rastgele doğrulama oluşturan erken durdurma kapalıdır.

## Zaman ayrımı ve sonuçların niteliği

Fiyat modeli 2025 Ocak–Haziran'daki 26 haftalık kararın MAE'siyle seçilir. Seçim kaydedildikten sonra 2025 Temmuz–Aralık'taki 26 karar ve 2026'daki 44 karar değerlendirilir. 2025 ikinci yarı, yeni fiyat modelinin seçimine alınmaz. Eğitim her kararın bilinen fiyat kümesiyle güncellenir.

2025 ve 2026 önceki analizlerde incelenmiştir; bu geliştirme yeni, bağımsız ve hiç görülmemiş bir kör test iddiası taşımaz. Özellikle 2026 yeniden kullanılan geriye dönük bir karşılaştırmadır. Geliştirme seçimleri 2026 hatasına göre yapılmaz.

Ucuz saat tanısı için her hedef günün tahmine göre en ucuz altı saatinin gerçek ortalama fiyatı, gerçekte en ucuz altı saatin ortalamasıyla karşılaştırılır. Birim TL/MWh'dir. Bu ölçüt saat sıralamasını inceler; gerçek fabrika maliyeti veya altı saatlik bir işin uygulanabilirliği olarak yorumlanmaz.

## Çözüm süresinden bağımsız ortak plan deneyi

Kaynak planlar yalnızca 2025'e ait referans ile kış/ilkbahar/yaz/ekim çalışmalarının uygun önerileridir. 2026 gerçek fiyatlarıyla üretilmiş planlar seçenek havuzuna alınmaz. Kaynaklar ve yükleme çizelgeleri birleştirilir; yalnız bütün işletme kurallarından geçen farklı bileşimler tutulur. Oluşan 19 seçenek `ortak_planlar.zip` içinde saklanır.

2026'nın her haftalık örneğinde tüm yöntemler tam olarak aynı seçenekleri görür. İlk gün gerçek/açıklanmış, sonraki 48 saat ilgili yöntemin tahminidir. Her seçeneğin beklenen maliyeti enerji matrisi ve başlatma/geçiş giderlerinden hesaplanır; bütün seçenekler tam taranarak en ucuz olan seçilir. Sonra gerçek fiyatlarla yeniden hesaplanır. Bütün seçilmiş planlar bağımsız tesis denetiminden geçirilir.

Bu sınırlı seçenek kümesinde arama süresi farkı yoktur. Gerçek fiyatlarla seçenekler arasındaki minimum kesin hesaplanabilir; fakat bu, fabrikanın tüm olası çizelgeleri üzerinde global optimum değildir. Deney ana MILP motorunun yerine geçmez. Aynı sentetik firmanın talep ve göreli takvim şablonu farklı fiyat haftalarına taşınır; bunlar 44 gerçek fabrika kaydı değildir.

## Karar maliyetiyle birleşim oranı

Ek kalibrasyonda basit tahmin ile seçilmiş yeni ML'nin 0 / %25 / %50 / %75 / %100 ML katkılı birleşimleri karşılaştırılır. Oran, 2025'in tamamındaki ortak plan karar maliyetinden seçilir; eşitlikte daha az ML kullanılır. 2026 birleşim sonucu görülmeden oran kaydedilir. Bu oran için 2025 ikinci yarı da kalibrasyon verisidir; bağımsız onay olarak sunulmaz. Kalibrasyonun %100 ML seçmesi, 2026'da da maliyet üstünlüğü olacağını garanti etmez.

## Ana çizelgeleme motorundaki kontrol

5 Ekim 2026 örneğinde basit yöntem ile yeni ML, aynı ortak havuzdan kendi planlama fiyatlarına göre seçilmiş uygun başlangıçlarla tam MILP modeline verilir. Her ana arama 120 saniye ve %0,1 hedef açık kullanır; ön arama süreleri ayrıca kaydedilir. Model bu başlangıçların dışındaki bütün tanımlı çizelgeleri de araştırabilir. Son planların gerçekleşmiş maliyetleri ayrı hesaplanır. Süre sınırındaki sonuçlar matematiksel optimum diye sunulmaz.

## Plan maliyetini doğrudan öğrenen ek model

Fiyat tahmini MAE'sinin azaltılması ortak seçeneklerde daha iyi karar vermediğinde, öğrenme hedefi de incelenmiştir. Bu ek model 48 saatlik fiyat üretmez; aynı 19 seçeneğin referansa göre maliyet farkında basit fiyat tekrarının ne kadar yanılacağını öğrenir. Fabrikanın bütün planlarda ortak olan temel yükü, göreli maliyet farkında kendiliğinden elenir.

Girdiler açıklanmış gün profili, hedef saatlerin önceki hafta/dört hafta profilleri ve takvimdir. Eğitim hedefi, sonraki 48 gerçek fiyatın üretim seçeneklerinin enerji farklarıyla çarpımından hesaplanan maliyet düzeltmesidir. Eğitim için o geçmiş kararın 48 saatlik hedefinin tamamının, güncel kararın bilgi sınırında açıklanmış olması zorunludur. Gelecek fiyatları değiştirme/silme testi bu bölüm için ayrıca uygulanır.

Ridge (100 ve 1000 düzenlileştirme katsayıları) ile çok çıktılı Random Forest karşılaştırılır. Öğrenilen düzeltmenin 0 / %50 / %100 katkısı dahil seçenekler, yalnız 2025 ilk yarının gerçekleşmiş karar maliyetiyle seçilir. Sıfır katkı, basit yöntemin korunmasına izin verir. Ardından seçilmiş yöntem ve katkı sabitlenerek 2025 ikinci yarı ve 2026 değerlendirilir. Bu analiz sınırlı plan kümesine özgüdür; genel amaçlı yeni bir fabrika çizelgeleyicisi değildir. Fiyat ve maliyet öğrenme modellerinin sonuçları ayrı gösterilir.

Kod `src/karar_maliyeti_modeli.py`, seçim ve karar kayıtları `maliyet_modeli_secimi.json`, `maliyet_modeli_kararlari.csv`, `maliyet_modeli_ozeti.csv` dosyalarındadır. [Ridge teknik belgesi](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).

## Dosyalar ve yeniden üretim

- `src/fiyat_tahmini_gelistirme.py`: karar anına göre özellikler, model seçimi ve tahmin tanıları.
- `src/ortak_plan_karsilastirmasi.py`: ortak seçeneklerin üretimi, tam tarama ve MILP kontrolü.
- `src/karar_odakli_tahmin.py`: 2025 karar maliyetiyle birleşim oranı.
- `data/results/tahmin_gelistirme`: protokol, tahminler, hata/ucuz saat ölçümleri, eğitim izleri ve oran kalibrasyonu.
- `data/results/ortak_plan_deneyi`: plan arşivi, enerji matrisi, haftalık seçimler, maliyet özeti ve MILP sonuçları.
- `notebooks/07_model_gelistirme_ve_karar_dogrulamasi.ipynb`: hesapların doğrulaması ve sonuçların yorumu.

```text
python src/fiyat_tahmini_gelistirme.py . data/results/tahmin_gelistirme
python src/ortak_plan_karsilastirmasi.py havuz . data/results/tahmin_gelistirme data/results/ortak_plan_deneyi
python src/ortak_plan_karsilastirmasi.py karsilastir . data/results/tahmin_gelistirme data/results/ortak_plan_deneyi
python src/karar_odakli_tahmin.py . data/results/tahmin_gelistirme data/results/ortak_plan_deneyi
python tests/test_tahmin_gelistirme.py
python tests/test_ortak_plan_deneyi.py
```

Kaynaklar: [scikit-learn HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html), [zaman sıralı gecikmeli özellik örneği](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html). Fiyatların veri kaynağı ve normal açıklanma zamanı varsayımı `fiyat-tahmini-yontemi.md` dosyasındadır.
