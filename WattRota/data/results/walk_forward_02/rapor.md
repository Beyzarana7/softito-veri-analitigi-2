# Walk-forward deney altyapısı — görev 2

Geliştirme: 5 Ocak–24 Ağustos 2026, 34 karar haftası. Kilitli bölüm: 31 Ağustos–2 Kasım 2026, 10 karar haftası. Kilitli hedef dönemi 4 Kasım 23.00 tarihinde biter. Kilitli bölüm bu çalışmada puanlanmadı.

2026 dönemi önceden incelenmiştir; ayrım yeni bir kör test değildir. Bundan sonraki model seçimi ve ayarlar için sınır oluşturur.

## Uygulama

Eğitim geçmişinin sol sınırı 1 Ocak 2024 olarak sabittir. Her haftada yalnız ilk günün sonuna kadar bilinen etiketler eklenir. Modellerin parametreleri bu aşamada sabittir; hiperparametre araması yapılmadı. İlk gün açıklanmış, sonraki 48 saat bilinmiyor varsayımı korunur.

## Geliştirme sonuçları

| Model | MAE (TL/MWh) |
|---|---:|
| hgb_residual_expanding | 492.64 |
| rf_expanding | 560.79 |
| son_yayinlanan_gun | 582.62 |

Yalnız geliştirme MAE değerine göre seçilen yöntem: **hgb_residual_expanding**. Bu seçim üretim maliyeti üstünlüğü veya test başarısı iddiası değildir. Eski 365 günlük sabit pencere skorlarıyla aynı deney değildir.

## Eğitim kayıtları

| Model | İlk eğitim satırı | Son eğitim satırı | İlk eğitim hedefi | Son eğitim hedefi |
|---|---:|---:|---|---|
| hgb_residual_expanding | 33984 | 45072 | 2024-01-29 00:00:00 | 2026-08-24 23:00:00 |
| rf_expanding | 16992 | 22536 | 2024-01-29 00:00:00 | 2026-08-24 23:00:00 |

## Doğrulama

- 4.896 geliştirme tahmini ve 102 model/hafta eğitim kaydı kontrol edildi.
- Eğitim başlangıcı sabit; ML eğitim satırı sayıları her haftada kesin olarak arttı. Eğitim hedefleri bilgi kesimini aşmadı.
- Hiçbir kilitli hafta geliştirme/puanlama kayıtlarına girmedi; kilitli test sonuç klasörü oluşmadı.
- Config, kaynak, ham veri ve fold özetleri kilitle eşleşti.
- Son geliştirme haftasında üç yöntem tam ayarlarıyla tekrar çalıştırıldı. Bilinmeyen bütün gelecek fiyatları 999.999 ile değiştirmek kayıtlı tahminleri değiştirmedi (sayısal tolerans: atol=1e-9, rtol=1e-12).
- Seed 42; parametreler, tarih kesimi, seçim ölçütü ve iş parçacığı sayısı config dosyasında.

## Sonraki çalışma

Yeni model ve hiperparametre adayları yalnız geliştirme bölümü üzerinde değerlendirilmelidir. Config/kod değişirse mevcut kilit sessizce değiştirilemez; aynı test tarihlerini koruyan yeni protokol sürümü oluşturulmalıdır. Kilitli sonuçlara bakılarak yeniden seçim yapılamaz.

Commit kullanıcı onayı bekliyor: `feat: add locked temporal split and expanding walk-forward protocol`.
