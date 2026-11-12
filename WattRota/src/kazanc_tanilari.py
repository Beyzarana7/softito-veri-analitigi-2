"""Kazanç aralıkları, plan tamponları ve fiyat hatasının karar farkına etkisi."""
import copy
import json
from pathlib import Path
import numpy as np
import pandas as pd

from firma_cizelgeleme import firma_verisini_oku,maliyet_ve_ozet
from ortak_plan_karsilastirmasi import tarihleri_tasi,arsivden_plan
from fiyat_tahmini import elektrik_fiyatlarini_oku
from kazanc_potansiyeli import DONEMLER


def plan_oku(folder):
    p=pd.read_csv(folder/'onerilen_plan.csv',keep_default_na=False)
    y=pd.read_csv(folder/'onerilen_yuklemeler.csv')
    for df in [p,y]:df['tarih_saat']=pd.to_datetime(df['tarih_saat'])
    return p,y


def plan_tamponlari(v,p,y):
    h,f,s,o=maliyet_ve_ozet(v,p,y)
    limit=v['stok_alanlari'][['urun_id','stok_turu','minimum_ton','kapasite_ton']]
    h=h.merge(limit,on=['urun_id','stok_turu'],validate='many_to_one')
    h['tuketim_sonrasi_tampon']=h['baslangic_ton']-h['cikis_ton']-h['minimum_ton']
    h['alt_sinirda']=h['tuketim_sonrasi_tampon'].abs()<=1e-5
    h['ust_sinirda']=(h['son_stok_ton']-h['kapasite_ton']).abs()<=1e-5
    stok=h.groupby(['urun_id','stok_turu']).agg(alt_sinir_saat=('alt_sinirda','sum'),ust_sinir_saat=('ust_sinirda','sum'),
        en_dusuk_tuketim_tamponu_ton=('tuketim_sonrasi_tampon','min')).reset_index()
    teslim=y.groupby('siparis_id',as_index=False)['tarih_saat'].max().rename(columns={'tarih_saat':'son_yukleme'})
    teslim=teslim.merge(v['siparisler'][['siparis_id','teslim_zamani']],on='siparis_id',validate='one_to_one')
    teslim['tamamlanma']=teslim['son_yukleme']+pd.Timedelta(hours=1)
    teslim['tampon_saat']=(teslim['teslim_zamani']-teslim['tamamlanma']).dt.total_seconds()/3600
    emir=f[f['durum']=='uretim'].groupby('is_emri_id',as_index=False)['tarih_saat'].max()
    emir=emir.merge(v['is_emirleri'][['is_emri_id','tamamlanma_siniri']],on='is_emri_id',validate='one_to_one')
    emir['tamamlanma']=emir['tarih_saat']+pd.Timedelta(hours=1)
    emir['tampon_saat']=(emir['tamamlanma_siniri']-emir['tamamlanma']).dt.total_seconds()/3600
    kur=v['isletme_kurallari'].set_index('kaynak_id');kayit=[]
    for r,df in p.groupby('kaynak_id',sort=False):
        df=df.sort_values('tarih_saat').copy()
        grup=(df['durum'].ne(df['durum'].shift())|df['urun_id'].ne(df['urun_id'].shift())).cumsum()
        min_uret=0;min_dur=0;haz=0
        for no,g in df.groupby(grup,sort=False):
            durum=g.iloc[0]['durum'];uzunluk=len(g)
            if durum=='uretim' and uzunluk==kur.loc[r,'minimum_uretim_saat']:min_uret+=1
            if durum=='kapali':
                if g.index[0]==df.index[0]:uzunluk+=kur.loc[r,'baslangic_durum_suresi_saat']
                if uzunluk==kur.loc[r,'minimum_durus_saat']:min_dur+=1
            if durum=='hazirlik':haz+=len(g)
        tak=v['kaynak_takvimi'].query('kaynak_id == @r')
        kayit.append([r,int(tak['kullanilabilir'].sum()),int(df['durum'].eq('uretim').sum()),haz,min_uret,min_dur])
    kaynak=pd.DataFrame(kayit,columns=['kaynak_id','uygun_saat','uretim_saat','hazirlik_saat','minimum_uretim_blogu_sayisi','minimum_durus_blogu_sayisi'])
    s=s.merge(v['tesis_takvimi'][['tarih_saat','guc_siniri_kw']],on='tarih_saat',validate='one_to_one')
    s['guc_tamponu_kw']=s['guc_siniri_kw']-s['toplam_enerji_kwh']
    return stok,teslim,emir,kaynak,s


