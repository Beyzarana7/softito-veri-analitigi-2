"""Açıklanmış profil ve çok ufuklu özelliklerde bilgi sınırı."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from fiyat_tahmini_gelistirme import ADAYLAR,gelistirilmis_tahmin,karar_ornekleri

if __name__=='__main__':
    idx=pd.date_range('2024-01-01',periods=90*24,freq='h')
    s=pd.Series(1500+300*np.sin(2*np.pi*idx.hour/24)+50*idx.day_of_week,index=idx)
    karar=pd.Timestamp('2024-03-16');cut=karar+pd.Timedelta(hours=23)
    bozuk=s.copy();bozuk.loc[bozuk.index>cut]=999999
    for ad in ADAYLAR:
        p,b=gelistirilmis_tahmin(s,karar,ad)
        p2,_=gelistirilmis_tahmin(bozuk,karar,ad)
        p3,_=gelistirilmis_tahmin(s.loc[:cut],karar,ad)
        np.testing.assert_allclose(p,p2,atol=1e-8)
        np.testing.assert_allclose(p,p3,atol=1e-8)
        assert len(p)==48 and not p.index.has_duplicates and (p>=0).all()
        assert pd.Timestamp(b['egitim_son_hedef'])<=cut
    x,m=karar_ornekleri(s.loc[:cut],karar+pd.Timedelta(hours=71))
    hedef=m['karar_zamani'].eq(karar)
    for gun in [1,2]:
        maske=hedef&x['ufuk_gun'].eq(gun)
        np.testing.assert_allclose(x.loc[maske,'aciklanmis_ayni_saat'],s.loc[karar:cut])
    degisen=s.loc[:cut].copy();degisen.loc[karar:cut]+=100
    x2,m2=karar_ornekleri(degisen,karar+pd.Timedelta(hours=71))
    np.testing.assert_allclose(x2.loc[hedef,'aciklanmis_ayni_saat']-x.loc[hedef,'aciklanmis_ayni_saat'],100)
    print('3 adayda gelecegi degistirmek/silmek tahmini etkilemedi; her iki hedef gun aciklanmis profili kullaniyor.')
