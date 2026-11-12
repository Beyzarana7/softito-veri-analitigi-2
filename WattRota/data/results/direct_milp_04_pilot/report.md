# Görev 4 — dört haftalık PostgreSQL MILP pilotu

Geliştirme fold indeksleri 0, 11, 22, 33 önceden sabitlendi. Kilitli 10 hafta açılmadı. 34 haftalık çalışma başlatılmadı.

Firma ve fiyat geçmişi kod.db PostgreSQL okuma katmanından alındı. Tahminler bu geçmişten yeniden üretildi; CSV tahmin veya aday plan havuzu optimizasyon girdisi değildir. 19 plan arşivi yalnız çıktı yeniliğini denetlemek için kullanıldı.

Her haftada aynı ayarlarla 7 MILP: bir gerçek-fiyat oracle, iki ilk karar ve her yöntem için iki günlük yeniden çözüm. HGB/ensemble açık döngü ve rolling ilk çözümü aynıdır; ekstra koşumların en iyisi seçilmedi. Başlangıç referansı ilk çözümlere warm starttır; ertesi gün geçmişe uygun son plan devamı warm start olur.

Her MILP: 15 saniye, gap hedefi 0.001, seed 42, tek thread, yerel ön arama kapalı. Süre sınırı solver.run içindir; kurulum/tahmin/doğrulama ayrıca ölçülür.

Rolling ufuk, aynı üç günlük sipariş için 72→48→24 saattir. Geçmiş tam modelde sabitlenir; stok, ürün ayarı, minimum süre ve iş emri ilerlemesi sıfırlanmaz. Yalnız o günün 24 saati uygulanır; uygulanan günlük maliyetlerin toplamı birleşik son planın gerçek maliyetiyle karşılaştırılır.

Oracle tam MILP uzayında gerçek fiyatlarla çözülür; süre/gap nedeniyle bulunan plan kesin optimum değildir. C* ∈ [oracle alt sınırı, oracle uygun plan maliyeti]. Bu yüzden gerçek regret için alt/üst aralıklar, kesin sertifika varsa exact_regret; ayrıca oracle bulunan planına göre ham fark ayrı tutulur. Negatif ham fark, gerçek negatif regret diye sunulmaz. Tahminli/rolling amaçlarının alt sınırları oracle sınırı yerine kullanılmaz.

Bilgi yakalama oranı toplam kazanç / toplam oracle potansiyelidir; haftalık oran ortalaması değildir. Oracle optimumu kesin değilse bu oran da bulunan oracle plana göre geçicidir; gerçek oran sınırları ayrıca verilir. Payda sıfırsa tanımsızdır.

| Politika | Ortalama gerçek maliyet TL | Oracle plana fark TL | Gerçek regret alt–üst TL | Toplam bilgi yakalama (geçici) |
|---|---:|---:|---|---:|
| ensemble_open | 472017.39 | 0.00 | 0.00–32366.10 | tanımsız |
| ensemble_rolling | 471648.73 | -368.66 | 0.00–31997.44 | tanımsız |
| hgb_open | 472017.39 | 0.00 | 0.00–32366.10 | tanımsız |
| hgb_rolling | 471648.73 | -368.66 | 0.00–31997.44 | tanımsız |
| oracle_incumbent | 472017.39 | 0.00 | 0.00–32366.10 | tanımsız |
| reference | 472017.39 | 0.00 | 0.00–32366.10 | tanımsız |

28 çözüm bağımsız kontrol edildi. İhlal: 0. Oracle kesin sertifikalı hafta: 0/4. Eski 19 planın dışında çıktı: 8 koşum. SQL satırları: {'milp_runs_04': 28, 'milp_weekly_04': 24}; çift yüklemede içerik ve sayılar aynı.

## Süre ve onay noktası

Pilot toplamı: 8.05 dakika. 34 haftanın gözlenen hafta ortalamasından tahmini: 68.01 dakika. Gözlenen en kısa/uzun haftanın ölçeklenmesi: [59.7336913266452, 72.0136309567024] dakika; bu bir istatistiksel güven aralığı değildir.
34 hafta kullanıcı onayı bekler. Pilot sonuçları diğer bütçeli koşumlarla birleştirilmez.

## Stokastik mod önerisi

Bu aşamada uygulanmadı. Önceki senaryoların nominal %80 aralığı yalnız %61,89 kapsama verdiği için risk modeli güvenilir biçimde kalibre edilmiş değildir. Tek ortak çizelgede doğrusal elektrik maliyetinin senaryolar üzerindeki beklentisini minimize etmek, senaryoların ortalama fiyatıyla deterministik çözümle aynıdır; yalnız senaryo sayısını artırmak ek karar değeri sağlamaz. Gerçek ek değer için iyi kalibre edilmiş senaryolar ve açıkça tanımlı recourse/nonanticipativity veya risk hedefi gerekir. Mevcut pilot böyle bir değer iddiası taşımaz.
