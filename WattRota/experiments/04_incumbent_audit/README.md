# Rolling incumbent ve regret sınırı denetimi

`src/firma_cizelgeleme.py` özgün tam MILP matrisi üzerinden aday kontrolü yapar. Optimizasyon başlatmaz. Rolling uygulama, d0/d1/d2 dosyalarının yalnız uygulanmış 24 saatlerinden yeniden birleştirilir. Bütün kısıtlar, değişken sınırları, tamsayılılık ve gerçek fiyatlı amaç denetlenir.

```powershell
.venv\Scripts\python.exe -B experiments\04_incumbent_audit\test_audit.py
.venv\Scripts\python.exe -B experiments\04_incumbent_audit\audit.py --project . --output data/results/direct_milp_04_incumbent_audit
```

Çıktı mevcutsa üzerine yazmaz. Özgün oracle sonucu ve ham pilot dosyaları değişmez. Doğrulanmış en iyi bilinen uygun üst sınır, sıkılaştırılmış regret ve mevcut log incelemesi ayrı dosyalardır. Ek SQL kayıtları `results.milp_posthoc_04` içindedir; ham deney tabloları güncellenmez. Seed önerisi rolling dahil 150 MILP'dir ve çalıştırılmaz.
