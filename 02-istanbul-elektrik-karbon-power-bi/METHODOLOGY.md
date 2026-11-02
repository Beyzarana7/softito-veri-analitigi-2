# Yöntem ve dosya incelemesi

## Ham veriden modele

Ham tüketim dosyası 400 satır ve 10 sütun içerir. Beş tüketici grubunun adları dönemlere göre değiştiği için ham dosyada yedi farklı sektör etiketi vardır. Veri hazırlama, raporun dört Power Query sorgusunda gerçekleştirilir:

1. `Elektrik_Tuketimi`: UTF-8 CSV'nin ilk sekiz alanını okur; ilk satırı başlık yapar. Veri tiplerini belirler ve noktalı ondalık tüketim değerlerini `en-US` kültürüyle sayıya dönüştürür.
2. Aynı sorguda `Kamu ve Özel Hizmetler Sektörü ile Diğer` → `Hizmetler/Ticarethane`, `Tarımsal Faaliyetler` → `Tarım` eşlemeleri yapılır. Yıl ve aydan ay başlangıcı tarihi oluşturulur.
3. `Dim_Sektor`: dönüştürülmüş tüketim sorgusundan tekil sektörleri alır.
4. `Dim_Takvim`: dönüştürülmüş tüketim sorgusundan tekil ay başlangıçlarını, yıl/ay numarası ve Türkçe ay adını üretir.
5. `Emisyon_Faktorleri`: noktalı virgülle ayrılmış dosyayı Türkçe ondalık virgül ayarıyla dönüştürür.

Sorguların özgün metinleri `model/*.pq` dosyalarındadır. Açılışta bulunan 400 gömülü tüketim kaydı, ham dosyaya yukarıdaki iki sektör eşlemesi uygulandıktan sonra ortak sekiz alan üzerinden karşılaştırılmış ve tüm alanlarda eşleşme bulunmuştur. Ek kaynak alanları ham CSV'de korunur.

## Dönem ve karşılaştırma mantığı

- Dönem ölçüleri `MAX(Dim_Takvim[Yıl])` ile son seçili yılı belirler. Çoklu seçim yılların tüketimini tek KPI'da toplamaz.
- Önceki yıl karşılaştırmasında son seçili yıldaki ay numaraları önceki yılda eşlenir. Eşleşen ay sayısı yetersizse boş sonuç döner.
- Yüzde değişim: `(bu dönem − önceki dönem) / önceki dönem`.
- Sektörün yüzde puan katkısı: `100 × sektörün mutlak tüketim farkı / seçili sektörlerin önceki dönem toplamı`. Sektörün kendi büyüme oranıyla aynı değildir.
- 12 aylık hareketli ortalama, ancak 12 takvim ayı ve 12 verili ay varsa gösterilir. İlk 11 ayda boş olması beklenir.
- Günlük ortalama, tüketimi kapsanan ayların gerçek gün sayısına böler; şubat ve artık yıl farkını dikkate alır.
- Isı haritası sayısal hücreleri MWh/gün gösterir; renkler sektör içi mevsimsellik endeksine dayanır.
- Emisyon çizgilerinde seçili son yılda bulunan aylar diğer yıllarda da kullanılır. Böylece 2026 sekiz aylıkken daha önceki yılların tamamıyla kıyaslanmaz.

## Emisyon kapsamı

Satır bazındaki tüketim ilgili yılın faktörüyle çarpılır ve toplanır. Faktör birimi tCO₂e/MWh olduğu için çıktı tCO₂e'dir. Rapor kartlarında milyon birimine dönüştürülür.

İletim ve dağıtım alternatif bağlantı senaryolarıdır. Veride bağlantı türü ayrımı bulunmadığı için İstanbul'un gerçek iletim/dağıtım tüketim karması tahmin edilmez. 2024–2026 hesaplarında kullanılan 2023 sabit faktörü, bu yılların emisyon değişiminin tüketim değişimini izlemesine neden olur. Grafik bir tahmin modeli veya İstanbul'un toplam karbon envanteri değildir.

## Bu incelemede yapılan kontroller

- PBIX arşivi ve rapor tanımları açıldı: tek sayfa, 23 görsel kapsayıcı, 29 DAX ölçüsü ve dört Power Query sorgusu incelendi.
- Üç aktif çoktan-bire, tek yönlü model ilişkisi doğrulandı.
- PBIX'in gömülü tüketim ve faktör tabloları çıkarılarak CSV'lerle karşılaştırıldı. Sayısal tüketim farkı tüm kayıtlarda sıfırdır.
- 400 tüketim kaydında eksik alan, negatif tüketim ve yıl/ay/ham sektör anahtarı tekrarı bulunmadı. Standartlaştırmadan sonra 80 ayın her birinde beş grup bulunur.
- Genel toplamlar, 2026/2025 aynı dönem farkı ve sektör katkıları bağımsız Python hesabıyla yeniden üretildi.
- Rapor tanımında A bölümüne yıl/ay dilimleyicilerinin etki etmediği, sektör dilimleyicisinin etki ettiği kontrol edildi.

## Kontrolün sınırları ve kullanım notları

Bu inceleme PBIX'in kayıtlı veri, sorgu, ölçü ve rapor tanımlarına dayanır. Bu ortamda Power BI Desktop açılıp DAX motoru, yenileme ve etkileşimler canlı çalıştırılmamış; son rapor ekranı görsel olarak doğrulanmamıştır. Bağımsız Python kontrolü DAX motorunun tüm filtre bağlamlarını test etmiş sayılmaz. Kaynak EPDK/ETKB belgeleri bu incelemede yeniden satır bazında denetlenmemiştir.

Genel dönem özet satırı statik bir metindir; veri yenilenip kapsam değişirse metnin güncellenmesi gerekir. Bu satır seçili dönemin dinamik KPI'larıyla karıştırılmamalıdır. Sektör seçimi tekil bir gruba indirildiğinde katkıların paydası da seçili gruba iner. A bölümü uzun dönem profili olarak tasarlandığı için dilimleyicilerden farklı dönem gösterebilir; bölüm başlığında bu davranış belirtilir.

Ham dosya, PBIX ve emisyon faktörleri teslim edilen içerikleriyle korunmuştur. GitHub için yalnızca dosya adları düzenlenmiş, açıklama ve okunabilir sorgu/ölçü dökümleri eklenmiştir.
