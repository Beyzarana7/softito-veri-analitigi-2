"""Tahmin hatasını aynı üretim kararının gerçekleşmiş maliyetinden ayırır."""
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import pandas as pd

from fiyat_tahmini import elektrik_fiyatlarini_oku
from firma_cizelgeleme import firma_verisini_oku, firma_cizelgele, maliyet_ve_ozet

KARAR_ZAMANI=pd.Timestamp('2026-10-05')
YONTEMLER=['tum_fiyatlar_biliniyor','basit_tahmin','ml_tahmin']


def karar_firmasini_hazirla(proje_dizini):
    """Aynı sentetik firmanın göreli takvimini sabit karar tarihine taşı."""
    v=firma_verisini_oku(proje_dizini)
    fark=KARAR_ZAMANI-v['tesis_takvimi']['tarih_saat'].min()
    for tablo in v.values():
        for alan in tablo.columns:
            if pd.api.types.is_datetime64_any_dtype(tablo[alan]):tablo[alan]+=fark
    fiyat=elektrik_fiyatlarini_oku(proje_dizini)
    saatler=v['tesis_takvimi']['tarih_saat']
    v['fiyatlar']=pd.DataFrame({'tarih_saat':saatler,'PTF (TL/MWh)':fiyat.reindex(saatler).to_numpy()})
    return v


def planlama_fiyatlarini_hazirla(gercek_fiyatlar,yontem,tahminler=None,model_adi=None):
    """İlk 24 saat ortak ve bilinen; kalan 48 saat yalnız seçilen tahmindir."""
    fiyat=gercek_fiyatlar.set_index('tarih_saat')['PTF (TL/MWh)']
    if len(fiyat)!=72 or fiyat.index.min()!=KARAR_ZAMANI:
        raise ValueError('Sabit karar örneği için kesintisiz 72 saat gerekir.')
    if not fiyat.index.equals(pd.date_range(KARAR_ZAMANI,periods=72,freq='h')):
        raise ValueError('Karar örneğinin saatleri sıralı ve kesintisiz olmalı.')
    kullanilan=fiyat.copy()
    kaynak=np.array(['aciklanmis']*24+['tahmin']*48,dtype=object)
    if yontem=='tum_fiyatlar_biliniyor':
        kaynak[:]='tum_fiyatlar_biliniyor'
    elif yontem in ['basit_tahmin','ml_tahmin']:
        hedef=pd.date_range(KARAR_ZAMANI+pd.Timedelta(hours=24),periods=48,freq='h')
        t=tahminler[(tahminler['bolum']=='ileri_donem_2026')&(tahminler['model']==model_adi)
                    &(tahminler['karar_zamani']==KARAR_ZAMANI)].set_index('tarih_saat')['tahmin']
        if t.index.has_duplicates or len(t)!=48:raise ValueError('Seçilen modelin karar tahminleri eksik/tekrarlı.')
        t=t.reindex(hedef)
        if not np.isfinite(t).all() or (t<0).any():raise ValueError('Planlama tahmini geçersiz.')
        kullanilan.loc[hedef]=t
    else:raise ValueError('Tanımsız karar yöntemi.')
    # Planlayıcıya gerçekleşmiş geleceği içermeyen bu tek fiyat sütunu verilir.
    girdi=pd.DataFrame({'tarih_saat':fiyat.index,'PTF (TL/MWh)':kullanilan.to_numpy()})
    rapor=pd.DataFrame({'tarih_saat':fiyat.index,'kullanilan_fiyat':kullanilan.to_numpy(),
                        'gercek_fiyat':fiyat.to_numpy(),'bilgi_turu':kaynak})
    return girdi,rapor


