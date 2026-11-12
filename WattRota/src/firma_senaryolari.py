"""Aynı çimento firmasının fiyat, talep ve değişiklik gideri senaryoları."""
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import pandas as pd

from firma_cizelgeleme import firma_verisini_oku, firma_cizelgele, maliyet_ve_ozet


def talebi_artir(v, siparis_id, ek_ton):
    """Siparişi, bağlı iş emirlerini ve tahsisleri aynı miktarla güncelle."""
    v['siparisler'].loc[v['siparisler']['siparis_id']==siparis_id,'miktar_ton']+=ek_ton
    baglar=v['is_emri_siparis_baglantisi']
    maske=baglar['siparis_id']==siparis_id
    baglar.loc[maske,'tahsis_ton']+=ek_ton
    emir_miktari=baglar.groupby('is_emri_id')['tahsis_ton'].sum()
    v['is_emirleri']['miktar_ton']=v['is_emirleri']['is_emri_id'].map(emir_miktari)


def yukleme_kapasitesini_kontrol_et(v):
    """Aynı gün teslim edilecek işlerin zorunlu yükleme saatleri alt sınırı.

    Her kaynakta saatte tek sipariş işlenir. Bu gerekli koşulun geçilmesi
    uygulanabilirliği kanıtlamaz; aşılması ise kesin kapasite çelişkisidir.
    """
    satirlar=[]
    kaynak_tur=v['kaynaklar'].set_index('kaynak_id')['kaynak_turu']
    tak=v['kaynak_takvimi']
    for (gun,tip),sip in v['siparisler'].groupby([v['siparisler']['teslim_zamani'].dt.normalize(),'teslim_turu']):
        tur='dokme_yukleme' if tip=='dokme' else 'torbali_yukleme'
        kaynaklar=kaynak_tur[kaynak_tur==tur].index
        # Bu firmanın her yükleme türü için tek kaynağı vardır.
        if len(kaynaklar)!=1:
            raise ValueError('Kapasite ön kontrolü tek yükleme kaynağı varsayar.')
        r=kaynaklar[0]
        kapasite=v['kaynak_urun'].query('kaynak_id == @r').set_index('urun_id')['kapasite_ton_saat']
        gerekli=np.ceil(sip['miktar_ton']/sip['urun_id'].map(kapasite)).sum()
        pencere=(tak['kaynak_id']==r)&tak['kullanilabilir']&(tak['tarih_saat']>=sip['en_erken_yukleme'].min())&(tak['tarih_saat']+pd.Timedelta(hours=1)<=sip['teslim_zamani'].max())
        # Başka günden taşan pencereler için bu günlük alt sınır kullanılmaz.
        if not sip['en_erken_yukleme'].dt.normalize().eq(gun).all():
            raise ValueError('Bu ön kontrol aynı gün içindeki yükleme pencereleri içindir.')
        uygun=int(pencere.sum())
        satirlar.append([gun,r,int(gerekli),uygun,int(gerekli)>uygun])
    return pd.DataFrame(satirlar,columns=['gun','kaynak_id','zorunlu_saat_alt_siniri','uygun_saat','kapasite_celiskisi'])


def senaryolari_hazirla(proje_dizini):
    """Tarihler sonuçlara bakılmadan, aynı hafta günü olacak şekilde seçilmiştir."""
    proje=Path(proje_dizini)
    temel=firma_verisini_oku(proje)
    fiyat=pd.read_csv(proje/'data/raw/epias/Piyasa_Takas_Fiyati-01012025-31122025.csv',
                      sep=';',decimal=',',thousands='.',dtype={'Tarih':str,'Saat':str})
    fiyat['tarih_saat']=pd.to_datetime(fiyat['Tarih']+' '+fiyat['Saat'],format='%d.%m.%Y %H:%M')
    cases={}
    for sid,ad,bas in [('kis_fiyatlari','Kış fiyatları','2025-01-06'),
                       ('ilkbahar_fiyatlari','İlkbahar fiyatları','2025-04-07'),
                       ('yaz_fiyatlari','Yaz fiyatları','2025-07-07')]:
        v=copy.deepcopy(temel)
        fark=pd.Timestamp(bas)-temel['tesis_takvimi']['tarih_saat'].min()
        for df in v.values():
            for alan in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[alan]):df[alan]+=fark
        saatler=v['tesis_takvimi']['tarih_saat']
        v['fiyatlar']=fiyat.loc[fiyat['tarih_saat'].isin(saatler),['tarih_saat','PTF (TL/MWh)']].reset_index(drop=True)
        cases[sid]=dict(ad=ad,veriler=v,degisiklik_gideri=0.0,
                        aciklama='Aynı talep ve göreli işletme takvimi; farklı gerçek 72 saatlik EPİAŞ fiyatı.')

    v=copy.deepcopy(temel)
    talebi_artir(v,'SP2_UR02_dokme',160)
    gun=pd.Timestamp('2025-10-07')
    plan=v['referans_plan']
    maske=(plan['kaynak_id']=='H02')&plan['tarih_saat'].isin([gun+pd.Timedelta(hours=h) for h in [19,20]])
    plan.loc[maske,['durum','urun_id','is_emri_id']]=['uretim','UR02','IE2_UR02_ogutme']
    yuk=v['referans_yuklemeler']
    maske=yuk['siparis_id']=='SP2_UR01_dokme'
    yuk.loc[maske,'tarih_saat']=yuk.loc[maske,'tarih_saat'].map(lambda z:gun+pd.Timedelta(hours={11:13,13:14,15:15,17:17}[z.hour]))
    v['referans_yuklemeler']=pd.concat([yuk,pd.DataFrame([['SP2_UR02_dokme','Y01',gun+pd.Timedelta(hours=11),160]],columns=yuk.columns)],ignore_index=True)
    cases['yogun_dokme_talep']=dict(ad='Yoğun dökme talep',veriler=v,degisiklik_gideri=0.0,
        aciklama='İkinci gün UR02 dökme siparişi 400→560 ton; toplam talep +%2,38. Y01 için en az 9/9 saat gerekir. Referans aynı yeni talebe göre fiyat kullanılmadan düzenlendi.')

    cases['yuksek_degisim_gideri']=dict(ad='Yüksek üretim planı değişikliği gideri',veriler=copy.deepcopy(temel),degisiklik_gideri=10000.0,
        aciklama='Değişen üretim/paketleme kaynak-saati başına 10.000 TL: yüksek gider davranış testi; gerçek fabrika maliyeti değildir. Yükleme saati değişimi bu cezaya dahil değildir.')
    v=copy.deepcopy(temel)
    talebi_artir(v,'SP2_UR02_torbali',400)
    cases['kapasite_asimi']=dict(ad='Yükleme kapasitesini aşan talep',veriler=v,degisiklik_gideri=0.0,
        aciklama='İkinci gün UR02 torbalı siparişi 400→800 ton. En az 12 torbalı yükleme saati gerekir; takvimde yalnızca 10 saat vardır.')
    return cases


