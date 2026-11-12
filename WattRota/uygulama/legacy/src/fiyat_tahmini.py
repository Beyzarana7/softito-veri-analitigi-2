"""İlk günü açıklanmış 72 saatlik plan için kalan 48 saatin fiyat tahmini."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import sklearn

BASIT_MODELLER=['son_yayinlanan_gun','onceki_hafta','son_dort_hafta']
ML_MODELLER=['random_forest_180gun','random_forest_365gun']


def elektrik_fiyatlarini_oku(proje_dizini):
    tablolar=[]
    for dosya in sorted((Path(proje_dizini)/'data/raw/epias').glob('Piyasa_Takas_Fiyati-*.csv')):
        t=pd.read_csv(dosya,sep=';',decimal=',',thousands='.',dtype={'Tarih':str,'Saat':str})
        t['tarih_saat']=pd.to_datetime(t['Tarih']+' '+t['Saat'],format='%d.%m.%Y %H:%M')
        tablolar.append(t[['tarih_saat','PTF (TL/MWh)']])
    if not tablolar:raise ValueError('EPİAŞ CSV dosyası bulunamadı.')
    t=pd.concat(tablolar,ignore_index=True).sort_values('tarih_saat')
    s=t.set_index('tarih_saat')['PTF (TL/MWh)'].astype(float)
    if s.index.has_duplicates or not s.index.equals(pd.date_range(s.index.min(),s.index.max(),freq='h')):
        raise ValueError('Fiyat dizisinde eksik veya tekrarlanan saat var.')
    if not np.isfinite(s).all() or (s<0).any():raise ValueError('Sonlu ve negatif olmayan fiyat bekleniyor.')
    return s


def ozellikleri_hazirla(bilinen_fiyatlar, son_saat=None):
    """Her hedefte en yeni fiyat girdisi t−48'dir; t−1/t−24 kullanılmaz."""
    if son_saat is None:son_saat=bilinen_fiyatlar.index.max()
    saatler=pd.date_range(bilinen_fiyatlar.index.min(),son_saat,freq='h')
    fiyat=bilinen_fiyatlar.reindex(saatler)
    x=pd.DataFrame(index=saatler)
    x['saat']=saatler.hour
    x['haftanin_gunu']=saatler.day_of_week
    x['ay']=saatler.month
    x['yil']=saatler.year
    for lag in [48,72,168,336,504,672]:x[f'ptf_gecikme_{lag}']=fiyat.shift(lag)
    gecikmeli=fiyat.shift(48)
    x['son_24_ortalama']=gecikmeli.rolling(24,min_periods=24).mean()
    x['son_24_en_dusuk']=gecikmeli.rolling(24,min_periods=24).min()
    x['son_24_en_yuksek']=gecikmeli.rolling(24,min_periods=24).max()
    x['son_168_ortalama']=gecikmeli.rolling(168,min_periods=168).mean()
    return x