def karar_deneyini_calistir(proje_dizini,tahmin_dizini,yontem,cikti_dizini,sure=120):
    gercek=karar_firmasini_hazirla(proje_dizini)
    tahmin_dizini=Path(tahmin_dizini)
    model_adi='tum_fiyatlar_biliniyor';t=None
    if yontem!='tum_fiyatlar_biliniyor':
        secim=json.loads((tahmin_dizini/'model_secimi.json').read_text(encoding='utf-8'))
        model_adi=secim['basit_model' if yontem=='basit_tahmin' else 'ml_model']
        t=pd.read_csv(tahmin_dizini/'saatlik_tahminler.csv',parse_dates=['karar_zamani','tarih_saat'])
    fiyat,rapor=planlama_fiyatlarini_hazirla(gercek['fiyatlar'],yontem,t,model_adi)
    v=copy.deepcopy(gercek);v['fiyatlar']=fiyat
    plan,yuk,_,_,_,beklenen,cozum=firma_cizelgele(v,zaman_siniri=sure,goreli_acik=0.001)
    stok,faaliyet,saatlik,gerceklesen=maliyet_ve_ozet(gercek,plan,yuk)
    referans=maliyet_ve_ozet(gercek,gercek['referans_plan'],gercek['referans_yuklemeler'])[-1]
    # Planın sonradan fiyatlandırılması, karar verildikten sonra yapılır.
    assert np.isclose(beklenen.iloc[-1],cozum['maliyet_tl'],atol=0.02,rtol=0)
    folder=Path(cikti_dizini)/yontem;folder.mkdir(parents=True,exist_ok=True)
    for ad,tablo in dict(onerilen_plan=plan,onerilen_yuklemeler=yuk,stok_hareketleri=stok,
                         gerceklesen_saatlik_maliyet=saatlik,planlama_fiyatlari=rapor).items():
        tablo.to_csv(folder/(ad+'.csv'),index=False,encoding='utf-8-sig')
    k=pd.concat([referans.rename('Referans — gerçek fiyat'),beklenen.rename('Öneri — planlama fiyatı'),
                 gerceklesen.rename('Öneri — gerçek fiyat')],axis=1)
    k.index.name='olcut';k.to_csv(folder/'maliyet_karsilastirmasi.csv',encoding='utf-8-sig')
    with ZipFile(folder/'gercek_firma_girdileri.zip','w',compression=ZIP_DEFLATED) as z:
        for ad,tablo in gercek.items():z.writestr(ad+'.csv','\ufeff'+tablo.to_csv(index=False))
    h=rapor.iloc[24:]['kullanilan_fiyat']-rapor.iloc[24:]['gercek_fiyat']
    bilgi=dict(yontem=yontem,model=model_adi,karar_zamani=str(KARAR_ZAMANI),bilinen_saat=24,tahmin_saat=48,
               referans_gercek_maliyet_tl=float(referans.iloc[-1]),planlama_maliyeti_tl=float(beklenen.iloc[-1]),
               gerceklesen_maliyet_tl=float(gerceklesen.iloc[-1]),
               gerceklesen_avantaj_tl=float(referans.iloc[-1]-gerceklesen.iloc[-1]),
               gerceklesen_avantaj_yuzde=float(100*(referans.iloc[-1]-gerceklesen.iloc[-1])/referans.iloc[-1]),
               fiyat_MAE_TL_MWh=float(h.abs().mean()),fiyat_RMSE_TL_MWh=float(np.sqrt((h**2).mean())),
               degisen_uretim_kaynak_saat=int(gerceklesen['Değişen kaynak-saat']),
               bagimsiz_fiziksel_kontrol=True,cozum=cozum)
    kaynaklar=[Path(proje_dizini)/'src'/f'{ad}.py' for ad in ['firma_verisi','firma_cizelgeleme','fiyat_tahmini','tahminli_cizelgeleme']]
    bilgi['kaynak_sha256']={str(p.relative_to(proje_dizini)):hashlib.sha256(p.read_bytes()).hexdigest() for p in kaynaklar}
    if yontem!='tum_fiyatlar_biliniyor':
        bilgi['tahmin_sha256']=hashlib.sha256((tahmin_dizini/'saatlik_tahminler.csv').read_bytes()).hexdigest()
    (folder/'sonuc.json').write_text(json.dumps(bilgi,ensure_ascii=False,indent=2),encoding='utf-8')
    return bilgi


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('proje');p.add_argument('tahmin_dizini');p.add_argument('yontem',choices=YONTEMLER)
    p.add_argument('cikti');p.add_argument('--sure',type=float,default=120)
    a=p.parse_args()
    print(json.dumps(karar_deneyini_calistir(a.proje,a.tahmin_dizini,a.yontem,a.cikti,a.sure),ensure_ascii=True,indent=2))
