"""WattRota'nın iki öğütme hatlı sentetik firma verisi ve plan kontrolleri."""

import json
from pathlib import Path

import numpy as np
import pandas as pd


def firma_verisini_olustur(proje_dizini):
    """Fiyatları kullanmadan, malzeme dengesi kurulmuş sabit senaryo üret."""
    baslangic = pd.Timestamp('2025-10-06')
    bitis = pd.Timestamp('2025-10-09')
    saatler = pd.date_range(baslangic, bitis, freq='h', inclusive='left')
    gunler = pd.date_range(baslangic, periods=3, freq='D')
    urunler = pd.DataFrame([
        ['UR01','Portland çimentosu'], ['UR02','Kalker katkılı çimento'],
        ['UR03','İnce öğütülmüş Portland çimentosu'],
    ], columns=['urun_id','urun_adi'])
    kaynaklar = pd.DataFrame([
        ['H01','Öğütme hattı 1','ogutme'], ['H02','Öğütme hattı 2','ogutme'],
        ['P01','Ortak paketleme hattı','paketleme'],
        ['Y01','Dökme yükleme','dokme_yukleme'], ['Y02','Torbalı yükleme','torbali_yukleme'],
    ], columns=['kaynak_id','kaynak_adi','kaynak_turu'])
    kaynak_urun = pd.DataFrame([
        ['H01','UR01',60,1800], ['H01','UR02',70,1800], ['H01','UR03',50,1900],
        ['H02','UR01',70,2100], ['H02','UR02',80,2200],
        ['P01','UR01',80,100], ['P01','UR02',100,120], ['P01','UR03',60,90],
        *[[r,p,q,w] for r,q,w in [('Y01',180,60),('Y02',120,50)] for p in urunler['urun_id']],
    ], columns=['kaynak_id','urun_id','kapasite_ton_saat','calisma_gucu_kw'])
    kurallar = pd.DataFrame([
        ['H01',4,2,False,4,'UR01',100,200],
        ['H02',4,2,False,4,'UR02',120,250],
        ['P01',2,1,False,4,'UR01',30,40],
    ], columns=['kaynak_id','minimum_uretim_saat','minimum_durus_saat',
                'baslangicta_aktif','baslangic_durum_suresi_saat','baslangic_urun_ayari',
                'baslatma_enerjisi_kwh','baslatma_elektrik_disi_gider_tl'])
    gecis_satirlari = []
    for r in kurallar['kaynak_id']:
        uygun = kaynak_urun.loc[kaynak_urun['kaynak_id']==r,'urun_id']
        for onceki in uygun:
            for sonraki in uygun:
                if onceki != sonraki:
                    sure = 2 if r=='H01' and 'UR03' in [onceki,sonraki] else 1
                    gecis_satirlari.append([r,onceki,sonraki,sure,300 if r.startswith('H') else 35,75 if r.startswith('H') else 20])
    gecisler = pd.DataFrame(gecis_satirlari,columns=['kaynak_id','onceki_urun','sonraki_urun',
                                                  'hazirlik_saat','hazirlik_gucu_kw','elektrik_disi_gider_tl'])
    stoklar = pd.DataFrame([
        ['D01','UR01','dokme',60,1200,240,240],
        ['D02','UR02','dokme',80,1600,900,900],
        ['D03','UR03','dokme',50,800,180,180],
        ['T01','UR01','torbali',0,600,120,120],
        ['T02','UR02','torbali',0,700,100,100],
        ['T03','UR03','torbali',0,400,80,80],
    ], columns=['stok_id','urun_id','stok_turu','minimum_ton','kapasite_ton','baslangic_ton','son_hedef_ton'])
    depo = pd.DataFrame([['TORBALI_DEPO',1100]],columns=['depo_id','toplam_kapasite_ton'])

    # Rota adımları bütün siparişin tek blokta bitmesini değil, malzemenin işlem sırasını tanımlar.
    rota = []
    for p in urunler['urun_id']:
        for teslim in ['dokme','torbali']:
            rota_id = f'R_{p}_{teslim}'
            rota.append([rota_id,p,teslim,1,'ogutme','hammadde','dokme'])
            if teslim=='torbali':
                rota.append([rota_id,p,teslim,2,'paketleme','dokme','torbali'])
            rota.append([rota_id,p,teslim,2 if teslim=='dokme' else 3,
                         'dokme_yukleme' if teslim=='dokme' else 'torbali_yukleme',teslim,'teslim'])
    rotalar = pd.DataFrame(rota,columns=['rota_id','urun_id','teslim_turu','adim_no','islem_turu','girdi_stok_turu','cikti_stok_turu'])

    siparis_satirlari, emir_satirlari, baglar = [], [], []
    for g,gun in enumerate(gunler,1):
        for p,bulk,bag,deadline in [('UR01',720,320,18),('UR02',400,400,12),('UR03',160,240,17)]:
            for teslim,miktar,son_saat in [('dokme',bulk,deadline),('torbali',bag,12 if p=='UR01' else 15 if p=='UR02' else 18)]:
                sid=f'SP{g}_{p}_{teslim}'
                siparis_satirlari.append([sid,p,miktar,teslim,f'R_{p}_{teslim}',baslangic,
                                         gun+pd.Timedelta(hours=8),gun+pd.Timedelta(hours=son_saat)])
            # Öğütme emri iki teslim türünün ortak dökme ürün ihtiyacını karşılar.
            for islem,miktar,son in [('ogutme',bulk+bag,gun+pd.Timedelta(days=1)),
                                    ('paketleme',bag,gun+pd.Timedelta(hours=14))]:
                eid=f'IE{g}_{p}_{islem}'
                emir_satirlari.append([eid,p,islem,miktar,baslangic,son,True])
                if islem=='ogutme':
                    baglar.extend([[eid,f'SP{g}_{p}_dokme',bulk],[eid,f'SP{g}_{p}_torbali',bag]])
                else:
                    baglar.append([eid,f'SP{g}_{p}_torbali',bag])
    siparisler=pd.DataFrame(siparis_satirlari,columns=['siparis_id','urun_id','miktar_ton','teslim_turu','rota_id',
                                                    'gelis_zamani','en_erken_yukleme','teslim_zamani'])
    emirler=pd.DataFrame(emir_satirlari,columns=['is_emri_id','urun_id','islem_turu','miktar_ton',
                                              'serbest_birakma','tamamlanma_siniri','bolunebilir'])
    baglantilar=pd.DataFrame(baglar,columns=['is_emri_id','siparis_id','tahsis_ton'])

    takvim=pd.MultiIndex.from_product([kaynaklar['kaynak_id'],saatler],names=['kaynak_id','tarih_saat']).to_frame(index=False)
    takvim['kullanilabilir']=True
    yukleme=takvim['kaynak_id'].isin(['Y01','Y02'])
    takvim.loc[yukleme,'kullanilabilir']=(takvim.loc[yukleme,'tarih_saat'].dt.hour>=8)&(takvim.loc[yukleme,'tarih_saat'].dt.hour<18)
    bakim=pd.DataFrame([
        ['H01',pd.Timestamp('2025-10-07 20:00'),pd.Timestamp('2025-10-07 22:00')],
        ['H02',pd.Timestamp('2025-10-06 21:00'),pd.Timestamp('2025-10-06 23:00')],
        ['P01',pd.Timestamp('2025-10-08 20:00'),pd.Timestamp('2025-10-08 21:00')],
        ['Y01',pd.Timestamp('2025-10-07 12:00'),pd.Timestamp('2025-10-07 13:00')],
    ],columns=['kaynak_id','baslangic','bitis'])
    for b in bakim.itertuples(index=False):
        maske=(takvim['kaynak_id']==b.kaynak_id)&(takvim['tarih_saat']>=b.baslangic)&(takvim['tarih_saat']<b.bitis)
        takvim.loc[maske,'kullanilabilir']=False
    tesis=pd.DataFrame({'tarih_saat':saatler,'temel_yuk_kw':300,'guc_siniri_kw':4700})

    plan=takvim.loc[takvim['kaynak_id'].isin(kurallar['kaynak_id']),['kaynak_id','tarih_saat']].copy()
    plan['durum']='kapali'; plan['urun_id']=''; plan['is_emri_id']=''
    bloklar=[]
    for g,gun in enumerate(gunler,1):
        if g in [1,3]:
            bloklar.extend([['H01',gun,0,8,'uretim','UR01',g],['H01',gun,8,10,'hazirlik','UR03',g],['H01',gun,10,18,'uretim','UR03',g]])
        else:
            bloklar.extend([['H01',gun,0,8,'uretim','UR03',g],['H01',gun,8,10,'hazirlik','UR01',g],['H01',gun,10,18,'uretim','UR01',g]])
        if g in [1,3]:
            bloklar.extend([['H02',gun,0,10,'uretim','UR02',g],['H02',gun,10,11,'hazirlik','UR01',g],['H02',gun,11,19,'uretim','UR01',g]])
        else:
            bloklar.extend([['H02',gun,0,8,'uretim','UR01',g],['H02',gun,8,9,'hazirlik','UR02',g],['H02',gun,9,19,'uretim','UR02',g]])
        if g>1:
            bloklar.append(['P01',gun,-1,0,'hazirlik','UR01',g])
        bloklar.extend([['P01',gun,0,4,'uretim','UR01',g],['P01',gun,4,5,'hazirlik','UR02',g],
                        ['P01',gun,5,9,'uretim','UR02',g],['P01',gun,9,10,'hazirlik','UR03',g],
                        ['P01',gun,10,14,'uretim','UR03',g]])
    for r,gun,a,b,durum,p,g in bloklar:
        start,end=gun+pd.Timedelta(hours=a),gun+pd.Timedelta(hours=b)
        # Gece hazırlığı önceki günün son saatinde gerçekleşir.
        mask=(plan['kaynak_id']==r)&(plan['tarih_saat']>=start)&(plan['tarih_saat']<end)
        if plan.loc[mask,'durum'].ne('kapali').any():
            raise ValueError('Referans bloklar çakışıyor.')
        plan.loc[mask,['durum','urun_id']]=[durum,p]
        if durum=='uretim':
            islem='paketleme' if r=='P01' else 'ogutme'
            plan.loc[mask,'is_emri_id']=f'IE{g}_{p}_{islem}'

    yukler=[]
    for g,gun in enumerate(gunler,1):
        for p,tur,r,dagilim in [
            ('UR01','dokme','Y01',[(11,180),(13,180),(15,180),(17,180)]),
            ('UR02','dokme','Y01',[(8,180),(9,180),(10,40)]),
            ('UR03','dokme','Y01',[(16,160)]),
            ('UR01','torbali','Y02',[(8,120),(9,120),(10,80)]),
            ('UR02','torbali','Y02',[(11,100),(12,100),(13,100),(14,100)]),
            ('UR03','torbali','Y02',[(15,120),(16,120)]),
        ]:
            yukler.extend([[f'SP{g}_{p}_{tur}',r,gun+pd.Timedelta(hours=h),q] for h,q in dagilim])
    yuklemeler=pd.DataFrame(yukler,columns=['siparis_id','kaynak_id','tarih_saat','miktar_ton'])

    # Fiyatlar yalnız üretim ve sevkiyat planı kurulduktan sonra okunur.
    fiyat=pd.read_csv(Path(proje_dizini)/'data/raw/epias/Piyasa_Takas_Fiyati-01012025-31122025.csv',
                      sep=';',decimal=',',thousands='.',dtype={'Tarih':str,'Saat':str})
    fiyat['tarih_saat']=pd.to_datetime(fiyat['Tarih']+' '+fiyat['Saat'],format='%d.%m.%Y %H:%M')
    fiyat=fiyat.loc[(fiyat['tarih_saat']>=baslangic)&(fiyat['tarih_saat']<bitis),['tarih_saat','PTF (TL/MWh)']].reset_index(drop=True)
    v=dict(urunler=urunler,kaynaklar=kaynaklar,kaynak_urun=kaynak_urun,isletme_kurallari=kurallar,
           urun_gecisleri=gecisler,stok_alanlari=stoklar,depo_kurallari=depo,rotalar=rotalar,
           siparisler=siparisler,is_emirleri=emirler,is_emri_siparis_baglantisi=baglantilar,
           kaynak_takvimi=takvim,bakimlar=bakim,tesis_takvimi=tesis,referans_plan=plan,
           referans_yuklemeler=yuklemeler,fiyatlar=fiyat)
    uygunluk=[]
    kaynak_tip=kaynaklar.set_index('kaynak_id')['kaynak_turu']
    for adim in rotalar.itertuples(index=False):
        secenekler=kaynak_urun[(kaynak_urun['urun_id']==adim.urun_id)
                              & kaynak_urun['kaynak_id'].map(kaynak_tip).eq(adim.islem_turu)]
        uygunluk.extend([[adim.rota_id,adim.adim_no,r] for r in secenekler['kaynak_id']])
    v['rota_kaynaklari']=pd.DataFrame(uygunluk,columns=['rota_id','adim_no','kaynak_id'])
    return v