def fiyat_tahmini_uret(fiyatlar, karar_zamani, model_adi):
    """Gelecek fiyatları bilgi kümesine almadan 2. ve 3. gün için tahmin üret."""
    karar=pd.Timestamp(karar_zamani)
    if karar!=karar.normalize():raise ValueError('Karar zamanı Türkiye yerel saatiyle 00.00 olmalı.')
    if model_adi not in BASIT_MODELLER+ML_MODELLER:raise ValueError('Tanımsız tahmin yöntemi.')
    bilinen_bitis=karar+pd.Timedelta(hours=24)
    # Kesim, özellik üretiminden ve model eğitiminden önce yapılır.
    bilinen=fiyatlar.loc[fiyatlar.index<bilinen_bitis].copy()
    if bilinen.empty or bilinen.index.max()!=bilinen_bitis-pd.Timedelta(hours=1):
        raise ValueError('İlk günün açıklanmış 24 saatlik fiyatı eksik.')
    if not bilinen.index.equals(pd.date_range(bilinen.index.min(),bilinen.index.max(),freq='h')):
        raise ValueError('Bilinen fiyat geçmişi kesintisiz olmalı.')
    if not np.isfinite(bilinen).all() or (bilinen<0).any():raise ValueError('Bilinen fiyatlar geçersiz.')
    hedef=pd.date_range(bilinen_bitis,periods=48,freq='h')
    bilgi=dict(model=model_adi,karar_zamani=str(karar),bilinen_son_saat=str(bilinen.index.max()),
               tahmin_ilk_saat=str(hedef.min()),tahmin_son_saat=str(hedef.max()),
               tahmin_edilen_saat=48)
    if model_adi=='son_yayinlanan_gun':
        gun=bilinen.reindex(pd.date_range(karar,periods=24,freq='h')).to_numpy()
        tahmin=np.tile(gun,2)
    elif model_adi=='onceki_hafta':
        tahmin=bilinen.reindex(hedef-pd.Timedelta(hours=168)).to_numpy()
    elif model_adi=='son_dort_hafta':
        tahmin=np.mean([bilinen.reindex(hedef-pd.Timedelta(hours=lag)).to_numpy() for lag in [168,336,504,672]],axis=0)
    else:
        gun=180 if model_adi.endswith('180gun') else 365
        x=ozellikleri_hazirla(bilinen,hedef.max())
        egitim=x.loc[(x.index>=bilinen_bitis-pd.Timedelta(days=gun))&(x.index<bilinen_bitis)].dropna()
        if len(egitim)<1000:raise ValueError('Model eğitimi için yeterli saatlik geçmiş yok.')
        hedef_x=x.loc[hedef]
        if hedef_x.isna().any().any():raise ValueError('Tahmin için gereken geçmiş fiyat eksik.')
        model=RandomForestRegressor(n_estimators=80,max_depth=10,min_samples_leaf=8,
                                    max_features=1.0,n_jobs=2,random_state=42)
        model.fit(egitim,bilinen.loc[egitim.index])
        tahmin=model.predict(hedef_x)
        bilgi.update(egitim_ilk_saat=str(egitim.index.min()),egitim_son_saat=str(egitim.index.max()),
                     egitim_saat_sayisi=len(egitim),egitim_penceresi_gun=gun,
                     en_yeni_gecmis_ozellik_saati=str(hedef.max()-pd.Timedelta(hours=48)))
    if not np.isfinite(tahmin).all() or np.any(tahmin<0):raise ValueError('Tahmin üretilemedi veya geçmiş yetersiz.')
    return pd.Series(tahmin,index=hedef,name='tahmin'),bilgi


def hata_ozeti(tahminler):
    satirlar=[]
    for (bolum,model),df in tahminler.groupby(['bolum','model'],sort=False):
        hata=df['tahmin']-df['gercek']
        satirlar.append([bolum,model,len(df),len(df['karar_zamani'].unique()),
                        hata.abs().mean(),np.sqrt((hata**2).mean()),hata.mean()])
    return pd.DataFrame(satirlar,columns=['bolum','model','saat_sayisi','karar_sayisi',
                                        'MAE_TL_MWh','RMSE_TL_MWh','ortalama_isaretli_hata'])


