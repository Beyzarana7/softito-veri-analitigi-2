# Fiyat tahmini geliştirme — görev 3

Bu modül eski sonuçları değiştirmez. Görev 2'nin mühürlü geliştirme/test sınırlarını kullanır; test haftalarını puanlamaz. Yeni modeller için ayrı config ve kaynak özetleri saklanır. Ana requirements dosyasını değiştirmeden ek bağımlılık `requirements.txt` dosyasındadır.

```text
python -m pip install -r experiments/03_price_models/requirements.txt
python -B -m unittest discover -s experiments/03_price_models -p test_forecasts.py -v
python -B experiments/03_price_models/run.py --project . --output data/results/price_models_03
```

## Deney

- Aynı saat dün (ikinci gün özyinelemeli), geçen hafta ve 28 günlük hafta içi/sonu naive.
- Saat ve ufuk bazında 48 ayrı Lasso-AR; seviye için alpha 1/10, profil için 0,001/0,01.
- LightGBM: seviye, günlük ortalamaya normalize profil ve iki aşamalı sıfır/pozitif fiyat.
- Önceden sabit eşit ağırlıklı iki ensemble. Görev 2'deki HGB tahminleri mühür kontrolüyle yeniden kullanılır.
- LEAR, orijinal modelin birebir kopyası değildir: standartlaştırılmış Lasso-AR uyarlamasıdır; asinh dönüşümü, AIC seçimi ve dış değişkenli orijinal özellik matrisi aynen uygulanmaz. Dış kaynak kodu kopyalanmamıştır.

Gerçek hedef gün ortalaması yalnız **geçmiş eğitim hedefini** normalize eder. Tahmin anında günlük ortalama ayrı bir LightGBM ile tahmin edilir; gerçek gelecek ortalaması kullanılmaz. Saatlik profil kendi ortalamasıyla tekrar normalize edilerek tahmini günlük ortalamayla çarpılır. Tarihsel sıfıra yakın günlük ortalamalar epsilon=1 ile ele alınır.

Takvim kaynakları ve kimliksiz EPİAŞ denemesi `sources.json` içindedir. Yük tahmini isteği HTTP 401 döndürmüştür. Yetkili TGT ve tahmin anındaki tarihsel veri sürümleri olmadan yük/rüzgâr/güneş gerçekleşmeleri modele katılmaz. Dış değişken katkısı değerlendirilmiş sayılmaz.

## DM ve belirsizlik

DM için 48 saatlik hatalar her haftada önce ortalanır. 34 haftalık kayıp farkına Newey–West/Bartlett HAC (0 ve 3 haftalık gecikme) uygulanır; her gecikme için bütün ikililere Holm düzeltmesi verilir. Seçim için kullanılan geliştirme verisinde yapılan bu testler keşifseldir; test başarısı veya modelin genel üstünlüğünün kanıtı olarak yorumlanmaz.

Sabit LightGBM-seviye modelinin 2025 son çeyreğindeki 12 OOS tahmin yoluyla artık havuzu başlatılır. Sadece o anda gerçekleşmiş yollar eklenir. Her haftada 30 adet 48 saatlik artık yolu örneklenir; açıklanmış ilk 24 saat sabit kalır. Senaryo olasılıkları eşittir. Kapsama, aralık genişliği ve pinball kayıpları raporlanır; kalibrasyon garantisi verilmez.

## Çıktılar

`model_scores.csv`, `predictions.csv`, `training_audit.csv`, `dm_tests.csv`, `zero_predictions.csv`, `scenario_prices.csv`, `scenario_audit.csv`, `probabilistic_forecasts.csv`, `calibration_predictions.csv`, grafikler, `experiment_info.json` ve `report.md`.

`training_audit.csv` içindeki `training_rows` ve `training_last_label`, o haftadaki ortak uygun eğitim havuzunu gösterir. Naive yeniden eğitim yapmaz; cached HGB önceki mühürlü tahmini okur; iki aşamalı modelin pozitif fiyat bileşeni daha küçük alt kümeyi kullanır. Bu sütunlar her modelin tek bir fit çağrısındaki örnek sayısı olarak yorumlanmamalıdır.

Senaryolara tarihsel, sürümlenmiş üst fiyat limitleri uygulanmamıştır. Bu limitlerin karar anındaki sürümleri ayrıca edinilmeden senaryoların tüm piyasa sınırlarını temsil ettiği söylenemez. Alt sınır sıfırdır. `verify_results.py` sonuç tablolarını, tam ayarlı gelecek-bozma tekrarını ve senaryo yollarını doğrular; `verification.json` kaydını ve rapor bulgularını üretir.

Yakınsama uyarıları gizlenmez. Uyarı veren Lasso adayları ve onlara bağlı ensemble seçimden dışlanır; skorları yine gösterilir. Config/source/input özetleri kaydedilir ve çalışma sonunda tekrar kontrol edilir. Mevcut çıktı klasörlerinin üzerine yazılmaz.

Önerilen commit: `feat: compare price models and generate leakage-safe forecast scenarios`. Kullanıcı onayı olmadan commit atılmaz.
