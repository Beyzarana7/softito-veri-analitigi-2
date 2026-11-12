"""Açıklanmış gün profilinden sapmayı öğrenen, ufku açık fiyat modelleri."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from threadpoolctl import threadpool_limits

from fiyat_tahmini import elektrik_fiyatlarini_oku, fiyat_tahmini_uret, hata_ozeti

ADAYLAR=['rf_duzeltme_180','hgb_duzeltme_180','hgb_duzeltme_365']


def karar_ornekleri(bilinen, son_hedef):
    """Her satırın kendi karar anı vardır; tüm fiyat girdileri o anda bilinir."""
    hedefler=pd.date_range(bilinen.index.min()+pd.Timedelta(days=28),son_hedef,freq='h')
    hedef=pd.DatetimeIndex(np.tile(hedefler.to_numpy(),2))
    ufuk=np.repeat([1,2],len(hedefler))
    karar=hedef.normalize()-pd.to_timedelta(ufuk,unit='D')
    saat=hedef.hour
    def al(z):return bilinen.reindex(pd.DatetimeIndex(z)).to_numpy(dtype=float)
    bugun_saat=karar+pd.to_timedelta(saat,unit='h')
    gunluk=bilinen.groupby(bilinen.index.normalize()).agg(['mean','min','max','std'])
    x=pd.DataFrame(index=pd.RangeIndex(len(hedef)))
    x['hedef_saat']=saat;x['hedef_gun']=hedef.day_of_week
    x['hedef_ay']=hedef.month;x['ufuk_gun']=ufuk
    x['aciklanmis_ayni_saat']=al(bugun_saat)
    x['onceki_gun_ayni_saat']=al(bugun_saat-pd.Timedelta(days=1))
    x['aciklanmis_gunun_onceki_haftasi']=al(bugun_saat-pd.Timedelta(days=7))
    for lag in [168,336,504,672]:x[f'hedef_gecmis_{lag}']=al(hedef-pd.Timedelta(hours=lag))
    x['hedef_dort_hafta_ortalama']=x[[f'hedef_gecmis_{lag}' for lag in [168,336,504,672]]].mean(axis=1,skipna=False)
    for col in ['mean','min','max','std']:
        x[f'aciklanmis_gun_{col}']=gunluk[col].reindex(karar).to_numpy()
    x['aciklanmis_gun_degisim']=x['aciklanmis_ayni_saat']-x['onceki_gun_ayni_saat']
    x['haftalik_profil_farki']=x['aciklanmis_ayni_saat']-x['aciklanmis_gunun_onceki_haftasi']
    meta=pd.DataFrame({'karar_zamani':karar,'tarih_saat':hedef,'gercek':al(hedef)})
    return x,meta


def gelistirilmis_tahmin(fiyat,karar_zamani,ad):
    if ad not in ADAYLAR:raise ValueError('Tanımsız geliştirme adayı.')
    karar=pd.Timestamp(karar_zamani)
    if karar!=karar.normalize():raise ValueError('Karar saati 00.00 olmalı.')
    bitis=karar+pd.Timedelta(hours=24)
    bilinen=fiyat.loc[fiyat.index<bitis].copy()
    if bilinen.empty or bilinen.index.max()!=bitis-pd.Timedelta(hours=1):raise ValueError('Açıklanmış ilk gün eksik.')
    if not bilinen.index.equals(pd.date_range(bilinen.index.min(),bilinen.index.max(),freq='h')):raise ValueError('Geçmiş saatler kesintisiz olmalı.')
    if not np.isfinite(bilinen).all() or (bilinen<0).any():raise ValueError('Geçersiz geçmiş fiyat.')
    x,m=karar_ornekleri(bilinen,karar+pd.Timedelta(hours=71))
    pencere=180 if ad.endswith('180') else 365
    egitim=(m['tarih_saat']<bitis)&(m['tarih_saat']>=bitis-pd.Timedelta(days=pencere))&x.notna().all(axis=1)&m['gercek'].notna()
    hedef=m['karar_zamani'].eq(karar)
    if egitim.sum()<1000 or hedef.sum()!=48 or x.loc[hedef].isna().any().any():raise ValueError('Eğitim veya hedef geçmişi yetersiz.')
    if ad.startswith('rf'):
        model=RandomForestRegressor(n_estimators=80,max_depth=10,min_samples_leaf=12,n_jobs=2,random_state=42)
    else:
        model=HistGradientBoostingRegressor(loss='absolute_error',learning_rate=0.05,max_iter=160,
            max_leaf_nodes=15,min_samples_leaf=30,l2_regularization=10,early_stopping=False,random_state=42)
    # Model ham fiyatı değil, bilinen gün profilinin ne kadar değişeceğini öğrenir.
    y=m.loc[egitim,'gercek']-x.loc[egitim,'aciklanmis_ayni_saat']
    with threadpool_limits(limits=2):
        model.fit(x.loc[egitim],y)
        p=x.loc[hedef,'aciklanmis_ayni_saat'].to_numpy()+model.predict(x.loc[hedef])
    p=np.maximum(p,0)
    sonuc=pd.Series(p,index=pd.DatetimeIndex(m.loc[hedef,'tarih_saat']),name='tahmin').sort_index()
    bilgi=dict(model=ad,karar_zamani=str(karar),bilinen_son_saat=str(bilinen.index.max()),
        egitim_son_hedef=str(m.loc[egitim,'tarih_saat'].max()),egitim_son_karar=str(m.loc[egitim,'karar_zamani'].max()),
        egitim_ornek_sayisi=int(egitim.sum()),egitim_penceresi_gun=pencere)
    return sonuc,bilgi


def saat_secimi_hatasi(tahminler):
    """Her hedef günde tahmine göre en ucuz altı saatin gerçek fiyat farkı."""
    kayit=[]
    for (bolum,model,karar,gun),df in tahminler.groupby(['bolum','model','karar_zamani',tahminler['tarih_saat'].dt.normalize()]):
        secim=df.sort_values(['tahmin','tarih_saat']).head(6)
        en_ucuz=df.nsmallest(6,'gercek')
        kayit.append([bolum,model,karar,gun,secim['gercek'].mean()-en_ucuz['gercek'].mean()])
    return pd.DataFrame(kayit,columns=['bolum','model','karar_zamani','hedef_gun','ucuz_saat_fiyat_farki_TL_MWh'])


def gelistirme_deneyi(proje_dizini,cikti_dizini):
    proje=Path(proje_dizini);out=Path(cikti_dizini);out.mkdir(parents=True,exist_ok=True)
    fiyat=elektrik_fiyatlarini_oku(proje)
    eski=pd.read_csv(proje/'data/results/fiyat_tahmini/saatlik_tahminler.csv',parse_dates=['karar_zamani','tarih_saat'])
    protokol=dict(adaylar=ADAYLAR,secim_donemi='2025-01-06 / 2025-06-30',
        onay_donemi='2025-07-07 / 2025-12-29',geriye_donuk_donem='2026-01-05 / 2026-11-02',
        secim_olcutu='MAE; yalnız ilk altı ay',donem_2026_yorumu='Daha önce incelenmiş dönem; yeni kör test değildir.')
    (out/'protokol.json').write_text(json.dumps(protokol,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[];izler=[]
    def ekle(bolum,kararlar,modeller):
        for karar in kararlar:
            for ad in modeller:
                p,b=gelistirilmis_tahmin(fiyat,karar,ad)
                izler.append(dict(bolum=bolum,**b))
                for t,v in p.items():rows.append([bolum,ad,karar,t,2 if t<karar+pd.Timedelta(hours=48) else 3,float(fiyat.loc[t]),float(v)])
            print(bolum,karar.date(),flush=True)
    kolonlar=['bolum','model','karar_zamani','tarih_saat','ufuk_gun','gercek','tahmin']
    ekle('gelistirme_2025_ilk_yari',pd.date_range('2025-01-06','2025-06-30',freq='W-MON'),ADAYLAR)
    ilk=hata_ozeti(pd.DataFrame(rows,columns=kolonlar))
    secilen=ilk.sort_values(['MAE_TL_MWh','model']).iloc[0]['model']
    (out/'secilen_model.json').write_text(json.dumps(dict(model=secilen,secim='2025 ilk yarı MAE'),ensure_ascii=False,indent=2),encoding='utf-8')
    ekle('onay_2025_ikinci_yari',pd.date_range('2025-07-07','2025-12-29',freq='W-MON'),[secilen])
    ekle('geriye_donuk_2026',pd.date_range('2026-01-05','2026-11-02',freq='W-MON'),[secilen])
    yeni=pd.DataFrame(rows,columns=kolonlar)
    eski=eski[eski['model'].isin(['son_yayinlanan_gun','random_forest_365gun'])].copy()
    eski['bolum']=np.where(eski['karar_zamani']<pd.Timestamp('2025-07-01'),'gelistirme_2025_ilk_yari',
                    np.where(eski['karar_zamani']<pd.Timestamp('2026-01-01'),'onay_2025_ikinci_yari','geriye_donuk_2026'))
    tablo=pd.concat([yeni,eski],ignore_index=True)
    tablo.to_csv(out/'saatlik_tahminler.csv',index=False,encoding='utf-8-sig')
    hata_ozeti(tablo).to_csv(out/'hata_ozeti.csv',index=False,encoding='utf-8-sig')
    saat_secimi_hatasi(tablo).to_csv(out/'saat_secimi_hatalari.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(izler).to_csv(out/'egitim_izleri.csv',index=False,encoding='utf-8-sig')
    hedef_hata=tablo.assign(mutlak_hata=lambda d:(d['tahmin']-d['gercek']).abs())
    hedef_hata.groupby(['bolum','model',hedef_hata['tarih_saat'].dt.hour])['mutlak_hata'].mean().to_csv(out/'saate_gore_hata.csv',encoding='utf-8-sig')
    kaynaklar=[proje/'src/fiyat_tahmini_gelistirme.py',proje/'src/fiyat_tahmini.py',proje/'data/results/fiyat_tahmini/saatlik_tahminler.csv']
    kaynaklar+=list((proje/'data/raw/epias').glob('Piyasa_Takas_Fiyati-*.csv'))
    (out/'kaynak_izleri.json').write_text(json.dumps({str(p.relative_to(proje)):hashlib.sha256(p.read_bytes()).hexdigest() for p in kaynaklar},indent=2),encoding='utf-8')
    print(hata_ozeti(tablo).to_string(index=False),flush=True)


if __name__=='__main__':
    import sys
    gelistirme_deneyi(sys.argv[1],sys.argv[2])