def senaryoyu_calistir(proje_dizini, senaryo_id, cikti_koku, sure=120):
    case=senaryolari_hazirla(proje_dizini)[senaryo_id]
    v=case['veriler'];ucret=case['degisiklik_gideri']
    folder=Path(cikti_koku)/senaryo_id
    folder.mkdir(parents=True,exist_ok=True)
    kapasite=yukleme_kapasitesini_kontrol_et(v)
    kapasite.to_csv(folder/'kapasite_kontrolu.csv',index=False,encoding='utf-8-sig')
    with ZipFile(folder/'girdiler.zip','w',compression=ZIP_DEFLATED) as z:
        for ad,df in v.items():z.writestr(ad+'.csv','\ufeff'+df.to_csv(index=False))
    bilgi=dict(senaryo_id=senaryo_id,ad=case['ad'],aciklama=case['aciklama'],
               degisiklik_gideri_tl_kaynak_saat=ucret,
               toplam_siparis_ton=float(v['siparisler']['miktar_ton'].sum()))
    if kapasite['kapasite_celiskisi'].any():
        bilgi.update(durum='Kapasite alt sınırı ile uygulanamaz',uygulanabilir=False,
                     kontrol='Zorunlu yükleme saati alt sınırı takvim kapasitesini aşıyor.',
                     cozum_calistirildi=False)
    else:
        # Her senaryonun referansı kendi fiyatı, talebi ve kısıtlarıyla denetlenir.
        ref=maliyet_ve_ozet(v,v['referans_plan'],v['referans_yuklemeler'],ucret)[-1]
        plan,yuk,stok,faaliyet,saatlik,ozet,cozum=firma_cizelgele(v,zaman_siniri=sure,goreli_acik=0.001,degisiklik_gideri=ucret)
        for ad,df in dict(onerilen_plan=plan,onerilen_yuklemeler=yuk,stok_hareketleri=stok,saatlik_sonuc=saatlik).items():
            df.to_csv(folder/(ad+'.csv'),index=False,encoding='utf-8-sig')
        tablo=pd.concat([ref.rename('Referans'),ozet.rename('Önerilen')],axis=1)
        tablo.index.name='olcut'
        tablo.to_csv(folder/'karsilastirma.csv',encoding='utf-8-sig')
        avantaj=ref.iloc[-1]-ozet.iloc[-1]
        bilgi.update(uygulanabilir=True,cozum_calistirildi=True,cozum=cozum,
                     referans_maliyet_tl=float(ref.iloc[-1]),onerilen_maliyet_tl=float(ozet.iloc[-1]),
                     avantaj_tl=float(avantaj),avantaj_yuzde=float(100*avantaj/ref.iloc[-1]),
                     degisen_uretim_kaynak_saat=int(ozet['Değişen kaynak-saat']),
                     referans_enerji_kwh=float(ref['Enerji (kWh)']),onerilen_enerji_kwh=float(ozet['Enerji (kWh)']),
                     teslim_kontrolu=True,stok_kontrolu=True,guc_kontrolu=True)
    dosyalar=[Path(proje_dizini)/'src'/f'{ad}.py' for ad in ['firma_verisi','firma_cizelgeleme','firma_senaryolari']]
    bilgi['kaynak_sha256']={str(p.relative_to(proje_dizini)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dosyalar}
    bilgi['girdi_zip_sha256']=hashlib.sha256((folder/'girdiler.zip').read_bytes()).hexdigest()
    (folder/'sonuc.json').write_text(json.dumps(bilgi,ensure_ascii=False,indent=2),encoding='utf-8')
    return bilgi


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('proje')
    parser.add_argument('senaryo',choices=['kis_fiyatlari','ilkbahar_fiyatlari','yaz_fiyatlari','yogun_dokme_talep','yuksek_degisim_gideri','kapasite_asimi'])
    parser.add_argument('cikti')
    parser.add_argument('--sure',type=float,default=120)
    args=parser.parse_args()
    print(json.dumps(senaryoyu_calistir(args.proje,args.senaryo,args.cikti,args.sure),ensure_ascii=True,indent=2))
