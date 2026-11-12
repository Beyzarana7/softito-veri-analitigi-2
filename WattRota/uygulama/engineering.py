"""Kayıtlı planlardan mühendislik göstergeleri; çözüm veya tahmin üretmez."""
import numpy as np
import pandas as pd
from analytics import date_label
from service import evaluated_cost
from firma_cizelgeleme import maliyet_ve_ozet

def engineering(a):
    firm=a['firm'];prices=a['prices'].set_index('tarih_saat');expected=prices.planlama_fiyati_tl_mwh
    v={k:x.copy(deep=True) for k,x in firm.items()}
    v['fiyatlar']=pd.DataFrame({'tarih_saat':expected.index,'PTF (TL/MWh)':expected.to_numpy()})
    _,activities,expected_hourly,_=maliyet_ve_ozet(v,a['plan'],a['loads'])
    _,ref_activities,_,_=maliyet_ve_ozet(v,firm['referans_plan'],firm['referans_yuklemeler'])
    def daily(frame,column):return frame.groupby(frame.tarih_saat.dt.normalize())[column].sum()
    day=pd.DataFrame({'Beklenen maliyet (TL)':daily(expected_hourly,'karsilastirilan_maliyet_tl')})
    if a['use_actual']:
        day['Gerçekleşen maliyet (TL)']=daily(a['hourly'],'karsilastirilan_maliyet_tl')
        day['Referans gerçek maliyeti (TL)']=daily(a['reference_hourly'],'karsilastirilan_maliyet_tl')
        day['Avantaj (TL)']=day['Referans gerçek maliyeti (TL)']-day['Gerçekleşen maliyet (TL)']
    else:
        for c in ('Gerçekleşen maliyet (TL)','Referans gerçek maliyeti (TL)','Avantaj (TL)'):day[c]=np.nan
    checks={'Beklenen maliyet (TL)':a['decision']['expected_cost_tl']}
    if a['use_actual']:checks.update({'Gerçekleşen maliyet (TL)':a['evaluation']['actual_cost_tl'],'Referans gerçek maliyeti (TL)':a['evaluation']['reference_actual_cost_tl'],'Avantaj (TL)':a['evaluation']['actual_advantage_tl']})
    for c,total in checks.items():
        if abs(day[c].sum()-total)>.02:raise ValueError('Günlük toplam kayıtlı maliyetle eşleşmiyor: '+c)
    day=day.rename_axis('Gün').reset_index();day['Tarih']=day.Gün.map(date_label)
    names=firm['kaynaklar'].set_index('kaynak_id').kaynak_adi
    types=firm['kaynaklar'].set_index('kaynak_id').kaynak_turu
    cap=firm['kaynak_urun'].set_index(['kaynak_id','urun_id'])
    op=firm['siparisler'].set_index('siparis_id').urun_id
    stats=[];energy=[];distribution=[];daily_production=[]
    median=float(expected.median())
    for label,gantt,act,loads,hourly in [('Referans',a['reference_gantt'],ref_activities,firm['referans_yuklemeler'],a['reference_hourly']),('WattRota',a['gantt'],activities,a['loads'],a['hourly'])]:
        for rid,g in gantt.groupby('kaynak_id'):
            counts=g.durum.value_counts();available=int(g.kullanilabilir.sum());active=int(g.durum.isin(['uretim','hazirlik','yukleme']).sum())
            stats.append({'Makine':names[rid],'Plan':label,'Üretim (saat)':int(counts.get('uretim',0)),'Yükleme (saat)':int(counts.get('yukleme',0)),
                'Ürün değişimi (saat)':int(counts.get('hazirlik',0)),'Aktif (saat)':active,'Bekleme (saat)':int(counts.get('kapali',0)),
                'Bakım (saat)':int(counts.get('bakim',0)),'Çalışma dışı (saat)':int(counts.get('takvim_disi',0)),
                'Uygun (saat)':available,'Kullanım (%)':100*active/available if available else np.nan})
        e=act.groupby('kaynak_id').enerji_kwh.sum().to_dict()
        for x in loads.itertuples():
            rid=x.kaynak_id;p=op[x.siparis_id]
            e[rid]=e.get(rid,0.)+float(cap.loc[(rid,p),'calisma_gucu_kw'])
        for rid in names.index:energy.append({'Makine':names[rid],'Plan':label,'Enerji (kWh)':e.get(rid,0.)})
        base=float(firm['tesis_takvimi'].temel_yuk_kw.sum())
        if abs(sum(e.values())+base-hourly.toplam_enerji_kwh.sum())>1e-6:raise ValueError('Makine enerjileri ile tesis toplamı eşleşmiyor.')
        prod=act[act.kaynak_id.map(types).eq('ogutme')].copy()
        prod['Fiyat grubu']=np.where(prod.tarih_saat.map(expected)<=median,'Düşük fiyatlı saatler','Yüksek fiyatlı saatler')
        for band,g in prod.groupby('Fiyat grubu'):distribution.append({'Plan':label,'Fiyat grubu':band,'Üretim (ton)':g.miktar_ton.sum()})
        for t,g in prod.groupby(prod.tarih_saat.dt.normalize()):daily_production.append({'Gün':t,'Plan':label,'Üretim (ton)':g.miktar_ton.sum()})
    changed=a['gantt'][['kaynak_id','tarih_saat','Makine','Saat','Durum','Ürün','miktar_ton']].merge(
        a['reference_gantt'][['kaynak_id','tarih_saat','Durum','Ürün','miktar_ton']],on=['kaynak_id','tarih_saat'],suffixes=('','_ref'))
    changed=changed[(changed.Durum!=changed.Durum_ref)|(changed['Ürün']!=changed['Ürün_ref'])|((changed.miktar_ton.fillna(0)-changed.miktar_ton_ref.fillna(0)).abs()>1e-6)]
    changed=changed[['Makine','Saat','Durum_ref','Durum','Ürün_ref','Ürün','miktar_ton_ref','miktar_ton']].rename(columns={'Durum_ref':'Referans durumu','Durum':'WattRota durumu','Ürün_ref':'Referans ürünü','Ürün':'WattRota ürünü','miktar_ton_ref':'Referans yükleme (ton)','miktar_ton':'WattRota yükleme (ton)'})
    performance=pd.DataFrame(daily_production).pivot(index='Gün',columns='Plan',values='Üretim (ton)').rename(columns={'Referans':'Referans üretim (ton)','WattRota':'WattRota üretim (ton)'})
    performance['Teslim (ton)']=a['loads'].groupby(a['loads'].tarih_saat.dt.normalize()).miktar_ton.sum()
    completion=a['loads'].groupby('siparis_id').tarih_saat.max().dt.normalize().value_counts()
    performance['Tamamlanan sipariş']=completion
    performance=performance.fillna(0).reset_index();performance['Tarih']=performance.Gün.map(date_label)
    return dict(daily=day,machines=pd.DataFrame(stats),machine_energy=pd.DataFrame(energy),changes=changed,
        distribution=pd.DataFrame(distribution),median_price=median,performance=performance,base_energy=base,
        produced_tonnes=float(activities.loc[activities.kaynak_id.map(types).eq('ogutme'),'miktar_ton'].sum()))