def tahmin_deneyini_calistir(proje_dizini,cikti_dizini):
    """2025 ile yöntem seç; seçim sabitlendikten sonra 2026'yı değerlendir."""
    bas=time.perf_counter()
    fiyat=elektrik_fiyatlarini_oku(proje_dizini)
    folder=Path(cikti_dizini);folder.mkdir(parents=True,exist_ok=True)
    satirlar=[];egitim_kayitlari=[]
    def donemi_calistir(bolum,kararlar,modeller):
        for karar in kararlar:
            for ad in modeller:
                pred,bilgi=fiyat_tahmini_uret(fiyat,karar,ad)
                gercek=fiyat.reindex(pred.index)
                if gercek.isna().any():raise ValueError('Değerlendirme hedefi kaynakta yok.')
                for saat,p,g in zip(pred.index,pred,gercek):
                    satirlar.append([bolum,ad,karar,saat,2 if saat<karar+pd.Timedelta(hours=48) else 3,float(g),float(p)])
                egitim_kayitlari.append(dict(bolum=bolum,**bilgi))
            print(bolum,karar.date(),'tamamlandı',flush=True)
    val_kararlar=pd.date_range('2025-01-06','2025-12-29',freq='W-MON')
    ileri_kararlar=pd.date_range('2026-01-05','2026-11-02',freq='W-MON')
    kolonlar=['bolum','model','karar_zamani','tarih_saat','ufuk_gun','gercek','tahmin']
    donemi_calistir('dogrulama_2025',val_kararlar,BASIT_MODELLER+ML_MODELLER)
    val=pd.DataFrame(satirlar,columns=kolonlar)
    val_ozet=hata_ozeti(val)
    en_iyi_basit=val_ozet[val_ozet['model'].isin(BASIT_MODELLER)].sort_values(['MAE_TL_MWh','model']).iloc[0]['model']
    en_iyi_ml=val_ozet[val_ozet['model'].isin(ML_MODELLER)].sort_values(['MAE_TL_MWh','model']).iloc[0]['model']
    secim=dict(basit_model=en_iyi_basit,ml_model=en_iyi_ml,secim_olcutu='2025 doğrulama MAE',
               dogrulama_karar_sayisi=len(val_kararlar),ileri_donem_karar_sayisi=len(ileri_kararlar),
               sklearn_surumu=sklearn.__version__,random_state=42,
               n_estimators=80,max_depth=10,min_samples_leaf=8)
    # 2026 hataları henüz hesaplanmadan seçim dosyası yazılır.
    (folder/'model_secimi.json').write_text(json.dumps(secim,ensure_ascii=False,indent=2),encoding='utf-8')
    donemi_calistir('ileri_donem_2026',ileri_kararlar,[en_iyi_basit,en_iyi_ml])
    tablo=pd.DataFrame(satirlar,columns=kolonlar)
    tablo.to_csv(folder/'saatlik_tahminler.csv',index=False,encoding='utf-8-sig')
    ozet=hata_ozeti(tablo)
    ozet.to_csv(folder/'hata_ozeti.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(egitim_kayitlari).to_csv(folder/'egitim_izleri.csv',index=False,encoding='utf-8-sig')
    gun_ozeti=[]
    for (bolum,ad,gun),df in tablo.groupby(['bolum','model','ufuk_gun']):
        h=df['tahmin']-df['gercek']
        gun_ozeti.append([bolum,ad,gun,len(df),h.abs().mean(),np.sqrt((h**2).mean())])
    pd.DataFrame(gun_ozeti,columns=['bolum','model','ufuk_gun','saat_sayisi','MAE_TL_MWh','RMSE_TL_MWh']).to_csv(folder/'ufuk_hatalari.csv',index=False,encoding='utf-8-sig')
    kaynaklar=list((Path(proje_dizini)/'data/raw/epias').glob('Piyasa_Takas_Fiyati-*.csv'))+[Path(proje_dizini)/'src/fiyat_tahmini.py']
    meta=dict(toplam_sure_saniye=time.perf_counter()-bas,ilk_fiyat=str(fiyat.index.min()),son_fiyat=str(fiyat.index.max()),
              fiyat_saat_sayisi=len(fiyat),bilinen_saat=24,tahmin_saat=48,karar_saati='00:00 Europe/Istanbul',
              dosya_sha256={str(p.relative_to(proje_dizini)):hashlib.sha256(p.read_bytes()).hexdigest() for p in kaynaklar})
    (folder/'deney_bilgisi.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(ozet.to_string(index=False),flush=True)
    return ozet


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('proje');p.add_argument('cikti')
    args=p.parse_args()
    tahmin_deneyini_calistir(args.proje,args.cikti)