def kontrol(kosul,mesaj):
    if not bool(kosul):
        raise ValueError(mesaj)


def firma_planini_dogrula(v,plan=None,yuklemeler=None):
    """İş emirleri, kaynak durumları ve iki stok katmanını bağımsız hesapla."""
    plan=v['referans_plan'] if plan is None else plan
    yuklemeler=v['referans_yuklemeler'] if yuklemeler is None else yuklemeler
    kaynaklar=v['kaynaklar'].set_index('kaynak_id',verify_integrity=True)
    modlar=v['kaynak_urun'].set_index(['kaynak_id','urun_id'],verify_integrity=True)
    emirler=v['is_emirleri'].set_index('is_emri_id',verify_integrity=True)
    siparis=v['siparisler'].set_index('siparis_id',verify_integrity=True)
    stok_alan=v['stok_alanlari'].set_index(['urun_id','stok_turu'],verify_integrity=True)
    kurallar=v['isletme_kurallari'].set_index('kaynak_id',verify_integrity=True)
    gecis=v['urun_gecisleri'].set_index(['kaynak_id','onceki_urun','sonraki_urun'],verify_integrity=True)
    takvim=v['kaynak_takvimi'].set_index(['kaynak_id','tarih_saat'],verify_integrity=True)
    tesis=v['tesis_takvimi'].set_index('tarih_saat',verify_integrity=True)
    saatler=pd.DatetimeIndex(tesis.index)
    depo_kapasite=float(v['depo_kurallari'].iloc[0]['toplam_kapasite_ton'])
    urunler=list(v['urunler']['urun_id'])
    kontrol(saatler.equals(pd.date_range(saatler[0],periods=len(saatler),freq='h')),'Tesis saatleri kesintisiz olmalı.')
    kontrol(pd.DatetimeIndex(v['fiyatlar']['tarih_saat']).equals(saatler),'Fiyat dönemi eşleşmiyor.')
    kontrol(v['fiyatlar']['PTF (TL/MWh)'].notna().all(),'Eksik PTF.')
    kontrol(kaynaklar.index.is_unique and set(kurallar.index).issubset(kaynaklar.index),'Kaynak bağlantısı hatalı.')
    kontrol(set(emirler['urun_id']).issubset(urunler),'İş emrinde tanımsız ürün.')
    kontrol((emirler['miktar_ton']>0).all() and (siparis['miktar_ton']>0).all(),'Miktar pozitif olmalı.')
    kontrol((siparis['gelis_zamani']<=siparis['en_erken_yukleme']).all()
             and (siparis['en_erken_yukleme']<siparis['teslim_zamani']).all(),'Sipariş zamanları geçersiz.')
    kontrol(set(plan['kaynak_id'])==set(kurallar.index),'Üretim kaynakları eksik veya tanımsız.')
    kontrol(plan['durum'].isin(['kapali','uretim','hazirlik']).all(),'Tanımsız faaliyet.')
    kontrol(not plan.duplicated(['kaynak_id','tarih_saat']).any(),'Aynı kaynakta çakışma.')
    plan_index=plan.set_index(['kaynak_id','tarih_saat'],verify_integrity=True)
    for r in kurallar.index:
        kontrol(pd.DatetimeIndex(plan.loc[plan['kaynak_id']==r,'tarih_saat']).equals(saatler),f'{r}: eksik/sırasız saat.')
    for r in kaynaklar.index:
        tak=v['kaynak_takvimi'].loc[v['kaynak_takvimi']['kaynak_id']==r,'tarih_saat']
        kontrol(pd.DatetimeIndex(tak).equals(saatler),f'{r}: kaynak takvimi eksik/sırasız.')
    for b in v['bakimlar'].itertuples(index=False):
        kontrol(b.kaynak_id in kaynaklar.index and b.baslangic<b.bitis,'Bakım aralığı geçersiz.')
        bs=saatler[(saatler>=b.baslangic)&(saatler<b.bitis)]
        kontrol(not takvim.loc[[(b.kaynak_id,t) for t in bs],'kullanilabilir'].any(),'Bakım takvime işlenmemiş.')
    kontrol(yuklemeler['siparis_id'].isin(siparis.index).all(),'Tanımsız sipariş yüklemesi.')
    kontrol(yuklemeler['kaynak_id'].isin(kaynaklar.index).all(),'Tanımsız yükleme kaynağı.')
    kontrol(yuklemeler['tarih_saat'].isin(saatler).all(),'Yükleme dönem dışında.')
    kontrol((yuklemeler['miktar_ton']>0).all(),'Yükleme miktarı pozitif olmalı.')
    kontrol(not yuklemeler.duplicated(['kaynak_id','tarih_saat']).any(),'Bir yükleme kaynağında eşzamanlı sipariş.')
    for sid,s in siparis.iterrows():
        y=yuklemeler[yuklemeler['siparis_id']==sid]
        kontrol(np.isclose(y['miktar_ton'].sum(),s['miktar_ton'],atol=1e-6),f'{sid}: eksik/fazla teslimat.')
        kontrol(((y['tarih_saat']>=s['gelis_zamani'])&(y['tarih_saat']>=s['en_erken_yukleme'])
                 &(y['tarih_saat']+pd.Timedelta(hours=1)<=s['teslim_zamani'])).all(),f'{sid}: teslim aralığı ihlali.')
    # Rota ve iş emri bağlantıları: miktarlar aynı aşama içinde tahsis edilir.
    rota=v['rotalar']
    kontrol(not rota.duplicated(['rota_id','adim_no']).any(),'Tekrarlı rota adımı.')
    rota_kaynak=v['rota_kaynaklari']
    kontrol(not rota_kaynak.duplicated(['rota_id','adim_no','kaynak_id']).any(),'Tekrarlı rota-kaynak eşleşmesi.')
    for adim in rota.itertuples(index=False):
        uygun=rota_kaynak[(rota_kaynak['rota_id']==adim.rota_id)&(rota_kaynak['adim_no']==adim.adim_no)]
        kontrol(len(uygun)>0,f'{adim.rota_id}: uygun kaynak yok.')
        for r in uygun['kaynak_id']:
            kontrol(r in kaynaklar.index and kaynaklar.loc[r,'kaynak_turu']==adim.islem_turu
                     and (r,adim.urun_id) in modlar.index,f'{adim.rota_id}: rota kaynağı uygun değil.')
    for sid,s in siparis.iterrows():
        adimlar=rota[rota['rota_id']==s['rota_id']].sort_values('adim_no')
        beklenen=['ogutme','dokme_yukleme'] if s['teslim_turu']=='dokme' else ['ogutme','paketleme','torbali_yukleme']
        kontrol(list(adimlar['islem_turu'])==beklenen and adimlar['urun_id'].eq(s['urun_id']).all(),f'{sid}: rota hatalı.')
    bag=v['is_emri_siparis_baglantisi']
    kontrol(bag['is_emri_id'].isin(emirler.index).all() and bag['siparis_id'].isin(siparis.index).all(),'İş emri tahsis bağlantısı hatalı.')
    for eid,e in emirler.iterrows():
        tahsis=bag[bag['is_emri_id']==eid]
        kontrol(np.isclose(tahsis['tahsis_ton'].sum(),e['miktar_ton']),f'{eid}: tahsis miktarı eşleşmiyor.')
        kontrol(siparis.loc[tahsis['siparis_id'],'urun_id'].eq(e['urun_id']).all(),f'{eid}: tahsis ürünü farklı.')
    for sid,s in siparis.iterrows():
        for islem in ['ogutme']+(['paketleme'] if s['teslim_turu']=='torbali' else []):
            ilgili=bag[(bag['siparis_id']==sid)&bag['is_emri_id'].map(emirler['islem_turu']).eq(islem)]
            kontrol(np.isclose(ilgili['tahsis_ton'].sum(),s['miktar_ton']),f'{sid}: aşama tahsisi eksik.')

    stok=stok_alan['baslangic_ton'].astype(float).to_dict()
    kontrol(((stok_alan['minimum_ton']>=0)&(stok_alan['minimum_ton']<=stok_alan['baslangic_ton'])
             &(stok_alan['baslangic_ton']<=stok_alan['kapasite_ton'])
             &(stok_alan['minimum_ton']<=stok_alan['son_hedef_ton'])
             &(stok_alan['son_hedef_ton']<=stok_alan['kapasite_ton'])).all(),'Başlangıç/son stok sınırı hatalı.')
    kontrol(sum(q for (p,tip),q in stok.items() if tip=='torbali')<=depo_kapasite,'Başlangıç torbalı stoğu ortak depoyu aşıyor.')
    durumlar={}
    for r,k in kurallar.iterrows():
        kontrol(not k['baslangicta_aktif'],'Bu veri sürümü kapalı başlangıç kullanır.')
        durumlar[r]=dict(durum='kapali',urun='',sure=int(k['baslangic_durum_suresi_saat']),
                         ayar=k['baslangic_urun_ayari'],hazirlik_gereken=0,hedef='',hazirlik_gucu=0)
    tamamlanan={eid:0.0 for eid in emirler.index}
    hareketler=[]; saatlik=[]; faaliyetler=[]
    for t in saatler:
        cikis={key:0.0 for key in stok}
        giris={key:0.0 for key in stok}
        enerji=float(tesis.loc[t,'temel_yuk_kw']); elektrik_disi=0.0
        for r,k in kurallar.iterrows():
            satir=plan_index.loc[(r,t)]
            d,p,eid=satir['durum'],satir['urun_id'],satir['is_emri_id']
            once=durumlar[r]
            ayni=d==once['durum'] and (d=='kapali' or p==once['urun'])
            if not ayni:
                if once['durum']=='uretim':
                    kontrol(once['sure']>=k['minimum_uretim_saat'],f'{r}: minimum üretim süresi ihlali.')
                if once['durum']=='hazirlik':
                    kontrol(once['sure']==once['hazirlik_gereken'],f'{r}: eksik/fazla hazırlık.')
                    once['ayar']=once['hedef']
                if once['durum']=='kapali' and d!='kapali':
                    kontrol(once['sure']>=k['minimum_durus_saat'],f'{r}: minimum duruş ihlali.')
                once['sure']=0
                if d=='hazirlik':
                    key=(r,once['ayar'],p)
                    kontrol(key in gecis.index,f'{r}: tanımsız ürün geçişi.')
                    g=gecis.loc[key]
                    once.update(hazirlik_gereken=int(g['hazirlik_saat']),hedef=p,hazirlik_gucu=float(g['hazirlik_gucu_kw']))
                    elektrik_disi+=float(g['elektrik_disi_gider_tl'])
            kontrol(d=='kapali' or takvim.loc[(r,t),'kullanilabilir'],f'{r}: bakım/uygunluk ihlali.')
            baslatma=once['durum']=='kapali' and d!='kapali'
            kaynak_enerji=float(k['baslatma_enerjisi_kwh']) if baslatma else 0.0
            elektrik_disi+=float(k['baslatma_elektrik_disi_gider_tl']) if baslatma else 0.0
            miktar=0.0
            if d=='kapali':
                kontrol(p=='' and eid=='',f'{r}: kapalı saatte ürün/iş emri atanmış.')
            elif d=='hazirlik':
                kontrol(eid=='',f'{r}: hazırlık üretim iş emri sayılmaz.')
                kaynak_enerji+=once['hazirlik_gucu']
            else:
                kontrol((r,p) in modlar.index and p==once['ayar'],f'{r}: ürün uygunluğu/ayar ihlali.')
                kontrol(eid in emirler.index,f'{r}: tanımsız iş emri.')
                e=emirler.loc[eid]
                kontrol(e['urun_id']==p and e['islem_turu']==kaynaklar.loc[r,'kaynak_turu'],f'{r}: iş emri/işlem uyumsuz.')
                kontrol(e['serbest_birakma']<=t and t+pd.Timedelta(hours=1)<=e['tamamlanma_siniri'],f'{eid}: iş emri zamanı ihlali.')
                miktar=float(modlar.loc[(r,p),'kapasite_ton_saat'])
                kaynak_enerji+=float(modlar.loc[(r,p),'calisma_gucu_kw'])
                tamamlanan[eid]+=miktar
                if kaynaklar.loc[r,'kaynak_turu']=='ogutme':
                    giris[p,'dokme']+=miktar
                else:
                    cikis[p,'dokme']+=miktar
                    giris[p,'torbali']+=miktar
            enerji+=kaynak_enerji
            faaliyetler.append([r,t,d,p,eid,miktar,int(baslatma),kaynak_enerji])
            once.update(durum=d,urun=p,sure=once['sure']+1)

        for y in yuklemeler[yuklemeler['tarih_saat']==t].itertuples(index=False):
            s=siparis.loc[y.siparis_id]; r=y.kaynak_id; p=s['urun_id']
            tip='dokme_yukleme' if s['teslim_turu']=='dokme' else 'torbali_yukleme'
            kontrol(kaynaklar.loc[r,'kaynak_turu']==tip,f'{y.siparis_id}: yanlış yükleme kaynağı.')
            kontrol((r,p) in modlar.index and takvim.loc[(r,t),'kullanilabilir'],f'{r}: yükleme uygun değil.')
            kontrol(y.miktar_ton<=modlar.loc[(r,p),'kapasite_ton_saat']+1e-6,f'{r}: yükleme kapasitesi aşıldı.')
            cikis[p,s['teslim_turu']]+=y.miktar_ton
            enerji+=float(modlar.loc[(r,p),'calisma_gucu_kw'])
        for key in stok:
            ilk=stok[key]
            kontrol(ilk-cikis[key]>=stok_alan.loc[key,'minimum_ton']-1e-6,f'{key}, {t}: dönem başı stok yetersiz.')
            stok[key]=ilk-cikis[key]+giris[key]
            kontrol(stok[key]<=stok_alan.loc[key,'kapasite_ton']+1e-6,f'{key}, {t}: stok kapasitesi aşıldı.')
            hareketler.append([t,key[0],key[1],ilk,giris[key],cikis[key],stok[key]])
        torbali=sum(q for (p,tip),q in stok.items() if tip=='torbali')
        kontrol(torbali<=depo_kapasite+1e-6,f'{t}: ortak torbalı depo doldu.')
        kontrol(enerji<=tesis.loc[t,'guc_siniri_kw']+1e-6,f'{t}: ortak güç sınırı aşıldı.')
        saatlik.append([t,enerji,elektrik_disi,torbali])
    for r,once in durumlar.items():
        k=kurallar.loc[r]
        alt=k['minimum_uretim_saat'] if once['durum']=='uretim' else k['minimum_durus_saat'] if once['durum']=='kapali' else once['hazirlik_gereken']
        kontrol(once['sure']>=alt,f'{r}: ufuk sonunda tamamlanmamış süre.')
        if once['durum']=='hazirlik':
            kontrol(once['sure']==alt,f'{r}: ufuk sonunda hazırlık süresi fazla.')
    for eid,q in tamamlanan.items():
        kontrol(np.isclose(q,emirler.loc[eid,'miktar_ton']),f'{eid}: iş emri miktarı eşleşmiyor.')
    for key,q in stok.items():
        kontrol(np.isclose(q,stok_alan.loc[key,'son_hedef_ton']),f'{key}: dönem sonu stok hedefi sağlanmadı.')
    hareket=pd.DataFrame(hareketler,columns=['tarih_saat','urun_id','stok_turu','baslangic_ton','giris_ton','cikis_ton','son_stok_ton'])
    faaliyet=pd.DataFrame(faaliyetler,columns=['kaynak_id','tarih_saat','durum','urun_id','is_emri_id','miktar_ton','baslatma','enerji_kwh'])
    saatlik=pd.DataFrame(saatlik,columns=['tarih_saat','toplam_enerji_kwh','elektrik_disi_gider_tl','torbali_toplam_stok_ton'])
    saatlik=saatlik.merge(v['fiyatlar'],on='tarih_saat',validate='one_to_one')
    saatlik['ptf_bedeli_tl']=saatlik['toplam_enerji_kwh']/1000*saatlik['PTF (TL/MWh)']
    return hareket,faaliyet,saatlik