def sonuclari_incele(proje_dizini,cikti_dizini):
    proje=Path(proje_dizini);out=Path(cikti_dizini)
    temel=firma_verisini_oku(proje);ham=elektrik_fiyatlarini_oku(proje)
    ortak=proje/'data/results/ortak_plan_deneyi'
    onceki=pd.read_csv(ortak/'haftalik_kararlar.csv',parse_dates=['karar_zamani'])
    tahmin=pd.read_csv(proje/'data/results/tahmin_gelistirme/saatlik_tahminler.csv',parse_dates=['karar_zamani','tarih_saat'])
    modeller=['son_yayinlanan_gun','hgb_duzeltme_365']
    sinirlar=[];fiyat_etkisi=[];ikili=[];temel_aralik=None
    for tarih in DONEMLER:
        karar=pd.Timestamp(tarih);prefix=karar.strftime('%Y%m%d')
        v=tarihleri_tasi(temel,karar);saatler=v['tesis_takvimi']['tarih_saat']
        gercek=ham.reindex(saatler).to_numpy();v['fiyatlar']=pd.DataFrame({'tarih_saat':saatler,'PTF (TL/MWh)':gercek})
        folder=out/(prefix+'_bilinen_fiyat_temel')
        meta=json.loads((folder/'sonuc.json').read_text(encoding='utf-8'))
        p,y=plan_oku(folder);o=maliyet_ve_ozet(v,p,y)[-1]
        adaylar=[('tam_bilgi_arama',p,y,float(o.iloc[-1]))];yontem_planlari={}
        for model in modeller:
            pid=onceki[(onceki['karar_zamani']==karar)&(onceki['model']==model)].iloc[0]['secilen_plan']
            p,y=arsivden_plan(ortak,pid,karar,pd.Timestamp('2025-10-06'))
            if karar==pd.Timestamp('2026-10-05'):
                k=out/(prefix+'_basit_tahmin_temel') if model=='son_yayinlanan_gun' else ortak/'milp_kontrolu'/model
                if (k/'onerilen_plan.csv').is_file():p,y=plan_oku(k)
            cost=float(maliyet_ve_ozet(v,p,y)[-1].iloc[-1]);adaylar.append((model,p,y,cost));yontem_planlari[model]=(p,y,cost)
        en=min(adaylar,key=lambda a:a[3]);ad,po,yo,ust=en
        alt=float(meta['cozum']['alt_sinir_tl'])
        if not np.isfinite(alt) or alt>ust+0.02:raise ValueError('Maliyet sınırları tutarsız.')
        referans=float(maliyet_ve_ozet(v,v['referans_plan'],v['referans_yuklemeler'])[-1].iloc[-1])
        satir=dict(karar_zamani=str(karar),referans_maliyet_tl=referans,bulunan_en_iyi_maliyet_tl=ust,
            matematiksel_alt_sinir_tl=alt,cozulmemis_aralik_tl=ust-alt,bulunan_avantaj_tl=referans-ust,
            olasi_azami_avantaj_ust_siniri_tl=referans-alt,en_iyi_plan_kaynagi=ad,
            arama_durumu=meta['cozum']['durum'],tum_fiyatlar_biliniyor=True)
        sinirlar.append(satir)
        for isim,df in zip(['stok_tamponlari','teslim_tamponlari','is_emri_tamponlari','kaynak_ozeti','guc_tamponlari'],plan_tamponlari(v,po,yo)):
            df.to_csv(folder/(isim+'.csv'),index=False,encoding='utf-8-sig')
        _,_,so,_=maliyet_ve_ozet(v,po,yo)
        for model,(p,y,cost) in yontem_planlari.items():
            _,_,sb,_=maliyet_ve_ozet(v,p,y)
            df=tahmin[(tahmin['karar_zamani']==karar)&(tahmin['model']==model)&(tahmin['bolum']=='geriye_donuk_2026')].sort_values('tarih_saat')
            if len(df)!=48:raise ValueError('Teşhis fiyat tahmini eksik.')
            f=np.r_[gercek[:24],df['tahmin'].to_numpy()]
            delta=sb['toplam_enerji_kwh'].to_numpy()-so['toplam_enerji_kwh'].to_numpy()
            diger=(sb['elektrik_disi_gider_tl']-so['elektrik_disi_gider_tl']).sum()
            gercek_fark=float(delta@gercek/1000+diger)
            tahmin_farki=float(delta@f/1000+diger)
            etki=delta*(f-gercek)/1000
            if not np.isclose(etki.sum(),tahmin_farki-gercek_fark,atol=0.02,rtol=0):raise ValueError('Fiyat hata ayrıştırması uyuşmuyor.')
            ikili.append([karar,model,cost,ust,gercek_fark,tahmin_farki,tahmin_farki>0.02])
            for i,t in enumerate(saatler):fiyat_etkisi.append([karar,model,t,gercek[i],f[i],delta[i],etki[i]])
        if karar==pd.Timestamp('2026-10-05'):temel_aralik=(alt,ust)
    pd.DataFrame(sinirlar).to_csv(out/'kazanc_araliklari.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(ikili,columns=['karar_zamani','model','yontem_gercek_maliyet_tl','en_iyi_uygun_maliyet_tl',
        'gercek_iyilestirme_tl','tahmine_gore_iyilestirme_tl','tahmin_de_iyilestirmeyi_tercih_ediyor']).to_csv(out/'ikili_plan_teshisi.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(fiyat_etkisi,columns=['karar_zamani','model','tarih_saat','gercek_fiyat','tahmin_fiyat',
        'yontem_eksi_iyi_plan_enerji_kwh','fiyat_hatasi_karar_farki_etkisi_tl']).to_csv(out/'saatlik_karar_hatasi.csv',index=False,encoding='utf-8-sig')
    teshis=[]
    for tani in ['stok_alt_siniri','ic_is_emri_sureleri','minimum_blok_sureleri']:
        k=out/('20261005_bilinen_fiyat_'+tani)
        if not (k/'sonuc.json').is_file():continue
        b=json.loads((k/'sonuc.json').read_text(encoding='utf-8'))
        lb,ub=temel_aralik;rlb=float(b['cozum']['alt_sinir_tl']);rub=min(float(b['gercek_maliyet_tl']),ub)
        if rlb>rub+0.02:raise ValueError('Teşhis sınırları tutarsız.')
        teshis.append([tani,b['gercek_maliyet_tl'],rlb,max(0,lb-rub),max(0,ub-rlb),b.get('asil_fabrika_kurallarina_uyuyor')])
    pd.DataFrame(teshis,columns=['tani','bulunan_teshis_maliyeti_tl','teshis_alt_siniri_tl','kural_maliyet_etkisi_alt_tl',
        'kural_maliyet_etkisi_ust_tl','asil_kurallara_uyuyor']).to_csv(out/'kural_teshis_araliklari.csv',index=False,encoding='utf-8-sig')
    print(pd.DataFrame(sinirlar).to_string(index=False),flush=True)


if __name__=='__main__':
    import sys
    sonuclari_incele(sys.argv[1],sys.argv[2])
