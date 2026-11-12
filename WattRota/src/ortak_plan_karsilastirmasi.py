"""Tahmin etkisini MILP arama süresinden ayıran sabit uygulanabilir plan deneyi."""
import copy
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import pandas as pd

from firma_cizelgeleme import firma_verisini_oku,maliyet_ve_ozet,firma_cizelgele
from fiyat_tahmini import elektrik_fiyatlarini_oku


def planlari_oku(klasor):
    p=pd.read_csv(klasor/'onerilen_plan.csv',keep_default_na=False)
    y=pd.read_csv(klasor/'onerilen_yuklemeler.csv')
    for df in [p,y]:df['tarih_saat']=pd.to_datetime(df['tarih_saat'])
    return p,y


def tarihleri_tasi(v,karar):
    yeni=copy.deepcopy(v)
    fark=pd.Timestamp(karar)-v['tesis_takvimi']['tarih_saat'].min()
    for df in yeni.values():
        for col in df:
            if pd.api.types.is_datetime64_any_dtype(df[col]):df[col]+=fark
    return yeni


def ortak_planlari_hazirla(proje_dizini,cikti_dizini):
    proje=Path(proje_dizini);out=Path(cikti_dizini);out.mkdir(parents=True,exist_ok=True)
    v=firma_verisini_oku(proje);bas=v['tesis_takvimi']['tarih_saat'].min()
    kaynaklar=[('referans',v['referans_plan'],v['referans_yuklemeler'])]
    kaynak_dosyalar=[]
    for ad,folder in [('ekim_2025',proje/'data/results/firma_01_cizelgeleme'),
        ('kis_2025',proje/'data/results/firma_01_senaryolar/kis_fiyatlari'),
        ('ilkbahar_2025',proje/'data/results/firma_01_senaryolar/ilkbahar_fiyatlari'),
        ('yaz_2025',proje/'data/results/firma_01_senaryolar/yaz_fiyatlari')]:
        p,y=planlari_oku(folder)
        if not p['tarih_saat'].dt.year.eq(2025).all():raise ValueError('Plan havuzu yalnız 2025 kaynaklarıyla kurulmalı.')
        fark=bas-p['tarih_saat'].min()
        p['tarih_saat']+=fark;y['tarih_saat']+=fark
        maliyet_ve_ozet(v,p,y)
        kaynaklar.append((ad,p,y))
        kaynak_dosyalar += [folder/'onerilen_plan.csv',folder/'onerilen_yuklemeler.csv']
    kayitlar=[];enerjiler=[];gorulen=set();reddedilen=0
    with ZipFile(out/'ortak_planlar.zip','w',compression=ZIP_DEFLATED) as z:
        for diger,p,_ in kaynaklar:
            for h02,ph,_ in kaynaklar:
                plan=pd.concat([p[p['kaynak_id']!='H02'],ph[ph['kaynak_id']=='H02']],ignore_index=True).sort_values(['kaynak_id','tarih_saat']).reset_index(drop=True)
                for yuk_ad,_,y in kaynaklar:
                    yuk=y.sort_values(['tarih_saat','kaynak_id','siparis_id']).reset_index(drop=True)
                    fiziksel=plan.drop(columns='is_emri_id').to_csv(index=False)+yuk.to_csv(index=False)
                    iz=hashlib.sha256(fiziksel.encode()).hexdigest()
                    if iz in gorulen:continue
                    try:_,_,s,o=maliyet_ve_ozet(v,plan,yuk)
                    except ValueError:
                        reddedilen+=1;continue
                    gorulen.add(iz);pid=f'P{len(kayitlar):03d}'
                    kayitlar.append([pid,diger,h02,yuk_ad,float(s['elektrik_disi_gider_tl'].sum()),float(o['Enerji (kWh)'])])
                    enerjiler.append(s['toplam_enerji_kwh'].to_numpy())
                    z.writestr(pid+'/plan.csv','\ufeff'+plan.to_csv(index=False))
                    z.writestr(pid+'/yuklemeler.csv','\ufeff'+yuk.to_csv(index=False))
    indeks=pd.DataFrame(kayitlar,columns=['plan_id','diger_kaynaklar','H02_kaynagi','yukleme_kaynagi','elektrik_disi_gider_tl','enerji_kwh'])
    if len(indeks)<2:raise ValueError('Karşılaştırma için yeterli farklı uygun plan yok.')
    indeks.to_csv(out/'plan_indeksi.csv',index=False,encoding='utf-8-sig')
    np.save(out/'saatlik_enerji.npy',np.stack(enerjiler))
    pd.DataFrame(np.stack(enerjiler),index=indeks['plan_id'],columns=[f'saat_{i}' for i in range(72)]).to_csv(out/'saatlik_enerji.csv',encoding='utf-8-sig')
    (out/'havuz_bilgisi.json').write_text(json.dumps(dict(uygun_plan_sayisi=len(indeks),reddedilen_bilesim_sayisi=reddedilen,
        kaynak_yili=2025,amac='Aynı geçerli planlar arasında tam tarama; tüm fabrika çizelgelerinin optimumu değildir.',
        kaynak_sha256={str(p.relative_to(proje)):hashlib.sha256(p.read_bytes()).hexdigest() for p in kaynak_dosyalar}),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Ortak uygun plan sayısı:',len(indeks),flush=True)


def arsivden_plan(out,pid,karar,temel_baslangic):
    with ZipFile(Path(out)/'ortak_planlar.zip') as z:
        p=pd.read_csv(io.BytesIO(z.read(pid+'/plan.csv')),keep_default_na=False)
        y=pd.read_csv(io.BytesIO(z.read(pid+'/yuklemeler.csv')))
    fark=pd.Timestamp(karar)-temel_baslangic
    for df in [p,y]:df['tarih_saat']=pd.to_datetime(df['tarih_saat'])+fark
    return p,y


def ortak_plan_deneyi(proje_dizini,tahmin_dizini,cikti_dizini):
    proje=Path(proje_dizini);out=Path(cikti_dizini);tahmin_out=Path(tahmin_dizini)
    v=firma_verisini_oku(proje);fiyat=elektrik_fiyatlarini_oku(proje)
    t=pd.read_csv(tahmin_out/'saatlik_tahminler.csv',parse_dates=['karar_zamani','tarih_saat'])
    secim=json.loads((tahmin_out/'secilen_model.json').read_text(encoding='utf-8'))['model']
    t=t[t['bolum']=='geriye_donuk_2026']
    idx=pd.read_csv(out/'plan_indeksi.csv');e=np.load(out/'saatlik_enerji.npy')
    gider=idx['elektrik_disi_gider_tl'].to_numpy()
    satirlar=[]
    for karar,df in t.groupby('karar_zamani',sort=True):
        saatler=pd.date_range(karar,periods=72,freq='h');gercek=fiyat.reindex(saatler).to_numpy()
        gercek_maliyet=e@gercek/1000+gider
        en_iyi=int(np.argmin(gercek_maliyet))
        yeni=tarihleri_tasi(v,karar)
        yeni['fiyatlar']=pd.DataFrame({'tarih_saat':saatler,'PTF (TL/MWh)':gercek})
        for model in ['son_yayinlanan_gun','random_forest_365gun',secim]:
            tahmin=df[df['model']==model].sort_values('tarih_saat')
            if len(tahmin)!=48 or not pd.DatetimeIndex(tahmin['tarih_saat']).equals(saatler[24:]):raise ValueError('Ortak plan deneyi tahminleri eksik.')
            plan_fiyati=np.r_[gercek[:24],tahmin['tahmin'].to_numpy()]
            beklenen=e@plan_fiyati/1000+gider
            secilen=int(np.argmin(beklenen));pid=idx.iloc[secilen]['plan_id']
            p,y=arsivden_plan(out,pid,karar,v['tesis_takvimi']['tarih_saat'].min())
            o=maliyet_ve_ozet(yeni,p,y)[-1]
            if not np.isclose(o.iloc[-1],gercek_maliyet[secilen],atol=0.02,rtol=0):raise ValueError('Ortak plan maliyeti bağımsız hesapla eşleşmiyor.')
            fark=gercek_maliyet[secilen]-gercek_maliyet[en_iyi]
            if fark < -0.02:raise ValueError('Havuz minimumundan daha düşük maliyet hesaplandı.')
            satirlar.append([karar,model,pid,float(beklenen[secilen]),float(gercek_maliyet[secilen]),
                idx.iloc[en_iyi]['plan_id'],float(gercek_maliyet[en_iyi]),float(fark),
                float(gercek_maliyet[0]-gercek_maliyet[secilen]),True])
        print('Ortak plan kontrolü',karar.date(),flush=True)
    sonuc=pd.DataFrame(satirlar,columns=['karar_zamani','model','secilen_plan','beklenen_maliyet_tl','gercek_maliyet_tl',
        'havuz_gercek_minimum_plan','havuz_gercek_minimum_maliyet_tl','havuz_minimumuna_fark_tl','referansa_avantaj_tl','bagimsiz_kontrol'])
    sonuc.to_csv(out/'haftalik_kararlar.csv',index=False,encoding='utf-8-sig')
    ozet=sonuc.groupby('model').agg(karar_sayisi=('karar_zamani','nunique'),ortalama_maliyet_tl=('gercek_maliyet_tl','mean'),
        ortalama_havuz_farki_tl=('havuz_minimumuna_fark_tl','mean'),ortalama_avantaj_tl=('referansa_avantaj_tl','mean'))
    ozet.to_csv(out/'ortak_plan_ozeti.csv',encoding='utf-8-sig')
    print(ozet.to_string(),flush=True)


def milp_kontrolu(proje_dizini,tahmin_dizini,havuz_dizini,model,sure=120):
    proje=Path(proje_dizini);havuz=Path(havuz_dizini);karar=pd.Timestamp('2026-10-05')
    v=tarihleri_tasi(firma_verisini_oku(proje),karar)
    ham=elektrik_fiyatlarini_oku(proje);saatler=v['tesis_takvimi']['tarih_saat'];gercek=ham.reindex(saatler).to_numpy()
    v['fiyatlar']=pd.DataFrame({'tarih_saat':saatler,'PTF (TL/MWh)':gercek})
    t=pd.read_csv(Path(tahmin_dizini)/'saatlik_tahminler.csv',parse_dates=['karar_zamani','tarih_saat'])
    t=t[(t['karar_zamani']==karar)&(t['model']==model)&(t['bolum']=='geriye_donuk_2026')].sort_values('tarih_saat')
    if len(t)!=48:raise ValueError('MILP kontrol tahmini eksik.')
    kararlar=pd.read_csv(havuz/'haftalik_kararlar.csv',parse_dates=['karar_zamani'])
    pid=kararlar[(kararlar['karar_zamani']==karar)&(kararlar['model']==model)].iloc[0]['secilen_plan']
    p,y=arsivden_plan(havuz,pid,karar,pd.Timestamp('2025-10-06'))
    plan_firmasi=copy.deepcopy(v);plan_firmasi['fiyatlar']['PTF (TL/MWh)']=np.r_[gercek[:24],t['tahmin'].to_numpy()]
    # Aynı ortak havuzdan seçilen geçerli başlangıç, her yönteme aynı süre bütçesi.
    sonuc=firma_cizelgele(plan_firmasi,zaman_siniri=sure,goreli_acik=0.001,baslangic_cozumu=(p,y))
    o=maliyet_ve_ozet(v,sonuc[0],sonuc[1])[-1]
    folder=havuz/'milp_kontrolu'/model;folder.mkdir(parents=True,exist_ok=True)
    sonuc[0].to_csv(folder/'onerilen_plan.csv',index=False,encoding='utf-8-sig')
    sonuc[1].to_csv(folder/'onerilen_yuklemeler.csv',index=False,encoding='utf-8-sig')
    b=dict(model=model,karar_zamani=str(karar),baslangic_plan=pid,gercek_maliyet_tl=float(o.iloc[-1]),cozum=sonuc[-1],bagimsiz_kontrol=True)
    (folder/'sonuc.json').write_text(json.dumps(b,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(b,ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':
    import sys
    komut,proje,tahmin,out=sys.argv[1:5]
    if komut=='havuz':ortak_planlari_hazirla(proje,out)
    elif komut=='karsilastir':ortak_plan_deneyi(proje,tahmin,out)
    elif komut=='milp':milp_kontrolu(proje,tahmin,out,sys.argv[5])
    else:raise ValueError('Tanımsız deney komutu.')