def hata_kontrolleri(v):
    """Kritik kural ihlallerinin yakalandığını küçük bozulmalarla sına."""
    import copy
    sonuclar=[]
    def reddet(ad,veri,plan=None,yuk=None):
        try:
            firma_planini_dogrula(veri,plan,yuk)
        except ValueError as exc:
            sonuclar.append([ad,'Reddedildi',str(exc)])
        else:
            raise AssertionError(f'Hatalı veri kabul edildi: {ad}')
    bozuk=v['referans_plan'].copy()
    bozuk.loc[(bozuk['kaynak_id']=='H02')&(bozuk['durum']=='uretim'),'urun_id']='UR03'
    reddet('Uygun olmayan makinede ürün',v,bozuk)
    bozuk=v['referans_plan'].copy()
    bozuk.loc[(bozuk['kaynak_id']=='H01')&(bozuk['tarih_saat']=='2025-10-06 08:00'),['durum','urun_id','is_emri_id']]=['uretim','UR01','IE1_UR01_ogutme']
    reddet('Ürün değişimi hazırlığı atlama',v,bozuk)
    bozuk=copy.deepcopy(v)
    bozuk['stok_alanlari'].loc[(bozuk['stok_alanlari']['urun_id']=='UR01')&(bozuk['stok_alanlari']['stok_turu']=='dokme'),'baslangic_ton']=60
    reddet('Paketleme için dökme stok yok',bozuk)
    bozuk=copy.deepcopy(v)
    bozuk['stok_alanlari'].loc[(bozuk['stok_alanlari']['urun_id']=='UR01')&(bozuk['stok_alanlari']['stok_turu']=='dokme'),'kapasite_ton']=250
    reddet('Dökme silo taşması',bozuk)
    bozuk=copy.deepcopy(v)
    bozuk['depo_kurallari']['toplam_kapasite_ton']=400
    reddet('Ortak torbalı depo kapasitesi',bozuk)
    bozuk=copy.deepcopy(v)
    bozuk['kaynak_takvimi'].loc[(bozuk['kaynak_takvimi']['kaynak_id']=='H01')
                              &(bozuk['kaynak_takvimi']['tarih_saat']=='2025-10-06 00:00'),'kullanilabilir']=False
    reddet('Bakımda üretim',bozuk)
    bozuk=copy.deepcopy(v)
    bozuk['tesis_takvimi']['guc_siniri_kw']=4000
    reddet('Ortak elektrik güç sınırı',bozuk)
    bozuk=v['referans_yuklemeler'].copy()
    idx=bozuk.index[(bozuk['kaynak_id']=='Y01')&(bozuk['tarih_saat']=='2025-10-06 17:00')][0]
    bozuk.loc[idx,'kaynak_id']='Y02'
    reddet('Dökme siparişi torbalı noktadan yükleme',v,yuk=bozuk)
    bozuk=v['referans_yuklemeler'].copy()
    bozuk.loc[0,'tarih_saat']=pd.Timestamp('2025-10-06 19:00')
    reddet('Geç teslimat',v,yuk=bozuk)
    reddet('Eksik sevkiyat',v,yuk=v['referans_yuklemeler'].iloc[1:].copy())
    bozuk=copy.deepcopy(v)
    bozuk['is_emirleri'].loc[0,'miktar_ton']+=60
    reddet('İş emri miktar tahsisi',bozuk)
    bozuk=copy.deepcopy(v)
    idx=bozuk['rotalar'].index[(bozuk['rotalar']['teslim_turu']=='torbali')&(bozuk['rotalar']['adim_no']==2)][0]
    bozuk['rotalar'].loc[idx,'islem_turu']='dokme_yukleme'
    reddet('Torbalı rotada paketleme atlama',bozuk)
    bozuk=copy.deepcopy(v)
    bozuk['stok_alanlari'].loc[0,'son_hedef_ton']+=60
    reddet('Dönem sonu stok hedefi',bozuk)
    return pd.DataFrame(sonuclar,columns=['deneme','sonuc','yakalanan_ihlal'])


