# Görev 3 sonrası karar metrikleri — geliştirme bölümü

Lasso-AR (`lear_level_1`), HGB (`hgb_expanding_cached`) ve sabit ensemble (`ensemble_level_fixed`) aynı 19 uygulanabilir planda karşılaştırılır. Dünkü gün naive kıyası kontrol olarak korunur. Yalnız Görev 2'nin 34 geliştirme haftası kullanılır; kilitli 10 hafta açılmaz.

```text
python -B -m unittest discover -s experiments/03_decision_evaluation -p test_decisions.py -v
python -B experiments/03_decision_evaluation/run.py --project . --output data/results/development_decisions_03
```

Kaynak tahminlerin ve eski protokolün özetleri doğrulanır. Tahmin edilen 48 saat dışında ilk gün her yöntemde açıklanmış fiyatlardan alınır. Yeni model eğitilmez; yeni MILP çözülmez. Referans, seçilen ve havuz minimumu planları bağımsız fiziksel/maliyet doğrulayıcısından geçirilir. Basit kıyas Görev 1'in aynı haftalarıyla karşılaştırılır.

Regret ve bilgi yakalama yalnız **plan havuzuna göredir**. Tam MILP oracle mevcutmuş gibi raporlanmaz. Payda sıfıra yakınsa oran tanımsızdır; negatif oranlar korunur. Haftalık oranların ortalaması ve toplam kazanç/toplam potansiyel ayrı verilir.

Bu ek değerlendirme ayrı commit olarak önerilir; kullanıcı onayı olmadan commit atılmaz.
