"""Tahmine dayalı plan fiyatı, gerçekleşmiş gelecek fiyattan etkilenmemeli."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from tahminli_cizelgeleme import KARAR_ZAMANI,karar_firmasini_hazirla,planlama_fiyatlarini_hazirla
from firma_verisi import firma_planini_dogrula

if __name__=='__main__':
    v=karar_firmasini_hazirla(proje)
    firma_planini_dogrula(v)
    f=v['fiyatlar']
    tahmin=pd.DataFrame(dict(bolum=['ileri_donem_2026']*48,model=['ornek']*48,
                            karar_zamani=[KARAR_ZAMANI]*48,tarih_saat=f['tarih_saat'].iloc[24:].to_numpy(),
                            tahmin=np.arange(48,dtype=float)+1000))
    bozuk=f.copy();bozuk.loc[24:,'PTF (TL/MWh)']=999999
    for ad in ['basit_tahmin','ml_tahmin']:
        x,r=planlama_fiyatlarini_hazirla(f,ad,tahmin,'ornek')
        x2,r2=planlama_fiyatlarini_hazirla(bozuk,ad,tahmin,'ornek')
        pd.testing.assert_frame_equal(x,x2)
        np.testing.assert_allclose(x['PTF (TL/MWh)'].iloc[:24],f['PTF (TL/MWh)'].iloc[:24])
        np.testing.assert_allclose(x['PTF (TL/MWh)'].iloc[24:],tahmin['tahmin'])
        assert list(x.columns)==['tarih_saat','PTF (TL/MWh)']
        try:planlama_fiyatlarini_hazirla(f,ad,tahmin.iloc[:-1],'ornek')
        except ValueError:pass
        else:raise AssertionError('Eksik tahminle plan kurulmasına izin verildi.')
    x,_=planlama_fiyatlarini_hazirla(f,'tum_fiyatlar_biliniyor')
    pd.testing.assert_frame_equal(x.reset_index(drop=True),f.reset_index(drop=True))
    print('Ilk 24 saat korundu; gercek gelecegi degistirmek tahminli plan fiyatini degistirmedi.')
    print('Eksik tahmin reddedildi; karar firmasinin referans plani dogrulandi.')
