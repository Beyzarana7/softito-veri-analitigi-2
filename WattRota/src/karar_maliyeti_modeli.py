"""Aynı geçerli planların maliyet farkını, bilinen fiyat bilgilerinden öğrenir."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from fiyat_tahmini import elektrik_fiyatlarini_oku
from fiyat_tahmini_gelistirme import karar_ornekleri

MODELLER=['ridge_100','ridge_1000','rf_maliyet']
KATKILAR=[0.0,0.5,1.0]


def maliyet_ornekleri(fiyat,enerji):
    x,m=karar_ornekleri(fiyat,fiyat.index.max()+pd.Timedelta(hours=48))
    saatlik=pd.concat([m[['karar_zamani','tarih_saat','gercek']],
        x[['aciklanmis_ayni_saat','hedef_gecmis_168','hedef_dort_hafta_ortalama']]],axis=1)
    X=[];Y=[];B=[];T=[]
    delta=(enerji-enerji[0])[...,24:]/1000
    for karar,d in saatlik.groupby('karar_zamani',sort=True):
        if len(d)!=48:continue
        d=d.sort_values('tarih_saat')
        bilinen=d[['aciklanmis_ayni_saat','hedef_gecmis_168','hedef_dort_hafta_ortalama']].to_numpy().T.ravel()
        if not np.isfinite(bilinen).all():continue
        # Tüm girdiler o kararın açıklanmış gün/önceki hafta profilleridir.
        cal=np.r_[np.eye(7)[karar.day_of_week],np.sin(2*np.pi*karar.month/12),np.cos(2*np.pi*karar.month/12)]
        X.append(np.r_[bilinen,cal]);T.append(karar)
        baz=d['aciklanmis_ayni_saat'].to_numpy();B.append(baz)
        Y.append(delta@(d['gercek'].to_numpy()-baz))
    return np.array(X),np.array(Y),np.array(B),pd.DatetimeIndex(T)


def maliyet_duzeltmesi(fiyat,enerji,karar,ad):
    karar=pd.Timestamp(karar);bitis=karar+pd.Timedelta(hours=24)
    bilinen=fiyat.loc[fiyat.index<bitis]
    if bilinen.index.max()!=bitis-pd.Timedelta(hours=1):raise ValueError('Bilinen gün eksik.')
    X,Y,B,T=maliyet_ornekleri(bilinen,enerji)
    egitim=(T+pd.Timedelta(hours=72)<=bitis)&(T>=bitis-pd.Timedelta(days=365))&np.isfinite(Y).all(axis=1)
    hedef=T==karar
    if egitim.sum()<90 or hedef.sum()!=1:raise ValueError('Maliyet modelinin eğitim geçmişi yetersiz.')
    if ad.startswith('ridge'):
        model=make_pipeline(StandardScaler(),Ridge(alpha=float(ad.split('_')[-1])))
    else:model=RandomForestRegressor(n_estimators=80,max_depth=8,min_samples_leaf=8,n_jobs=2,random_state=42)
    model.fit(X[egitim],Y[egitim])
    duzeltme=model.predict(X[hedef])[0]
    return duzeltme,B[hedef][0],dict(egitim_son_karar=str(T[egitim].max()),bilinen_son_saat=str(bilinen.index.max()))


def maliyet_modeli_deneyi(proje,tahmin_dizini,havuz_dizini):
    folder=Path(tahmin_dizini);havuz=Path(havuz_dizini)
    fiyat=elektrik_fiyatlarini_oku(proje);e=np.load(havuz/'saatlik_enerji.npy')
    idx=pd.read_csv(havuz/'plan_indeksi.csv');gider=idx['elektrik_disi_gider_tl'].to_numpy()
    rows=[]
    def hesapla(bolum,kararlar,adaylar,katkilar):
        for karar in kararlar:
            gercek=fiyat.reindex(pd.date_range(karar,periods=72,freq='h')).to_numpy()
            cost=e@gercek/1000+gider
            for ad in adaylar:
                duz,baz,iz=maliyet_duzeltmesi(fiyat,e,karar,ad)
                temel=e@np.r_[gercek[:24],baz]/1000+gider
                for w in katkilar:
                    sec=int(np.argmin(temel+w*duz))
                    rows.append([bolum,karar,ad,w,idx.iloc[sec]['plan_id'],cost[sec],cost[sec]-cost.min(),cost[0]-cost[sec],iz['egitim_son_karar']])
            print('Maliyet öğrenme',bolum,karar.date(),flush=True)
    hesapla('gelistirme_2025_ilk_yari',pd.date_range('2025-01-06','2025-06-30',freq='W-MON'),MODELLER,KATKILAR)
    cols=['bolum','karar_zamani','model','katki','secilen_plan','gercek_maliyet_tl','havuz_minimumuna_fark_tl','referansa_avantaj_tl','egitim_son_karar']
    ilk=pd.DataFrame(rows,columns=cols)
    secim=ilk.groupby(['model','katki'],as_index=False)['gercek_maliyet_tl'].mean().sort_values(['gercek_maliyet_tl','katki','model']).iloc[0]
    ad=str(secim['model']);w=float(secim['katki'])
    (folder/'maliyet_modeli_secimi.json').write_text(json.dumps(dict(model=ad,katki=w,secim_donemi='2025 Ocak–Haziran',
        amac='Aynı 19 plan içinde maliyet düzeltmesi; saatlik fiyat tahmini değildir.'),ensure_ascii=False,indent=2),encoding='utf-8')
    hesapla('onay_2025_ikinci_yari',pd.date_range('2025-07-07','2025-12-29',freq='W-MON'),[ad],[w])
    hesapla('geriye_donuk_2026',pd.date_range('2026-01-05','2026-11-02',freq='W-MON'),[ad],[w])
    d=pd.DataFrame(rows,columns=cols);d.to_csv(folder/'maliyet_modeli_kararlari.csv',index=False,encoding='utf-8-sig')
    o=d.groupby(['bolum','model','katki']).agg(karar_sayisi=('karar_zamani','nunique'),ortalama_maliyet_tl=('gercek_maliyet_tl','mean'),ortalama_havuz_farki_tl=('havuz_minimumuna_fark_tl','mean'))
    o.to_csv(folder/'maliyet_modeli_ozeti.csv',encoding='utf-8-sig');print(o.to_string(),flush=True)


if __name__=='__main__':
    import sys
    maliyet_modeli_deneyi(*sys.argv[1:4])
