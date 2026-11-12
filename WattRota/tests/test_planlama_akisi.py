"""Ana akışın geleceği görmeden fiyat hazırladığını kontrol eder."""
from pathlib import Path
import sys
import pandas as pd

proje = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(proje / 'src'))
from firma_cizelgeleme import firma_verisini_oku
from fiyat_tahmini import elektrik_fiyatlarini_oku
from planlama_akisi import planlama_girdisini_hazirla


if __name__ == '__main__':
    firma = firma_verisini_oku(proje)
    fiyat = elektrik_fiyatlarini_oku(proje)
    orijinal = firma['fiyatlar'].copy(deep=True)
    karar = firma['tesis_takvimi']['tarih_saat'].min()
    kesim = karar + pd.Timedelta(days=1)
    bozuk = fiyat.copy()
    bozuk.loc[bozuk.index >= kesim] = 999999.0
    for yontem in ('basit', 'ml'):
        v, rapor, bilgi = planlama_girdisini_hazirla(firma, fiyat, yontem)
        v2, _, _ = planlama_girdisini_hazirla(firma, bozuk, yontem)
        v3, _, _ = planlama_girdisini_hazirla(firma, fiyat.loc[fiyat.index < kesim], yontem)
        pd.testing.assert_frame_equal(v['fiyatlar'], v2['fiyatlar'])
        pd.testing.assert_frame_equal(v['fiyatlar'], v3['fiyatlar'])
        assert rapor['bilgi_turu'].value_counts().to_dict() == {'tahmin': 48, 'aciklanmis': 24}
    pd.testing.assert_frame_equal(firma['fiyatlar'], orijinal)
    try:
        planlama_girdisini_hazirla(firma, fiyat.drop(karar), 'basit')
    except ValueError:
        pass
    else:
        raise AssertionError('Eksik açıklanmış saat reddedilmedi.')
    print('Basit ve ML fiyat girdileri gelecek fiyatlardan etkilenmedi; eksik ilk gün reddedildi; firma girdileri korundu.')
