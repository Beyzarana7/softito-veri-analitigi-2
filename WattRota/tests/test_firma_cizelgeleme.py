"""Çok kaynaklı modeli küçük bağımsız aramayla karşılaştırır."""
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd

proje=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]
sys.path.insert(0,str(proje/'src'))
from firma_cizelgeleme import firma_verisini_oku,firma_cizelgele,maliyet_ve_ozet


def kucuk_veri(v):
    v=copy.deepcopy(v)
    ts=pd.date_range('2025-10-06',periods=8,freq='h')
    v['urunler']=v['urunler'].iloc[:1].copy()
    v['kaynak_urun']=v['kaynak_urun'][v['kaynak_urun']['urun_id']=='UR01'].copy()
    for r,cap,w in [('H01',60,200),('H02',60,300),('P01',30,50),('Y01',120,10),('Y02',120,10)]:
        v['kaynak_urun'].loc[v['kaynak_urun']['kaynak_id']==r,['kapasite_ton_saat','calisma_gucu_kw']]=[cap,w]
    for col,val in [('minimum_uretim_saat',2),('minimum_durus_saat',1),('baslangic_urun_ayari','UR01'),
                    ('baslatma_enerjisi_kwh',10),('baslatma_elektrik_disi_gider_tl',5)]:
        v['isletme_kurallari'][col]=val
    v['urun_gecisleri']=v['urun_gecisleri'].iloc[:0].copy()
    v['stok_alanlari']=v['stok_alanlari'][v['stok_alanlari']['urun_id']=='UR01'].copy()
    for tip,minimum,cap,ilk in [('dokme',0,240,60),('torbali',0,120,0)]:
        v['stok_alanlari'].loc[v['stok_alanlari']['stok_turu']==tip,['minimum_ton','kapasite_ton','baslangic_ton','son_hedef_ton']]=[minimum,cap,ilk,ilk]
    v['depo_kurallari']['toplam_kapasite_ton']=120
    v['rotalar']=v['rotalar'][v['rotalar']['urun_id']=='UR01'].copy()
    v['rota_kaynaklari']=v['rota_kaynaklari'][v['rota_kaynaklari']['rota_id'].isin(v['rotalar']['rota_id'])].copy()
    end=ts[-1]+pd.Timedelta(hours=1)
    v['siparisler']=pd.DataFrame([
        ['B','UR01',60,'dokme','R_UR01_dokme',ts[0],ts[0],end],
        ['T','UR01',60,'torbali','R_UR01_torbali',ts[0],ts[0],end],
    ],columns=v['siparisler'].columns)
    v['is_emirleri']=pd.DataFrame([
        ['OG','UR01','ogutme',120,ts[0],end,True],
        ['PA','UR01','paketleme',60,ts[0],end,True],
    ],columns=v['is_emirleri'].columns)
    v['is_emri_siparis_baglantisi']=pd.DataFrame([
        ['OG','B',60],['OG','T',60],['PA','T',60],
    ],columns=v['is_emri_siparis_baglantisi'].columns)
    v['kaynak_takvimi']=pd.MultiIndex.from_product([v['kaynaklar']['kaynak_id'],ts],names=['kaynak_id','tarih_saat']).to_frame(index=False)
    v['kaynak_takvimi']['kullanilabilir']=True
    v['tesis_takvimi']=pd.DataFrame({'tarih_saat':ts,'temel_yuk_kw':0,'guc_siniri_kw':1000})
    v['bakimlar']=v['bakimlar'].iloc[:0].copy()
    v['fiyatlar']=pd.DataFrame({'tarih_saat':ts,'PTF (TL/MWh)':[40,30,5,10,50,60,25,20]})
    plan=pd.MultiIndex.from_product([['H01','H02','P01'],ts],names=['kaynak_id','tarih_saat']).to_frame(index=False)
    plan['durum']='kapali';plan['urun_id']='';plan['is_emri_id']=''
    for r,idx,eid in [('H01',[0,1],'OG'),('P01',[1,2],'PA')]:
        mask=plan['kaynak_id'].eq(r)&plan['tarih_saat'].isin(ts[idx])
        plan.loc[mask,['durum','urun_id','is_emri_id']]=['uretim','UR01',eid]
    v['referans_plan']=plan
    v['referans_yuklemeler']=pd.DataFrame([['B','Y01',ts[3],60],['T','Y02',ts[3],60]],columns=v['referans_yuklemeler'].columns)
    return v