def veri_paketini_kaydet(v,hareket,faaliyet,saatlik,testler,proje_dizini):
    """Girdileri ve hesaplanan referans çıktıları ayrı klasörlerde sakla."""
    proje=Path(proje_dizini)
    girdi=proje/'data/synthetic/firma_01'
    sonuc=proje/'data/results/firma_01_veri_kontrolu'
    girdi.mkdir(parents=True,exist_ok=True); sonuc.mkdir(parents=True,exist_ok=True)
    girdiler={ad:tablo for ad,tablo in v.items() if not ad.startswith('referans_')}
    ciktilar={'referans_plan':v['referans_plan'],'referans_yuklemeler':v['referans_yuklemeler'],
              'stok_hareketleri':hareket,'faaliyetler':faaliyet,'saatlik_enerji_maliyet':saatlik,'hata_kontrolleri':testler}
    birimler={'miktar_ton':'ton','kapasite_ton_saat':'ton/saat','calisma_gucu_kw':'kW',
              'minimum_ton':'ton','kapasite_ton':'ton','baslangic_ton':'ton','son_hedef_ton':'ton',
              'toplam_kapasite_ton':'ton','minimum_uretim_saat':'saat','minimum_durus_saat':'saat',
              'baslangic_durum_suresi_saat':'saat','baslatma_enerjisi_kwh':'kWh',
              'baslatma_elektrik_disi_gider_tl':'TL','hazirlik_saat':'saat','hazirlik_gucu_kw':'kW',
              'elektrik_disi_gider_tl':'TL','tahsis_ton':'ton','temel_yuk_kw':'kW',
              'guc_siniri_kw':'kW','torbali_depo_kapasite_ton':'ton','PTF (TL/MWh)':'TL/MWh'}
    aciklama={
        'urun_id':'Ürün kimliği', 'urun_adi':'Senaryo ürün adı', 'kaynak_id':'Makine/hat/yükleme kimliği',
        'kaynak_adi':'Kaynak açıklaması','kaynak_turu':'ogutme, paketleme, dokme_yukleme veya torbali_yukleme',
        'kapasite_ton_saat':'Uygun ürün için saatlik çıktı veya yükleme kapasitesi',
        'calisma_gucu_kw':'Aktif saatte kaynak ve kapsanan yardımcıların toplam gücü',
        'minimum_uretim_saat':'Kesintisiz üretim bloğunun en kısa süresi','minimum_durus_saat':'Yeniden açılmadan önce kapalı kalma süresi',
        'baslangicta_aktif':'Plan başında aktiflik','baslangic_durum_suresi_saat':'Başlangıç durumunda önceden geçen süre',
        'baslangic_urun_ayari':'Hazırlık gereksinimini belirleyen ilk ürün ayarı',
        'baslatma_enerjisi_kwh':'Açılış başına normal tüketime ek enerji',
        'baslatma_elektrik_disi_gider_tl':'Açılış başına elektrik dışı gider',
        'onceki_urun':'Hazırlık öncesi ürün ayarı','sonraki_urun':'Hazırlık sonunda elde edilen ürün ayarı',
        'hazirlik_saat':'Ürün değiştirme süresi','hazirlik_gucu_kw':'Hazırlık saatindeki toplam güç',
        'elektrik_disi_gider_tl':'Geçiş başlangıcında bir kez oluşan elektrik dışı gider',
        'stok_id':'Ürüne ayrılmış stok alanı','stok_turu':'dokme veya torbali',
        'minimum_ton':'Korunacak en az stok','kapasite_ton':'En yüksek stok',
        'baslangic_ton':'Plan başlangıcı stoğu','son_hedef_ton':'Dönem sonu eşitlik hedefi',
        'depo_id':'Ortak depo kimliği','toplam_kapasite_ton':'Torbalı stokların toplam üst sınırı',
        'rota_id':'Ürün ve teslim biçimine ait işlem rotası','teslim_turu':'dokme veya torbali',
        'adim_no':'Rotadaki işlem sırası','islem_turu':'İşlemi yapabilecek kaynak türü',
        'girdi_stok_turu':'İşlemin malzeme aldığı stok türü','cikti_stok_turu':'İşlem sonunda oluşan stok veya teslimat',
        'siparis_id':'Müşteri siparişi kimliği','miktar_ton':'Sipariş veya iş emri toplam miktarı',
        'gelis_zamani':'Siparişin bilindiği an','en_erken_yukleme':'İzin verilen ilk yükleme saati',
        'teslim_zamani':'Son yüklemenin bitiş sınırı','is_emri_id':'Ürün ve üretim/paketleme aşaması için iş emri',
        'serbest_birakma':'İş emrinin çalışmaya başlayabileceği ilk an','tamamlanma_siniri':'İş emrinin tamamlanma sınırı',
        'bolunebilir':'İş emri uygun kaynak/zaman bloklarına ayrılabilir',
        'tahsis_ton':'İlgili aşamadaki iş emrinden siparişe ayrılan miktar; farklı aşamalar toplanmaz',
        'tarih_saat':'Saatlik dönem başlangıcı, Türkiye yerel saati','kullanilabilir':'Kaynak o saatte kullanılabilir mi?',
        'baslangic':'Bakım başlangıcı, dahil','bitis':'Bakım bitişi, hariç',
        'temel_yuk_kw':'Ayrı makinelere yazılmayan kontrol dışı tesis yükü',
        'guc_siniri_kw':'Tesis toplam saatlik ortalama güç üst sınırı',
        'torbali_depo_kapasite_ton':'Aynı saatte bütün torbalı stokların toplam üst sınırı',
        'PTF (TL/MWh)':'EPİAŞ gerçekleşmiş saatlik piyasa takas fiyatı',
    }
    sozluk=[]; dayanak=[]
    for ad,tablo in girdiler.items():
        for alan in tablo.columns:
            birim=birimler.get(alan,'tarih-saat' if pd.api.types.is_datetime64_any_dtype(tablo[alan]) else '—')
            kontrol(alan in aciklama,f'Veri sözlüğü açıklaması eksik: {alan}')
            kaynak='EPİAŞ CSV' if ad=='fiyatlar' else 'Sentetik firma senaryosu'
            sozluk.append([ad+'.csv',alan,str(tablo[alan].dtype),birim,aciklama[alan],kaynak])
            if alan in birimler and ad!='fiyatlar':
                for idx,deger in tablo[alan].items():
                    baglam='; '.join(f'{k}={tablo.loc[idx,k]}' for k in ['kaynak_id','urun_id','stok_id','siparis_id','is_emri_id','onceki_urun','sonraki_urun'] if k in tablo.columns)
                    if ad in ['tesis_takvimi'] and idx>0:
                        continue
                    dayanak.append([ad,baglam,alan,float(deger),birim,'Senaryo varsayımı',
                                    'Kurgusal tesis tasarımı; gerçek işletme ölçümü değildir.'])
    sozluk=pd.DataFrame(sozluk,columns=['dosya','alan','veri_turu','birim','aciklama','dayanak'])
    dayanak=pd.DataFrame(dayanak,columns=['tablo','baglam','parametre','deger','birim','nitelik','gerekce'])
    girdiler['veri_sozlugu']=sozluk; girdiler['parametre_dayanaklari']=dayanak
    for klasor,tablolar in [(girdi,girdiler),(sonuc,ciktilar)]:
        for ad,tablo in tablolar.items():
            path=klasor/f'{ad}.csv'
            tablo.to_csv(path,index=False,encoding='utf-8-sig',date_format='%Y-%m-%d %H:%M:%S')
            geri=pd.read_csv(path,encoding='utf-8-sig',keep_default_na=False)
            kontrol(len(geri)==len(tablo) and list(geri.columns)==list(tablo.columns),f'CSV kontrolü başarısız: {ad}')
    meta=dict(senaryo_id='firma_01',surum='1.0',sentetik=True,
              baslangic='2025-10-06 00:00:00',bitis_haric='2025-10-09 00:00:00',
              zaman_dilimi='Europe/Istanbul',donem_saat=1,rastgele=False,
              uretim_girdisi='Senaryo varsayımları',fiyat_kaynagi='EPİAŞ 2025 CSV',
              siparis_sayisi=len(v['siparisler']),is_emri_sayisi=len(v['is_emirleri']),
              rota_sayisi=int(v['rotalar']['rota_id'].nunique()),
              notlar='İş emirleri ürün ve aşama bazında birleştirilir; malzeme uygunluğu stok dengesiyle sağlanır.')
    (girdi/'senaryo.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return girdi,sonuc,sozluk
