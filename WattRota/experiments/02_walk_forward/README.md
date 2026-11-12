# Genişleyen pencereli walk-forward protokolü — görev 2

Mevcut kod ve sonuçlar değiştirilmez. Bu deney, önceki 180/365 günlük sabit pencere sonuçlarından ayrı yürütülür. Aynı temel model türleri kullanılır; eğitim geçmişinin sol sınırı 1 Ocak 2024'te sabittir, sağ sınırı her haftada ilerler.

## Zaman ve bilgi sözleşmesi

- Karar haftaları pazartesi 00.00'da başlayan tamamlanmış 72 saatlik örneklerdir.
- Birinci günün bütün 24 saatlik fiyatının açıklanmış olduğu varsayılır. Eğitime ve özelliklere yalnız bu günün sonuna kadar bilinen fiyatlar verilir.
- Sonraki 48 saatin fiyatları tahmin edildikten sonra puanlama için okunur. Bu hedefler eğitimde kullanılamaz.
- 2026'da tamamlanmış 44 örneğin ilk 34'ü geliştirme, son 10'u kilitli değerlendirmedir. Geliştirme kararları 5 Ocak–24 Ağustos; kilitli kararlar 31 Ağustos–2 Kasım'dır. Son kilitli hedef saati 4 Kasım 23.00'dır. 6 Kasım'da biten veri içindeki tamamlanmamış gelecek haftalar alınmaz.
- Kilitli haftalar **önceden görülmüş tarihsel dönemdir**. Kilit, bundan sonraki seçim/ayar disiplinini sağlar; dönemi geçmişe dönük olarak kör test yapmaz.

## Ayarlar ve sürümleme

Seed, iş parçacığı sayısı, tarih/ufuk, kilitli hafta sayısı, seçim ölçütü, minimum eğitim büyüklüğü ve model parametreleri `config.json` içindedir. Özellik tanımları mevcut iki sürümlenmiş üreticiden alınır; kaynak dosyalarının SHA-256 özetleri kilide dahildir. Gizli bir hiperparametre araması yapılmaz. Bu aşamada mevcut parametreler sabit tutulur.

`rf_expanding`, mevcut RF özelliklerini bütün uygun geçmişle kullanır. `hgb_residual_expanding`, açıklanmış gün profilinden sapmayı bütün uygun geçmişle öğrenir. Eski `random_forest_365gun` / `hgb_duzeltme_365` sonuçlarıyla aynı deney olarak adlandırılmaz.

## Çalıştırma

Proje kökünde, proje Python ortamıyla:

```text
python -B -m unittest discover -s experiments/02_walk_forward -p test_protocol.py -v
python -B experiments/02_walk_forward/run.py --project . --output data/results/walk_forward_02 --phase prepare
python -B experiments/02_walk_forward/run.py --project . --output data/results/walk_forward_02 --phase development
```

Kilitli test komutu ayrı bir işlemdir:

```text
python -B experiments/02_walk_forward/run.py --project . --output data/results/walk_forward_02 --phase locked-test --confirm-locked-test
```

Görev 2 tamamlanırken kilitli test çalıştırılmaz. Geliştirme sırasında her aday yalnız geliştirme haftalarında değerlendirilir; eşit sayıda 48 saatlik hedef ve aynı haftalar zorunludur. Seçim MAE, eşitlik durumunda model kimliği sırasıyla yapılır. Seçim, config ve geliştirme çıktıları özetlerle mühürlenir. Testte mühürlü kazanan ile naive kıyas çalışır; tekrar seçim yapılmaz.

Gerçek zamanlı kullanımı taklit etmek için sonraki bir test haftasının yeniden eğitiminde, o tarihte artık geçmişte kalmış önceki test fiyatları kullanılabilir. Bu **parametre/model seçimi** değildir. Gelecek haftanın henüz açıklanmamış fiyatları kullanılamaz. Bütün yeniden eğitimler `training_audit.csv` içinde kaydedilir.

Kilit dosyası, kaynak/veri/config veya fold tanımı değişirse çalışma durur. Mevcut çıktı klasörlerinin üzerine yazılmaz; deney sürümü değiştirilerek yeni klasör gerekir. Bu yazılımsal bir bütünlük kontrolüdür, dosya sisteminde erişim denetimi değildir.

## Çıktılar

- `folds.csv`: geliştirme/test tarih sınırları ve bilgi kesimleri.
- `test_lock.json`, `config_snapshot.json`: ayrım, config ve kaynak/veri özetleri.
- `development/predictions.csv`: yalnız geliştirme tahminleri ve gerçekleri.
- `development/training_audit.csv`: her hafta ve modelin eğitim hedef aralığı, satır sayısı, seed ve bilgi kesimi.
- `development/scores.csv`, `model_selection.json`, `development_seal.json`: geliştirme ölçümleri ve mühürlü seçim.
- `development/run_info.json`: çalışma kapsamı ve paket sürümleri.

## Kontrol noktası

Bu aşama yeni ekonomik üstünlük iddiası üretmez; görev 3 ve sonraki deneyler için zaman ayrımı ve tekrar üretilebilir eğitim altyapısını sağlar. Yeni modeller veya ayarlar eklenirse mevcut kilitli protokol sessizce değiştirilmez; yeni protokol sürümünde aynı test haftaları korunur ve önceki görülmüşlük belirtilir.

Önerilen commit: `feat: add locked temporal split and expanding walk-forward protocol`. Commit yalnız kullanıcı onayıyla atılır.
