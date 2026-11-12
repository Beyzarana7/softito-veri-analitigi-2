"""Bilinen fiyatlarda maliyet aralığı ve bağlayıcı işletme koşulları."""
import copy
import hashlib
import json
from itertools import product
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import pandas as pd

from firma_cizelgeleme import firma_verisini_oku,firma_cizelgele,maliyet_ve_ozet
from ortak_plan_karsilastirmasi import tarihleri_tasi,arsivden_plan
from fiyat_tahmini import elektrik_fiyatlarini_oku

DONEMLER=['2026-02-02','2026-05-04','2026-10-05']


def blok_baslangiclarini_hazirla(proje_dizini,cikti_dizini):
    """Yalnız başlangıç üretir; tam MILP çözüm uzayını bu bloklarla sınırlamaz."""
    proje=Path(proje_dizini);out=Path(cikti_dizini);out.mkdir(parents=True,exist_ok=True)
    v=firma_verisini_oku(proje);ts=pd.DatetimeIndex(v['tesis_takvimi']['tarih_saat'])
    ref=v['referans_plan'];kur=v['isletme_kurallari'].set_index('kaynak_id')
    gec=v['urun_gecisleri'].set_index(['kaynak_id','onceki_urun','sonraki_urun'])
    kaynaklar=list(kur.index);gunler=list(ts.normalize().unique())
    secenekler={}
    for r in kaynaklar:
        u=ref[(ref['kaynak_id']==r)&(ref['durum']=='uretim')]
        for d,gun in enumerate(gunler):
            bugun=u[u['tarih_saat'].dt.normalize()==gun]
            gruplar=[(p,g['is_emri_id'].iloc[0],len(g)) for p,g in bugun.groupby('urun_id',sort=False)]
            if r=='P01':
                ilk=[g for g in gruplar if g[0]=='UR01'];kalan=[g for g in gruplar if g[0]!='UR01']
                secenekler[r,d]=[ilk+kalan,ilk+kalan[::-1]]
            else:secenekler[r,d]=[gruplar,gruplar[::-1]]
    anahtar=list(secenekler)
    tak=v['kaynak_takvimi'].set_index(['kaynak_id','tarih_saat'])['kullanilabilir']
    stok=v['stok_alanlari'].set_index(['urun_id','stok_turu'])
    mod=v['kaynak_urun'].set_index(['kaynak_id','urun_id'])
    stok_key=list(stok.index);sidx={key:i for i,key in enumerate(stok_key)}
    cikis0=np.zeros((len(stok),len(ts)))
    sip=v['siparisler'].set_index('siparis_id')
    zaman_idx={t:i for i,t in enumerate(ts)}
    for y in v['referans_yuklemeler'].itertuples(index=False):
        s=sip.loc[y.siparis_id];cikis0[sidx[s['urun_id'],s['teslim_turu']],zaman_idx[y.tarih_saat]]+=y.miktar_ton
    seen=set();indeks=[];enerjiler=[];denenen=0
    with ZipFile(out/'blok_baslangiclari.zip','w',compression=ZIP_DEFLATED) as z:
        for kod in product([0,1],repeat=len(anahtar)):
            plan=ref[['kaynak_id','tarih_saat']].copy();plan[['durum','urun_id','is_emri_id']]=['kapali','','']
            uygun=True
            for r in kaynaklar:
                ayar=kur.loc[r,'baslangic_urun_ayari']
                for d,gun in enumerate(gunler):
                    sira=secenekler[r,d][kod[anahtar.index((r,d))]]
                    saat=0
                    for p,eid,sure in sira:
                        if ayar!=p:
                            l=int(gec.loc[(r,ayar,p),'hazirlik_saat'])
                            maske=(plan['kaynak_id']==r)&plan['tarih_saat'].between(gun+pd.Timedelta(hours=saat),gun+pd.Timedelta(hours=saat+l),inclusive='left')
                            plan.loc[maske,['durum','urun_id']]=['hazirlik',p];saat+=l;ayar=p
                        maske=(plan['kaynak_id']==r)&plan['tarih_saat'].between(gun+pd.Timedelta(hours=saat),gun+pd.Timedelta(hours=saat+sure),inclusive='left')
                        plan.loc[maske,['durum','urun_id','is_emri_id']]=['uretim',p,eid];saat+=sure
                    if d<2:
                        hedef=ref[(ref['kaynak_id']==r)&(ref['tarih_saat'].dt.normalize()==gunler[d+1])&(ref['durum']=='uretim')].iloc[0]['urun_id']
                        if ayar!=hedef:
                            l=int(gec.loc[(r,ayar,hedef),'hazirlik_saat'])
                            if saat>24-l:uygun=False;break
                            maske=(plan['kaynak_id']==r)&plan['tarih_saat'].between(gun+pd.Timedelta(hours=24-l),gun+pd.Timedelta(hours=24),inclusive='left')
                            plan.loc[maske,['durum','urun_id']]=['hazirlik',hedef];ayar=hedef
                if not uygun:break
            denenen+=1
            if not uygun:continue
            aktif=plan[plan['durum']!='kapali']
            if not tak.reindex(pd.MultiIndex.from_frame(aktif[['kaynak_id','tarih_saat']])).all():continue
            giris=np.zeros_like(cikis0);cikis=cikis0.copy()
            for a in plan[plan['durum']=='uretim'].itertuples(index=False):
                t=zaman_idx[a.tarih_saat];q=mod.loc[(a.kaynak_id,a.urun_id),'kapasite_ton_saat']
                if a.kaynak_id=='P01':
                    cikis[sidx[a.urun_id,'dokme'],t]+=q;giris[sidx[a.urun_id,'torbali'],t]+=q
                else:giris[sidx[a.urun_id,'dokme'],t]+=q
            son=stok['baslangic_ton'].to_numpy()[:,None]+np.cumsum(giris-cikis,axis=1)
            ilk=np.c_[stok['baslangic_ton'].to_numpy(),son[:,:-1]]
            if np.any(ilk-cikis<stok['minimum_ton'].to_numpy()[:,None]-1e-6) or np.any(son>stok['kapasite_ton'].to_numpy()[:,None]+1e-6):continue
            iz=hashlib.sha256(plan.to_csv(index=False).encode()).hexdigest()
            if iz in seen:continue
            try:_,_,s,o=maliyet_ve_ozet(v,plan,v['referans_yuklemeler'])
            except ValueError:continue
            seen.add(iz);pid=f'B{len(indeks):03d}'
            indeks.append([pid,float(s['elektrik_disi_gider_tl'].sum()),float(o['Enerji (kWh)'])])
            enerjiler.append(s['toplam_enerji_kwh'].to_numpy())
            z.writestr(pid+'/plan.csv','\ufeff'+plan.to_csv(index=False))
            z.writestr(pid+'/yuklemeler.csv','\ufeff'+v['referans_yuklemeler'].to_csv(index=False))
    if not indeks:raise ValueError('Geçerli blok başlangıcı üretilemedi.')
    pd.DataFrame(indeks,columns=['plan_id','elektrik_disi_gider_tl','enerji_kwh']).to_csv(out/'blok_indeksi.csv',index=False,encoding='utf-8-sig')
    np.save(out/'blok_enerji.npy',np.stack(enerjiler))
    (out/'blok_bilgisi.json').write_text(json.dumps(dict(denenen_sira=denenen,uygun_sira=len(indeks),
        yorum='Miktar, kaynak uygunluğu ve işletme kuralları değişmedi. Bunlar yalnız MILP başlangıcıdır.'),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Denenen:',denenen,'uygun başlangıç:',len(indeks),flush=True)


def zipten_oku(dosya,pid,karar):
    with ZipFile(dosya) as z:
        p=pd.read_csv(z.open(pid+'/plan.csv'),keep_default_na=False)
        y=pd.read_csv(z.open(pid+'/yuklemeler.csv'))
    fark=pd.Timestamp(karar)-pd.Timestamp('2025-10-06')
    for df in [p,y]:df['tarih_saat']=pd.to_datetime(df['tarih_saat'])+fark
    return p,y


def guclu_kiyas(proje_dizini,cikti_dizini,karar_zamani,sure=300,yontem='bilinen_fiyat',tani='temel'):
    proje=Path(proje_dizini);out=Path(cikti_dizini);karar=pd.Timestamp(karar_zamani)
    v=tarihleri_tasi(firma_verisini_oku(proje),karar)
    ham=elektrik_fiyatlarini_oku(proje);saatler=v['tesis_takvimi']['tarih_saat']
    v['fiyatlar']=pd.DataFrame({'tarih_saat':saatler,'PTF (TL/MWh)':ham.reindex(saatler).to_numpy()})
    if tani=='stok_alt_siniri':v['stok_alanlari']['minimum_ton']=0
    elif tani=='ic_is_emri_sureleri':
        v['is_emirleri']['tamamlanma_siniri']=saatler.max()+pd.Timedelta(hours=1)
    elif tani=='teslim_sureleri':
        v['siparisler']['teslim_zamani']=saatler.max()+pd.Timedelta(hours=1)
    elif tani=='tamamlanma_sureleri':
        v['is_emirleri']['tamamlanma_siniri']=saatler.max()+pd.Timedelta(hours=1)
        v['siparisler']['teslim_zamani']=saatler.max()+pd.Timedelta(hours=1)
    elif tani=='minimum_blok_sureleri':
        v['isletme_kurallari'][['minimum_uretim_saat','minimum_durus_saat']]=1
    elif tani!='temel':raise ValueError('Tanımsız teşhis.')
    gercek=copy.deepcopy(v)
    if yontem=='basit_tahmin':
        v['fiyatlar']['PTF (TL/MWh)']=np.tile(v['fiyatlar']['PTF (TL/MWh)'].iloc[:24].to_numpy(),3)
    elif yontem!='bilinen_fiyat':raise ValueError('Tanımsız yöntem.')
    adaylar=[('referans',v['referans_plan'],v['referans_yuklemeler'])]
    fiyat=v['fiyatlar']['PTF (TL/MWh)'].to_numpy()
    ortak=proje/'data/results/ortak_plan_deneyi'
    idx=pd.read_csv(ortak/'plan_indeksi.csv');e=np.load(ortak/'saatlik_enerji.npy')
    i=int(np.argmin(e@fiyat/1000+idx['elektrik_disi_gider_tl'].to_numpy()))
    p,y=arsivden_plan(ortak,idx.iloc[i]['plan_id'],karar,pd.Timestamp('2025-10-06'));adaylar.append(('ortak_havuz',p,y))
    idx=pd.read_csv(out/'blok_indeksi.csv');e=np.load(out/'blok_enerji.npy')
    i=int(np.argmin(e@fiyat/1000+idx['elektrik_disi_gider_tl'].to_numpy()))
    p,y=zipten_oku(out/'blok_baslangiclari.zip',idx.iloc[i]['plan_id'],karar);adaylar.append(('urun_sirasi',p,y))
    if karar==pd.Timestamp('2026-10-05'):
        for model in ['son_yayinlanan_gun','hgb_duzeltme_365']:
            folder=ortak/'milp_kontrolu'/model
            if (folder/'onerilen_plan.csv').is_file():
                p=pd.read_csv(folder/'onerilen_plan.csv',keep_default_na=False);y=pd.read_csv(folder/'onerilen_yuklemeler.csv')
                for df in [p,y]:df['tarih_saat']=pd.to_datetime(df['tarih_saat'])
                adaylar.append((model,p,y))
    temel_folder=out/(karar.strftime('%Y%m%d')+'_bilinen_fiyat_temel')
    if (temel_folder/'onerilen_plan.csv').is_file():
        p=pd.read_csv(temel_folder/'onerilen_plan.csv',keep_default_na=False)
        y=pd.read_csv(temel_folder/'onerilen_yuklemeler.csv')
        for df in [p,y]:df['tarih_saat']=pd.to_datetime(df['tarih_saat'])
        adaylar.append(('kayitli_tam_bilgi',p,y))
    puan=[float(maliyet_ve_ozet(v,p,y)[-1].iloc[-1]) for _,p,y in adaylar]
    sec=int(np.argmin(puan));ad,p,y=adaylar[sec]
    sonuc=firma_cizelgele(v,zaman_siniri=sure,goreli_acik=0.0001,yerel_iyilestirme=False,baslangic_cozumu=(p,y))
    p,y,h,f,s,o,b=sonuc
    hareket,faaliyet,saatlik,gercek_ozet=maliyet_ve_ozet(gercek,p,y)
    ref=maliyet_ve_ozet(gercek,gercek['referans_plan'],gercek['referans_yuklemeler'])[-1]
    folder=out/(karar.strftime('%Y%m%d')+'_'+yontem+'_'+tani);folder.mkdir(parents=True,exist_ok=True)
    for name,df in dict(onerilen_plan=p,onerilen_yuklemeler=y,stok_hareketleri=hareket,saatlik_maliyet=saatlik).items():df.to_csv(folder/(name+'.csv'),index=False,encoding='utf-8-sig')
    meta=dict(karar_zamani=str(karar),yontem=yontem,tani=tani,baslangic_kaynagi=ad,
        referans_gercek_maliyet_tl=float(ref.iloc[-1]),planlama_maliyeti_tl=float(o.iloc[-1]),
        gercek_maliyet_tl=float(gercek_ozet.iloc[-1]),cozum=b,
        kalan_mutlak_acik_tl=float(o.iloc[-1]-b['alt_sinir_tl']),
        kaydedilen_gercek_avantaj_tl=float(ref.iloc[-1]-gercek_ozet.iloc[-1]),
        temel_kurallar_degisti=tani!='temel',bagimsiz_kontrol=True)
    if tani!='temel':
        asil=tarihleri_tasi(firma_verisini_oku(proje),karar)
        asil['fiyatlar']=gercek['fiyatlar'].copy()
        try:
            maliyet_ve_ozet(asil,p,y)
            meta['asil_fabrika_kurallarina_uyuyor']=True
        except ValueError as hata:
            meta['asil_fabrika_kurallarina_uyuyor']=False
            meta['asil_kural_ihlali']=str(hata)
        meta['kontrol_kapsami']='Yalnız etiketlenmiş teşhis kopyası; uygulanabilir üretim önerisi olarak kullanılamaz.'
    (folder/'sonuc.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('komut',choices=['baslangic','kiyas']);a.add_argument('proje');a.add_argument('cikti')
    a.add_argument('--karar',default='2026-10-05');a.add_argument('--sure',type=float,default=300)
    a.add_argument('--yontem',default='bilinen_fiyat');a.add_argument('--tani',default='temel')
    p=a.parse_args()
    if p.komut=='baslangic':blok_baslangiclarini_hazirla(p.proje,p.cikti)
    else:guclu_kiyas(p.proje,p.cikti,p.karar,p.sure,p.yontem,p.tani)
