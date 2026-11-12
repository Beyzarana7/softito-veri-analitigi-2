"""Gelecek fiyatların eğitime sızmaması ve 48 saatlik tahmin ufku."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

proje=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from fiyat_tahmini import fiyat_tahmini_uret,ozellikleri_hazirla,hata_ozeti,BASIT_MODELLER,ML_MODELLER

if __name__=='__main__':
    index=pd.date_range('2024-01-01',periods=90*24,freq='h')
    s=pd.Series(1000+300*np.sin(2*np.pi*index.hour/24)+20*index.day_of_week,index=index,dtype=float)
    karar=pd.Timestamp('2024-03-16')
    son_bilinen=karar+pd.Timedelta(hours=23)
    zehirli=s.copy()
    zehirli.loc[zehirli.index>son_bilinen]=999999
    yalniz_bilinen=s.loc[:son_bilinen]
    for ad in BASIT_MODELLER+ML_MODELLER:
        p,b=fiyat_tahmini_uret(s,karar,ad)
        p2,b2=fiyat_tahmini_uret(zehirli,karar,ad)
        p3,b3=fiyat_tahmini_uret(yalniz_bilinen,karar,ad)
        np.testing.assert_allclose(p,p2,rtol=0,atol=1e-10)
        np.testing.assert_allclose(p,p3,rtol=0,atol=1e-10)
        assert len(p)==48 and p.index.min()==karar+pd.Timedelta(hours=24)
        assert p.index.max()==karar+pd.Timedelta(hours=71)
        assert np.isfinite(p).all()
        if ad in ML_MODELLER:
            assert pd.Timestamp(b['egitim_son_saat'])==son_bilinen
            assert pd.Timestamp(b['en_yeni_gecmis_ozellik_saati'])==son_bilinen
        if ad=='son_yayinlanan_gun':
            np.testing.assert_allclose(p.iloc[:24],p.iloc[24:])
            np.testing.assert_allclose(p.iloc[:24],s.loc[karar:son_bilinen])
    x=ozellikleri_hazirla(yalniz_bilinen,karar+pd.Timedelta(hours=71))
    assert x.iloc[-1]['ptf_gecikme_48']==s.loc[son_bilinen]
    try:fiyat_tahmini_uret(s,karar+pd.Timedelta(hours=1),BASIT_MODELLER[0])
    except ValueError:pass
    else:raise AssertionError('Gün başı dışındaki karar zamanı reddedilmedi.')
    try:fiyat_tahmini_uret(s.loc[:son_bilinen-pd.Timedelta(hours=1)],karar,BASIT_MODELLER[0])
    except ValueError:pass
    else:raise AssertionError('Eksik açıklanmış gün reddedilmedi.')
    ornek=pd.DataFrame(dict(bolum=['test']*3,model=['ornek']*3,
                           karar_zamani=[karar]*3,gercek=[0,100,200],tahmin=[10,90,210]))
    h=hata_ozeti(ornek).iloc[0]
    assert h['MAE_TL_MWh']==h['RMSE_TL_MWh']==10
    print('5 yöntemde gelecek fiyatları değiştirmek veya silmek tahmini değiştirmedi.')
    print('Bilgi kesimi, 48 saat ufuk, son gün tekrarı ve sıfır fiyat hata ölçümü geçti.')
