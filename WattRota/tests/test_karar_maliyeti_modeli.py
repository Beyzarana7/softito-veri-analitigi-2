"""Maliyet düzeltmesinde gelecekteki fiyatların eğitim/özelliklere sızmaması."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from karar_maliyeti_modeli import MODELLER,maliyet_duzeltmesi

if __name__=='__main__':
    zaman=pd.date_range('2024-01-01',periods=400*24,freq='h')
    fiyat=pd.Series(1500+200*np.sin(2*np.pi*zaman.hour/24)+30*zaman.day_of_week,index=zaman)
    karar=pd.Timestamp('2024-12-02');sinir=karar+pd.Timedelta(hours=23)
    zehirli=fiyat.copy();zehirli.loc[zehirli.index>sinir]=999999
    enerji=np.full((3,72),300.0)
    enerji[1,24:36]+=500;enerji[1,48:60]+=200
    enerji[2,36:48]+=500;enerji[2,60:72]+=200
    for ad in MODELLER:
        a,b,iz=maliyet_duzeltmesi(fiyat,enerji,karar,ad)
        a2,b2,_=maliyet_duzeltmesi(zehirli,enerji,karar,ad)
        a3,b3,_=maliyet_duzeltmesi(fiyat.loc[:sinir],enerji,karar,ad)
        np.testing.assert_allclose(a,a2,atol=1e-7)
        np.testing.assert_allclose(a,a3,atol=1e-7)
        np.testing.assert_allclose(b,b2);np.testing.assert_allclose(b,b3)
        assert abs(a[0])<1e-7
        assert pd.Timestamp(iz['egitim_son_karar'])+pd.Timedelta(hours=71)<=sinir
    print('3 maliyet modelinde gelecek fiyatlari degistirmek/silmek sonucu etkilemedi; tam hedef etiketleri bilinen sinirda kaldi.')
