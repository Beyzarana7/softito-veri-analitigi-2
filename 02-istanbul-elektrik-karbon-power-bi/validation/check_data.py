"""CSV tutarlılığı ve rapordaki temel hesaplar. Yalnızca Python standart kütüphanesi."""
from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal
import calendar
import csv

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "Kamu ve Özel Hizmetler Sektörü ile Diğer": "Hizmetler/Ticarethane",
    "Tarımsal Faaliyetler": "Tarım",
}
with (ROOT / "data/istanbul_aylik_sektorel_elektrik_tuketimi_2020_2026_agustos.csv").open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
with (ROOT / "data/Emisyon_Faktorleri.csv").open(encoding="utf-8-sig", newline="") as f:
    factor_rows = list(csv.DictReader(f, delimiter=";"))

assert len(rows) == 400
assert len(factor_rows) == 7
assert all(all(value not in (None, "") for value in r.values()) for r in rows)
factors = {int(r["yil"]): (Decimal(r["iletim_faktoru"].replace(",", ".")), Decimal(r["dagitim_faktoru"].replace(",", "."))) for r in factor_rows}
assert len(factors) == 7
keys = []
annual = defaultdict(Decimal)
monthly = defaultdict(Decimal)
sectors = defaultdict(Decimal)
emissions = [Decimal(0), Decimal(0)]
for r in rows:
    y, m = int(r["yil"]), int(r["ay"])
    s = ALIASES.get(r["tuketici_turu"], r["tuketici_turu"])
    v = Decimal(r["elektrik_tuketimi_mwh"])
    assert v >= 0 and r["birim"] == "MWh" and r["il"] == "İstanbul"
    assert 1 <= m <= 12
    keys.append((y, m, s))
    annual[y] += v
    monthly[y, m] += v
    sectors[y, m, s] += v
    for i, factor in enumerate(factors[y]):
        emissions[i] += v * factor
assert len(set(keys)) == 400
assert len(monthly) == 80
assert set(monthly) == {(y, m) for y in range(2020, 2027) for m in range(1, 9 if y == 2026 else 13)}
assert set(Counter((y, m) for y, m, _ in keys).values()) == {5}
assert len({s for _, _, s in keys}) == 5
assert sum(annual.values()) == Decimal("283869173.152332")
assert abs(emissions[0] - Decimal("124166909.181046752")) < Decimal("0.001")
assert abs(emissions[1] - Decimal("133652385.348623708")) < Decimal("0.001")
prev = sum(monthly[2025, m] for m in range(1, 9))
current = annual[2026]
growth = 100 * (current - prev) / prev
assert abs(growth - Decimal("2.39262651236")) < Decimal("0.000001")
assert sum(calendar.monthrange(y, m)[1] for y, m in monthly if y <= 2025) == 2192
print("OK: 400 kayıt, 80 ay, 5 standart grup; eksik/tekrarlı anahtar yok.")
print(f"Toplam tüketim: {sum(annual.values()):,.6f} MWh")
print(f"İletim senaryosu: {emissions[0]:,.6f} tCO2e")
print(f"Dağıtım senaryosu: {emissions[1]:,.6f} tCO2e")
print(f"2026 Ocak–Ağustos: {current:,.6f} MWh; aynı dönem değişimi: %{growth:.6f}")
print("Sektörel katkılar (2026/2025 Ocak–Ağustos; tüm sektörler):")
for s in sorted({s for _, _, s in keys}):
    delta = sum(sectors[2026, m, s] - sectors[2025, m, s] for m in range(1, 9))
    print(f"  {s}: {delta:+,.6f} MWh / {100 * delta / prev:+.6f} yüzde puan")