def bagimsiz_en_iyi(fiyat):
    """İki alternatif değirmen, iki saatlik bloklar ve bütün yükleme saatleri.

    Sipariş miktarı tek saatte yüklenebilir; stok kapasiteleri gecikmiş
    tek seferlik yüklemeye yeterlidir. Pozitif saatlik yükleme gideriyle
    bölünmüş yükleme daha ucuz olamaz; yükleme uç noktaları bu yüzden yeterlidir.
    """
    en_iyi=float('inf');uygun=0
    for guc in [200,300]:
        for og in range(7):
            for pa in range(7):
                for bulk in range(8):
                    for bag in range(8):
                        d,t=60,0;bedel=10.0
                        for s in range(8):
                            uretim=og<=s<og+2;paket=pa<=s<pa+2
                            d-=30*paket+60*(s==bulk);t-=60*(s==bag)
                            if d<0 or t<0:break
                            d+=60*uretim;t+=30*paket
                            if d>240 or t>120:break
                            enerji=guc*uretim+50*paket+10*(s==bulk)+10*(s==bag)+10*(s==og)+10*(s==pa)
                            bedel+=enerji/1000*fiyat[s]
                        else:
                            if d==60 and t==0:
                                uygun+=1;en_iyi=min(en_iyi,bedel)
    if uygun==0:raise AssertionError('Bağımsız aramada uygun plan yok.')
    return en_iyi,uygun


if __name__=='__main__':
    v=firma_verisini_oku(proje)
    for ad,sabit in [('degisken_fiyat',False),('sabit_fiyat',True)]:
        tiny=kucuk_veri(v)
        if sabit:tiny['fiyatlar']['PTF (TL/MWh)']=20
        beklenen,adet=bagimsiz_en_iyi(tiny['fiyatlar']['PTF (TL/MWh)'].to_numpy())
        result=firma_cizelgele(tiny,zaman_siniri=15,goreli_acik=0)
        assert result[-1]['tolerans_icinde_optimum']
        assert np.isclose(result[-2]['Karşılaştırılan toplam maliyet (TL)'],beklenen,atol=1e-5)
        print(f'{ad}: bağımsız arama ile eşleşti; {adet} uygun alternatif; maliyet={beklenen:.4f}')
    # Pozitif plan değişikliği giderinin bağımsız hesapla eşleşmesi.
    tiny=kucuk_veri(v)
    res=firma_cizelgele(tiny,zaman_siniri=15,goreli_acik=0,degisiklik_gideri=50)
    assert res[-1]['bagimsiz_maliyet_kontrolu']
    assert res[-2]['Değişen kaynak-saat']==0
    print('Yüksek plan değişikliği giderinde referans plan korundu; maliyet eşleşti.')

    # Geniş ana arama toleransı, yükleme alt problemindeki küçük kazancı yutmamalı.
    tiny=kucuk_veri(v)
    zamanlar=pd.date_range('2025-10-06',periods=13,freq='h')
    for ad in ['tesis_takvimi','fiyatlar']:
        yeni=pd.concat([tiny[ad],pd.concat([tiny[ad].iloc[[-1]]]*5,ignore_index=True)],ignore_index=True)
        yeni['tarih_saat']=zamanlar
        tiny[ad]=yeni
    kaynaklar=tiny['kaynaklar']['kaynak_id']
    tiny['kaynak_takvimi']=pd.MultiIndex.from_product([kaynaklar,zamanlar],names=['kaynak_id','tarih_saat']).to_frame(index=False)
    tiny['kaynak_takvimi']['kullanilabilir']=True
    ek=pd.MultiIndex.from_product([tiny['isletme_kurallari']['kaynak_id'],zamanlar[8:]],names=['kaynak_id','tarih_saat']).to_frame(index=False)
    ek[['durum','urun_id','is_emri_id']]=['kapali','','']
    tiny['referans_plan']=pd.concat([tiny['referans_plan'],ek],ignore_index=True)
    # Ana fiyatı yüksek tutup yalnızca teslim saatlerinde küçük fark oluştur.
    tiny['fiyatlar']['PTF (TL/MWh)']=100000.0
    tiny['fiyatlar'].loc[tiny['fiyatlar']['tarih_saat'].dt.hour==4,'PTF (TL/MWh)']=99999.0
    res=firma_cizelgele(tiny,zaman_siniri=0.1,goreli_acik=0.01)
    yerel=res[-1]['baslangic_iyilestirmeleri'][0]
    assert yerel['goreli_acik']<=0.000001+1e-8
    once=maliyet_ve_ozet(tiny,tiny['referans_plan'],tiny['referans_yuklemeler'])[-1]['Karşılaştırılan toplam maliyet (TL)']
    assert yerel['maliyet_tl'] < once-0.005
    print('Yerel arama, yüzde 1 ana toleransın altındaki küçük yükleme kazancını buldu.')
    tekrar=firma_cizelgele(tiny,zaman_siniri=0.1,goreli_acik=0.01,
                          yerel_iyilestirme=False,baslangic_cozumu=res[:2])
    assert tekrar[-1]['maliyet_tl']<=res[-1]['maliyet_tl']+0.02
    assert np.isclose(tekrar[-1]['baslangic_maliyet_tl'],res[-1]['maliyet_tl'])
    print('Doğrulanmış önceki çözüm başlangıç olarak korundu.')
